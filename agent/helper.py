"""The helper behind the floor page's ask box (docs/ASK-FAMILIES.md, part 4).

    python3 -m agent.helper [--port 8766] [--smt2020 data/smt2020/hvlm] [--quick]

Serves `web/` and an API on 127.0.0.1 only. It holds the model key (read from its file, never logged and never sent
to the page), asks a model for a scenario, checks it, runs `fabsim score` natively (4 threads, niced, one job at a
time) and hands the report to the page. The model is Meta's muse-spark-1.3-contributor at low effort by default
(`--preset meta`); `--preset open` asks Muse Spark Open on Baseten for the runs shown in the submission. Spend is
counted from each answer's usage and capped (`--spend-cap`, $5 by default; docs/BASETEN-PRICING.md). Without a key
it answers the recorded example questions and runs scenarios a person writes. From the SMT2020 testbed, a published set of a fab's tool groups, routes and times; not a real fab."""

import argparse
import hashlib
import re
import json
import os
import mimetypes
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent import ask, spend
from agent.fabgym_agent import DEFAULT_KEY, HttpModel
from agent import poster, race, sketch

ROOT = Path(__file__).resolve().parents[1]
KEYS = Path.home() / ".config" / "fab-gym"
PRESETS = {
    # ideas and trials (the founder, 30 Oct): Meta's contributor model; Meta may train on what is sent and returned
    "meta": {"provider": "meta", "label": "Meta", "base_url": "https://api.meta.ai/v1", "model": "muse-spark-1.3-contributor",
             "key_file": KEYS / "meta.key", "reasoning_effort": "low"},
    # the runs shown in the submission: the open-weights model
    "open": {"provider": "baseten", "label": "Baseten", "base_url": "https://inference.baseten.co/v1",
             "model": "meta-models/muse-spark-open-1026", "key_file": DEFAULT_KEY, "reasoning_effort": None},
}
BASE_URL = PRESETS["open"]["base_url"]
MODEL = PRESETS["open"]["model"]
SPEND_CAP = 20.0  # dollars, the helper's total for every model (raised 1 Nov by quiz from $5)
QUICK = ["--seeds", "0..2", "--warmup", "1", "--window", "2", "--layout-iters", "300"]


def plan_of(text, today=""):
    """A setup's floor from its fab file (docs/RUNS.md, part 2): the phases' lengths, every placed group's phase, side,
    bay, place along the spine, depth and tools, and, against today's file, the copies and the groups that stand
    elsewhere. None when the file places no groups (a question with one family keeps today's floor)."""
    def places(t):
        out = {}
        for line in t.splitlines():
            f = line.split("\t")
            if f[0] == "place" and len(f) == 7:
                out[f[1]] = (int(f[2]), int(f[3]), int(f[4]), float(f[5]), float(f[6]))
        return out
    here = places(text)
    if not here:
        return None
    tools, phases = {}, []
    for line in text.splitlines():
        f = line.split("\t")
        if f[0] == "group" and len(f) > 2:
            tools[f[1]] = int(f[2])
        elif f[0] == "ohtphase" and len(f) > 1:
            phases.append(float(f[1]))
    was = places(today) if today else {}
    groups = [{"g": g, "phase": p[0], "side": p[1], "bay": p[2], "x": p[3], "y": p[4], "tools": tools.get(g, 1)} for g, p in here.items()]
    return {
        "phases": phases,
        "groups": groups,
        "copies": [g for g in here if g.endswith("@B")],
        "moved": [g for g, p in here.items() if g in was and was[g][:3] != p[:3]],
    }


NO_KEY = Path("/nonexistent/fab-gym/no-model.key")  # where a no-model helper looks for keys: nowhere


class Helper:
    def __init__(self, web=ROOT / "web", fabsim=ROOT / "target" / "release" / "fabsim", smt2020=ROOT / "data" / "smt2020" / "hvlm",
                 key_file=None, jobs=ROOT / "data" / "ask" / "jobs", quick=False, base_url=None, model=None, threads=4,
                 preset="meta", spend_cap=SPEND_CAP, stand_in=None, race_cap=8.0, meta_key_file=None, meta_base_url=None,
                 poster_cap=5.0, sketch_cap=2.0, glossary_cap=5.0, runs=ROOT / "data" / "ask" / "runs", no_model=False):
        p = PRESETS[preset]
        # no paid model (tests; docs/RUNS.md, part 3): the real keys are hidden; a key file named here (a fake server) stays
        no_model = no_model or os.environ.get("FABGYM_NO_MODEL") == "1"
        self.no_model = no_model
        self.preset = preset
        self.provider = p["provider"]
        self.provider_label = p["label"]
        self.web = Path(web).resolve()
        self.fabsim = Path(fabsim)
        self.smt2020 = Path(smt2020)
        self.key_file = Path(key_file).expanduser() if key_file is not None else NO_KEY if no_model else Path(p["key_file"]).expanduser()
        self.jobs_dir = Path(jobs)
        # numbered runs, kept for good (docs/RUNS.md): data/ask/runs/Q-0004/ holds the setup, the log and the report
        self.runs_dir = Path(runs)
        self.quick = quick
        self.base_url = base_url or p["base_url"]
        self.model_name = model or p["model"]
        self.reasoning_effort = p["reasoning_effort"]
        self.meter = spend.Meter(spend.price(self.provider, self.model_name), cap_usd=spend_cap,
                                 path=self.jobs_dir.parent / "spend.json")
        # Meta's models in the 2D gym (docs/RACE-AI.md): a meter per feature, all under the helper's total, and a
        # stand-in that answers from recorded replies and spends nothing
        self.total_cap = float(spend_cap)
        self.stand_in = Path(stand_in) if stand_in else None
        self.meta_key_file = Path(meta_key_file).expanduser() if meta_key_file else NO_KEY if no_model else PRESETS["meta"]["key_file"]
        self.meta_base_url = meta_base_url or PRESETS["meta"]["base_url"]
        self.race_meter = spend.Meter(spend.price("meta", race.MODEL), cap_usd=race_cap, path=self.jobs_dir.parent / "spend-race.json")
        self.poster_meter = spend.Meter({}, cap_usd=poster_cap, path=self.jobs_dir.parent / "spend-poster.json")
        self.sketch_meter = spend.Meter(spend.price("meta", sketch.MODEL), cap_usd=sketch_cap, path=self.jobs_dir.parent / "spend-sketch.json")
        # the glossary's pictures, newcomer lines and questions (docs/SIM-SETTINGS.md's plan: glossary after the curves)
        self.glossary_meter = spend.Meter(spend.price("meta", sketch.MODEL), cap_usd=glossary_cap, path=self.jobs_dir.parent / "spend-glossary.json")
        self.threads = threads
        self.groups = ask.load_groups(self.web / "data" / "areas.tsv")
        self.jobs = {}
        self.lock = threading.Lock()
        self.keep_lock = threading.Lock()  # numbering the runs the pages send (docs/RUNS.md, part 3)
        self.fab_lock = threading.Lock()

    def __repr__(self):
        return f"Helper(web={str(self.web)!r}, model={self.model_name!r}, key_file={str(self.key_file)!r})"

    def model_connected(self):
        try:
            return self.key_file.is_file() and self.key_file.stat().st_size > 0
        except OSError:
            return False

    def busy(self):
        return any(j["stage"] not in ("done", "failed") for j in self.jobs.values())

    def status(self):
        return {
            "model_connected": self.model_connected(),
            "model": f"{self.model_name} on {self.provider_label}" if self.model_connected() else None,
            "examples": [{"question": e["question"]} for e in ask.examples()],
            "busy": self.busy(),
            "quick": self.quick,
            "spend": self.meter.summary(),
        }

    def client(self):
        """The model the ask box talks to: the preset's effort, and every request counted by the meter."""
        return HttpModel(self.base_url, self.model_name, key_file=self.key_file, temperature=0.2,
                         reasoning_effort=self.reasoning_effort, meter=self.meter)

    # ------------------------------------------------------------------ jobs

    # ------------------------------------------------------------------ numbered runs (docs/RUNS.md)

    KIND = {"Q": "question", "S": "settings", "B": "build", "F": "floor"}

    def _next_id(self, prefix="Q"):
        """The next free number of a kind, from the runs on disk, so a number is never used twice."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        used = [int(d.name[2:]) for d in self.runs_dir.iterdir() if d.is_dir() and re.fullmatch(prefix + r"-\d{4,}", d.name)]
        n = max(used, default=0) + 1
        while True:
            jid = f"{prefix}-{n:04d}"
            try:
                (self.runs_dir / jid).mkdir()  # taken at once, so two helpers cannot pick the same number
                return jid
            except FileExistsError:
                n += 1

    def _dir(self, jid):
        """A run's folder: numbered runs in the runs folder, older jobs where they were."""
        return self.runs_dir / jid if re.fullmatch(r"[A-Z]-\d{4,}", jid or "") else self.jobs_dir / jid

    META = ("id", "kind", "question", "answer_source", "model", "answer", "checks", "scenario", "stage", "started", "started_at",
            "seconds", "error", "runs_done", "runs_total", "leader", "model_usd", "title", "key", "record")

    def _save(self, jid):
        """The run's card on disk (run.json): what was asked, where its setup came from, how far it got."""
        j = self.jobs[jid]
        d = self._dir(jid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.json").write_text(json.dumps({k: j.get(k) for k in self.META}, indent=1))

    def _start(self, job, work):
        with self.lock:
            if self.busy():
                return {"error": "One question runs at a time; wait for the one running now.", "busy": True}
            jid = self._next_id("Q")
            job.update({"id": jid, "kind": "question", "stage": "queued", "started": time.time(),
                        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "report": None, "error": None,
                        "events": [], "runs_done": 0, "runs_total": None, "leader": None,
                        "model": self.model_name if job.get("answer_source") == "model" else None})
            self.jobs[jid] = job
            self._save(jid)
        threading.Thread(target=self._run, args=(jid, work), daemon=True).start()
        return {"job": jid}

    def ask(self, question):
        q = (question or "").strip()
        if not q:
            return {"error": "Type a question first."}
        for e in ask.examples():
            if e["question"].strip().lower() == q.lower():
                return self._start({"question": q, "answer_source": "example", "answer": e["answer"], "note": e["note"]}, "answer")
        if not self.model_connected():
            return {
                "no_model": True,
                "message": "No model is connected yet, so only the example questions answer. You can also write a scenario by hand.",
                "examples": [e["question"] for e in ask.examples()],
            }
        return self._start({"question": q, "answer_source": "model", "answer": None}, "model")

    def run_text(self, text):
        if not (text or "").strip():
            return {"error": "The scenario is empty."}
        # a hand-written setup carries its question in its own question line
        q = next((ln.split("\t", 1)[1].strip() for ln in text.splitlines() if ln.startswith("question\t")), None)
        return self._start({"question": q, "answer_source": "hand", "answer": None, "scenario": text}, "text")

    def _run(self, jid, work):
        job = self.jobs[jid]
        try:
            if work == "model":
                job["stage"] = "asking the model"
                self._save(jid)
                before = self.meter.usd
                model = self.client()
                try:
                    reply, answer = ask.ask_model(model, job["question"], self.groups)
                finally:
                    job["model_usd"] = round(self.meter.usd - before, 6)
                job["reply"] = reply
                job["answer"] = answer
            if work in ("model", "answer"):
                job["stage"] = "checking the scenario"
                reasons = ask.check(job["answer"], self.groups)
                job["checks"] = reasons
                if reasons:
                    raise ValueError("The scenario was refused: " + "; ".join(reasons))
                job["scenario"] = ask.to_scenario(job["answer"])
            job["stage"] = "laying out and simulating"
            self._save(jid)
            job["report"] = self._score(jid, job["scenario"])
            job["leader"] = job["report"].get("best")
            job["stage"] = "done"
        except Exception as e:  # shown to the person; never holds the key
            job["error"] = str(e)
            job["stage"] = "failed"
        job["seconds"] = round(time.time() - job["started"], 1)
        self._save(jid)

    def _score(self, jid, text):
        """Run the simulator with --events: each event it reports is stamped with the seconds since the run began,
        kept with the job and appended to the run's log.jsonl as it comes (docs/RUNS.md)."""
        job = self.jobs[jid]
        d = self._dir(jid)
        d.mkdir(parents=True, exist_ok=True)
        f = d / "scenario.txt"
        f.write_text(text)
        cmd = ["nice", "-n", "10", str(self.fabsim), "score", str(f), str(self.smt2020), "--threads", str(self.threads),
               "--layout-cache", str(ROOT / "data" / "ask" / "layouts"), "--events"]
        if self.quick:
            cmd += QUICK
        out = d / "report.part"
        other = []
        with open(out, "w") as rep, open(d / "log.jsonl", "a") as log:
            # the report goes to a file, so a large one never blocks the pipe the events come through
            p = subprocess.Popen(cmd, cwd=ROOT, stdout=rep, stderr=subprocess.PIPE, text=True)
            for line in p.stderr:
                if not line.startswith("event "):
                    other.append(line.rstrip())
                    continue
                try:
                    ev = json.loads(line[6:])
                except ValueError:
                    continue
                ev["t"] = round(time.time() - job["started"], 2)
                log.write(json.dumps(ev) + "\n")
                log.flush()
                job["events"].append(ev)
                if ev.get("e") == "start":
                    job["runs_total"] = ev.get("runs")
                    job["runs_began"] = ev["t"]
                elif ev.get("e") == "run":
                    job["runs_done"] += 1
            code = p.wait()
        if code != 0:
            msg = (other or ["the simulator stopped"])[-1]
            raise ValueError(msg.removeprefix("refused: "))
        out.replace(d / "report.json")
        return json.loads((d / "report.json").read_text())

    def _load(self, jid):
        """A run from its folder, for runs finished before this helper started."""
        if not re.fullmatch(r"[A-Z]-\d{4,}", jid or ""):
            return None
        d = self.runs_dir / jid
        try:
            j = json.loads((d / "run.json").read_text())
        except (OSError, ValueError):
            return None
        j["events"] = [json.loads(x) for x in (d / "log.jsonl").read_text().splitlines() if x.strip()] if (d / "log.jsonl").is_file() else []
        j["report"] = json.loads((d / "report.json").read_text()) if (d / "report.json").is_file() else None
        if (d / "signed.json").is_file():
            j["card"] = json.loads((d / "signed.json").read_text())
        if j.get("stage") not in ("done", "failed"):
            j["stage"], j["error"] = "failed", "The helper stopped before this run finished."
        j.setdefault("runs_done", sum(1 for e in j["events"] if e.get("e") == "run"))
        self.jobs[jid] = j
        return j

    def job(self, jid, since=None):
        j = self.jobs.get(jid) or self._load(jid)
        if j is None:
            return None
        out = {k: v for k, v in j.items() if k not in ("report", "events")}
        evs = j.get("events") or []
        k = max(0, int(since)) if since is not None else 0
        out["events"], out["since"] = evs[k:], k
        out["elapsed"] = round((time.time() - j["started"]) if j.get("stage") not in ("done", "failed") else (j.get("seconds") or 0), 1)
        done, total = j.get("runs_done") or 0, j.get("runs_total")
        out["minutes_left"] = None
        if total and 2 <= done < total and j.get("stage") not in ("done", "failed"):
            began = j.get("runs_began") or 0
            pace = (time.time() - j["started"] - began) / done  # seconds a run, all workers together
            out["minutes_left"] = round(pace * (total - done) / 60, 1)
        rep = j.get("report")
        if rep is not None:
            rep = dict(rep)
            arms = rep.get("arms", [])
            # each setup's floor as a plan, worked out once (docs/RUNS.md, part 2)
            if "_plans" not in j:
                today = arms[0]["shop"] if arms else ""
                j["_plans"] = [plan_of(a.get("shop", ""), today) for a in arms]
            rep["arms"] = [{k: v for k, v in a.items() if k != "shop"} | {"shop_url": f"/api/job/{jid}/arm/{i}", "plan": j["_plans"][i],
                                                                         "rule_in_file": "\ndispatch\t" in a.get("shop", "")}
                           for i, a in enumerate(arms)]
        out["report"] = rep
        return out

    def runs(self):
        """Every numbered run on disk, newest first (docs/RUNS.md)."""
        rows = []
        if self.runs_dir.is_dir():
            for d in self.runs_dir.iterdir():
                if not (d.is_dir() and re.fullmatch(r"[A-Z]-\d{4,}", d.name)):
                    continue
                live = self.jobs.get(d.name)
                try:
                    j = live or json.loads((d / "run.json").read_text())
                except (OSError, ValueError):
                    continue
                stage = j.get("stage")
                status = "done" if stage == "done" else "failed" if stage == "failed" else "running" if live else "stopped"
                rows.append({"id": d.name, "kind": j.get("kind") or self.KIND.get(d.name[0], "question"), "question": j.get("question"),
                             "title": j.get("title") or j.get("question"),
                             "started": j.get("started_at"), "started_ts": j.get("started") or 0, "status": status,
                             "runs_done": j.get("runs_done") or 0, "runs_total": j.get("runs_total"), "leader": j.get("leader"),
                             "seconds": j.get("seconds"), "answer_source": j.get("answer_source")})
        rows.sort(key=lambda r: (r["started_ts"], r["id"]), reverse=True)
        return {"runs": rows}

    # ------------------------------------------------------------------ signing (docs/FLOOR-UI.md)

    @staticmethod
    def _hashes(job):
        return {k: hashlib.sha256(v.encode()).hexdigest() for k, v in (
            ("question", job.get("question") or ""), ("scenario", job.get("scenario") or ""),
            ("report", json.dumps(job.get("report"), sort_keys=True)))}

    def sign(self, jid, name):
        """A person signs a finished answer: their name, the time and SHA-256 of question, scenario and report."""
        j = self.jobs.get(jid) or self._load(jid)
        name = (name or "").strip()
        if j is None:
            return {"signed": False, "error": "No such answer."}
        if j.get("stage") != "done" or j.get("report") is None:
            return {"signed": False, "error": "Only a finished answer can be signed."}
        if not name:
            return {"signed": False, "error": "Type the name of the person signing."}
        if j.get("card"):
            return {"signed": False, "error": "This answer is already signed.", "card": j["card"]}
        card = {"name": name[:120], "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sha256": self._hashes(j)}
        j["card"] = card
        d = self._dir(jid); d.mkdir(parents=True, exist_ok=True)
        (d / "signed.json").write_text(json.dumps(card, indent=1))
        return {"signed": True, "card": card}

    def verify(self, jid):
        """True while the question, scenario and report still match their signature."""
        j = self.jobs.get(jid)
        return bool(j and j.get("card") and j["card"]["sha256"] == self._hashes(j))

    # ------------------------------------------------------------------ the map editor (docs/EDITOR.md)

    def fab_base(self, name):
        """A template's base shop and its areas: SMT2020's, from the floor page's data."""
        if name != "smt2020":
            return {"error": f"no base {name!r}; the teaching fab is built into the editor"}
        d = self.web / "data"
        try:
            return {"shop": (d / "shop.txt").read_text(), "areas": (d / "areas.tsv").read_text()}
        except OSError:
            return {"error": "the SMT2020 data is not built yet: run web/build.sh"}

    def _fab_file(self, text):
        d = self.jobs_dir.parent / "fab"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{hashlib.sha256(text.encode()).hexdigest()[:16]}.fab.txt"
        # written whole, then renamed into place: a run and a check of the same layout at once must never read half a file
        tmp = d / f".{f.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        tmp.write_text(text)
        os.replace(tmp, f)
        return f

    def fab_check(self, text):
        """The simulator's checks on a fab file: {"ok", "issues"}, or {"ok": False, "error"} for text it refuses."""
        p = subprocess.run([str(self.fabsim), "fab-check", str(self._fab_file(text)), "--json"], capture_output=True, text=True)
        if p.returncode not in (0, 2):
            return {"ok": False, "error": (p.stderr.strip().splitlines() or ["the simulator refused the file"])[-1].removeprefix("refused: ")}
        issues = json.loads(p.stdout or "[]")
        return {"ok": p.returncode == 0, "issues": issues}

    def _ov_file(self, overrides):
        """An overrides file (docs/OVERRIDES.md) on disk, or None when there is none."""
        if not overrides:
            return None
        t = json.dumps(overrides, sort_keys=True)
        d = self.jobs_dir.parent / "fab"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{hashlib.sha256(t.encode()).hexdigest()[:16]}.overrides.json"
        f.write_text(t)
        return f

    def _fab_cmd(self, text, overrides, args):
        """Check, then run `fabsim ARGS...` niced, one at a time: (result, None) or (None, error dict)."""
        checks = self.fab_check(text)
        if not checks.get("ok"):
            return None, {"error": checks.get("error") or "The layout has errors; fix them before running.", "checks": checks}
        if not self.fab_lock.acquire(blocking=False):
            return None, {"error": "A run is going; wait for it.", "busy": True}
        try:
            cmd = ["nice", "-n", "10", str(self.fabsim), args[0], str(self._fab_file(text)), *args[1:]]
            ov = self._ov_file(overrides)
            if ov:
                cmd += ["--overrides", str(ov)]
            t = time.time()
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            if p.returncode != 0:
                msg = (p.stderr.strip().splitlines() or ["the simulator stopped"])[-1]
                return None, {"error": msg.replace(str(ov), "the overrides") if ov else msg, "checks": checks}
            return (json.loads(p.stdout), checks, round(time.time() - t, 1)), None
        finally:
            self.fab_lock.release()

    # ------------------------------------------------------------------ every kind of run (docs/RUNS.md, part 3)

    def _keyed(self, prefix, key):
        """A kept run of this kind with this key: the same run played again keeps its number."""
        if not key or not self.runs_dir.is_dir():
            return None
        for d in sorted(self.runs_dir.glob(prefix + "-*")):
            try:
                if json.loads((d / "run.json").read_text()).get("key") == key:
                    return d.name
            except (OSError, ValueError):
                continue
        return None

    def _keep(self, prefix, kind, title, key, record, events=(), files=None):
        """Number and keep a finished run of the page's (Simulation settings, the Floor) or Build's. `record` may be a
        function of the new number."""
        with self.keep_lock:
            jid = self._keyed(prefix, key)
            if jid:
                return jid
            jid = self._next_id(prefix)
            d = self.runs_dir / jid
            for name, text in (files or {}).items():
                (d / name).write_text(text)
            now = time.time()
            j = {"id": jid, "kind": kind, "question": None, "title": title, "key": key, "record": record(jid) if callable(record) else record, "stage": "done",
                 "started": now, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)), "seconds": 0,
                 "runs_done": sum(1 for e in events if e.get("e") == "run"), "runs_total": sum(1 for e in events if e.get("e") == "run")}
            (d / "log.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
            (d / "run.json").write_text(json.dumps({k: j.get(k) for k in self.META}, indent=1))
            return jid

    def record_run(self, body):
        """A Simulation settings comparison or a Floor run the page sends when it ends: {"id"}."""
        kind = body.get("kind")
        prefix = {"settings": "S", "floor": "F"}.get(kind)
        if not prefix:
            return {"error": "kind is settings or floor"}
        measure, seeds, arms = body.get("measure"), body.get("seeds") or [], body.get("arms") or []
        events = []
        if body.get("runs"):
            events.append({"e": "start", "arms": arms, "seeds": seeds, "measure": measure, "runs": len(body["runs"]),
                           "warmup_days": 0, "window_days": body.get("days") or 0, "threads": 0, "t": 0})
            for r in body["runs"]:
                events.append({"e": "run", "arm": r.get("arm"), "seed": r.get("seed"), "measure": measure,
                               "value": (r.get("values") or {}).get(measure), "values": r.get("values"), "point": None, "t": 0})
            events.append({"e": "end", "best": None, "t": 0})
        record = {k: body.get(k) for k in ("settings", "summary", "link", "days", "seeds")}
        return {"id": self._keep(prefix, kind, str(body.get("title") or kind), body.get("key"), record, events)}

    def fab_run(self, text, seed=1, days=2.0, every=60.0, overrides=None, record=None):
        """The checks, then, with no errors, a run's moods (`fabsim moods`), niced, one at a time. With `record` (Build's
        title, layout, template and challenge), the run is kept as a B run (docs/RUNS.md, part 3)."""
        r, err = self._fab_cmd(text, overrides, ["moods", str(seed), "--until", str(days * 1440.0), "--every", str(every)])
        if err:
            return err
        if record:
            key = hashlib.sha256(json.dumps([text, overrides, seed, days], sort_keys=True).encode()).hexdigest()
            score = r[0].get("score")
            files = {"fab.txt": text, "state.json": json.dumps(record.get("state")), "overrides.json": json.dumps(overrides)}
            rec = lambda jid: {"title": record.get("title"), "template": record.get("template"), "challenge": record.get("challenge"),
                               "state": record.get("state"), "seed": seed, "days": days, "score": score, "overrides": overrides,
                               "fab_url": f"/api/job/{jid}/fab"}
            jid = self._keep("B", "build", str(record.get("title") or "Build"), key, rec, files=files)
            return {"moods": r[0], "checks": r[1], "seconds": r[2], "run": jid}
        return {"moods": r[0], "checks": r[1], "seconds": r[2]}

    def fab_replay(self, text, seed=1, start=0.0, minutes=30.0, overrides=None):
        """Every vehicle's stays on the rail between START and START+MINUTES (`fabsim replay`), for the page to draw."""
        r, err = self._fab_cmd(text, overrides, ["replay", str(seed), "--from", str(start), "--to", str(start + minutes)])
        if err:
            return err
        return {**r[0], "seconds": r[2]}

    def arm_shop(self, jid, k):
        j = self.jobs.get(jid) or self._load(jid)
        arms = (j or {}).get("report", {}) or {}
        arms = arms.get("arms", [])
        return arms[k]["shop"] if 0 <= k < len(arms) else None


    # ---------------------------------------------------------------- Meta's models in the 2D gym (docs/RACE-AI.md)
    def spent_total(self):
        return self.meter.usd + self.race_meter.usd + self.poster_meter.usd + self.sketch_meter.usd + self.glossary_meter.usd

    def race_step(self, body):
        """One move of Race the AI: the page's game so far in, Muse Wonder's next message out, with its cost."""
        messages = body.get("messages")
        why = race.validate(messages)
        if why:
            return {"error": why}
        base = {"cap_usd": self.race_meter.cap_usd}
        if self.stand_in:
            return {"message": race.replay(self.stand_in, messages), "model": "stand-in", "cost_usd": 0,
                    "spent_usd": round(self.race_meter.usd, 6), **base}
        if self.race_meter.usd >= self.race_meter.cap_usd:
            return {"error": f"Race the AI has used its ${self.race_meter.cap_usd:g} budget. Raise its cap to keep playing.", **base}
        if self.spent_total() >= self.total_cap:
            return {"error": f"All ${self.total_cap:g} of the model budget is used. Raise the total cap to keep going.", **base}
        if not self.meta_key_file.is_file():
            return {"error": "No Meta key on this Mac, so the AI cannot play. Start the helper with --stand-in to watch a recorded game.", **base}
        m = HttpModel(self.meta_base_url, race.MODEL, key_file=self.meta_key_file, max_tokens=4000, reasoning_effort="low",
                      meter=self.race_meter, timeout=120)
        before = self.race_meter.usd
        try:
            msg = m.chat([{"role": "system", "content": race.SYSTEM}, *messages], tools=race.TOOLS)
        except spend.CapReached:
            return {"error": f"Race the AI has used its ${self.race_meter.cap_usd:g} budget. Raise its cap to keep playing.", **base}
        except Exception as e:  # noqa: BLE001 - the page shows the reason
            return {"error": f"The model did not answer: {e}", **base}
        msg = {k: msg[k] for k in ("role", "content", "tool_calls") if k in msg}
        return {"message": msg, "model": race.MODEL, "cost_usd": round(self.race_meter.usd - before, 6),
                "spent_usd": round(self.race_meter.usd, 6), **base}


    def poster_make(self, body):
        """The three-star poster (docs/POSTER.md): the map's picture in, Muse Image's poster out, saved on this Mac."""
        import base64
        import time
        bad = poster.check(body)
        if bad:
            return bad
        base = {"cap_usd": self.poster_meter.cap_usd}
        title, wafers, stars = poster.clean_title(body.get("title")), body["wafers"], body["stars"]
        folder = self.jobs_dir.parent / "posters"
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{poster.slug(title)}-{wafers}-{int(time.time())}"
        if self.stand_in:
            png, model, cost = (self.stand_in / "poster.png").read_bytes(), "stand-in", 0
        else:
            if self.poster_meter.usd + poster.PRICE_USD > self.poster_meter.cap_usd + 1e-9:
                return {"error": f"Posters have used their ${self.poster_meter.cap_usd:g} budget. Raise their cap to make more.", **base}
            if self.spent_total() + poster.PRICE_USD > self.total_cap + 1e-9:
                return {"error": f"All ${self.total_cap:g} of the model budget is used. Raise the total cap to keep going.", **base}
            if not self.meta_key_file.is_file():
                return {"error": "No Meta key on this Mac, so no poster can be made.", **base}
            from agent.fabgym_agent import _read_secret
            try:
                png = poster.edit(self.meta_base_url, _read_secret(self.meta_key_file, "key"), body["image"], poster.prompt(title, wafers, stars))
            except Exception as e:  # noqa: BLE001 - the page shows the reason
                return {"error": f"Muse Image did not answer: {str(e)[:200]}", **base}
            model, cost = poster.MODEL, self.poster_meter.add_usd(poster.PRICE_USD)
        mime, ext = poster.kind(png)
        dest = folder / f"{stem}.{ext}"
        dest.write_bytes(png)
        return {"image": f"data:{mime};base64," + base64.b64encode(png).decode(), "format": ext, "model": model, "cost_usd": cost, "saved": str(dest),
                "spent_usd": round(self.poster_meter.usd, 4), **base}


    def sketch_read(self, body):
        """Sketch to fab (docs/SKETCH.md): a photo in, Muse Spark's reading out, snapped to the editor's grid."""
        img = body.get("image")
        if not isinstance(img, str) or not re.match(r"data:image/(png|jpeg);base64,", img):
            return {"error": "the sketch must be a PNG or JPEG picture"}
        if len(img) * 3 // 4 > 8 * 1024 * 1024:
            return {"error": "the picture is over 8 MB"}
        base = {"cap_usd": self.sketch_meter.cap_usd}
        if self.stand_in:
            reading, model, cost = json.loads((self.stand_in / "sketch.json").read_text()), "stand-in", 0
        else:
            if self.sketch_meter.usd >= self.sketch_meter.cap_usd:
                return {"error": f"Sketch reading has used its ${self.sketch_meter.cap_usd:g} budget. Raise its cap to read more.", **base}
            if self.spent_total() >= self.total_cap:
                return {"error": f"All ${self.total_cap:g} of the model budget is used. Raise the total cap to keep going.", **base}
            if not self.meta_key_file.is_file():
                return {"error": "No Meta key on this Mac, so no sketch can be read.", **base}
            w, h = int(body.get("width") or 0), int(body.get("height") or 0)
            m = HttpModel(self.meta_base_url, sketch.MODEL, key_file=self.meta_key_file, max_tokens=4000, reasoning_effort="low",
                          meter=self.sketch_meter, timeout=120)
            before = self.sketch_meter.usd
            try:
                text = m.complete([{"role": "user", "content": [{"type": "text", "text": sketch.PROMPT.format(w=w or "?", h=h or "?")},
                                                                 {"type": "image_url", "image_url": {"url": img}}]}])
            except Exception as e:  # noqa: BLE001 - the page shows the reason
                return {"error": f"Muse Spark did not answer: {str(e)[:200]}", **base}
            reading, model, cost = sketch.read(text), sketch.MODEL, round(self.sketch_meter.usd - before, 6)
        return {**sketch.to_fab(reading), "read": {"boxes": len(reading.get("boxes", [])), "lines": len(reading.get("lines", []))},
                "model": model, "cost_usd": cost, "spent_usd": round(self.sketch_meter.usd, 6), **base}


def serve(h, port=8766):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype.endswith("json") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/status":
                return self._send(200, h.status())
            if path == "/api/fab/base":
                q = self.path.split("?", 1)[1] if "?" in self.path else ""
                name = dict(p.split("=", 1) for p in q.split("&") if "=" in p).get("name", "smt2020")
                return self._send(200, h.fab_base(name))
            if path.startswith("/api/job/"):
                parts = path.split("/")
                if len(parts) == 5 and parts[4] == "fab" and re.fullmatch(r"B-\d{4,}", parts[3]):
                    f = h.runs_dir / parts[3] / "fab.txt"
                    return self._send(200, f.read_text(), "text/plain") if f.is_file() else self._send(404, {"error": "no such run"})
                if len(parts) == 6 and parts[4] == "arm" and parts[5].isdigit():
                    t = h.arm_shop(parts[3], int(parts[5]))
                    return self._send(200, t, "text/plain") if t else self._send(404, {"error": "no such arm"})
                q = self.path.split("?", 1)[1] if "?" in self.path else ""
                since = dict(x.split("=", 1) for x in q.split("&") if "=" in x).get("since")
                j = h.job(parts[3], int(since) if since and since.isdigit() else None)
                return self._send(200, j) if j else self._send(404, {"error": "no such run"})
            if path == "/api/runs":
                return self._send(200, h.runs())
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (h.web / rel).resolve()
            if h.web not in f.parents and f != h.web or not f.is_file():
                return self._send(404, {"error": "not found"})
            return self._send(200, f.read_bytes(), mimetypes.guess_type(str(f))[0] or "application/octet-stream")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "not JSON"})
            if self.path == "/api/ask":
                r = h.ask(body.get("question"))
            elif self.path == "/api/run":
                r = h.run_text(body.get("scenario"))
            elif self.path == "/api/sign":
                r = h.sign(str(body.get("job", "")), body.get("name"))
            elif self.path == "/api/fab/check":
                r = h.fab_check(body.get("fab") or "")
            elif self.path == "/api/fab/run":
                r = h.fab_run(body.get("fab") or "", seed=int(body.get("seed", 1)), days=float(body.get("days", 2)),
                              every=float(body.get("every", 60)), overrides=body.get("overrides"), record=body.get("record"))
            elif self.path == "/api/runs/record":
                r = h.record_run(body)
            elif self.path == "/api/sketch":
                r = h.sketch_read(body)
            elif self.path == "/api/poster":
                r = h.poster_make(body)
            elif self.path == "/api/race/step":
                r = h.race_step(body)
            elif self.path == "/api/fab/replay":
                r = h.fab_replay(body.get("fab") or "", seed=int(body.get("seed", 1)), start=float(body.get("start", 0)),
                                 minutes=float(body.get("minutes", 30)), overrides=body.get("overrides"))
            else:
                return self._send(404, {"error": "not found"})
            return self._send(409 if r.get("busy") else 200, r)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    a = argparse.ArgumentParser(description="The floor page's ask box, on this Mac (127.0.0.1 only).")
    a.add_argument("--port", type=int, default=8766)
    a.add_argument("--smt2020", default=str(ROOT / "data" / "smt2020" / "hvlm"))
    a.add_argument("--quick", action="store_true", help="smoke runs: 3 seeds, short windows (not for results)")
    a.add_argument("--preset", choices=sorted(PRESETS), default="meta",
                   help="meta: muse-spark-1.3-contributor at low effort (ideas, trials); open: Muse Spark Open on Baseten (submission runs)")
    a.add_argument("--spend-cap", type=float, default=SPEND_CAP, help="stop asking the model once this many dollars are spent")
    a.add_argument("--stand-in", help="answer Meta's models from recorded replies in this folder (tests, no key); spends nothing")
    a.add_argument("--runs", default=str(ROOT / "data" / "ask" / "runs"), help="where numbered runs are kept (docs/RUNS.md)")
    a.add_argument("--threads", type=int, default=4, help="cores the simulator uses for a question (at most 4)")
    a.add_argument("--no-model", action="store_true", help="reach no paid model (tests): examples, hand-written setups and --stand-in only")
    o = a.parse_args()
    h = Helper(smt2020=o.smt2020, quick=o.quick, preset=o.preset, spend_cap=o.spend_cap, stand_in=o.stand_in, runs=o.runs,
               threads=max(1, min(4, o.threads)), no_model=o.no_model)
    srv = serve(h, o.port)
    state = f"{h.model_name} on {h.provider_label}" if h.model_connected() else "not connected: examples and hand-written scenarios only"
    s = h.meter.summary()
    print(f"Fab Gym on http://127.0.0.1:{o.port}  (model {state}; spent ${s['usd']:.4f} of ${s['cap_usd']:g} in {s['calls']} calls)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
