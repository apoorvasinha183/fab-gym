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
import itertools
import json
import mimetypes
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent import ask, spend
from agent.fabgym_agent import DEFAULT_KEY, HttpModel

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
SPEND_CAP = 5.0  # dollars, assumed
QUICK = ["--seeds", "0..2", "--warmup", "1", "--window", "2", "--layout-iters", "300"]


class Helper:
    def __init__(self, web=ROOT / "web", fabsim=ROOT / "target" / "release" / "fabsim", smt2020=ROOT / "data" / "smt2020" / "hvlm",
                 key_file=None, jobs=ROOT / "data" / "ask" / "jobs", quick=False, base_url=None, model=None, threads=4,
                 preset="meta", spend_cap=SPEND_CAP):
        p = PRESETS[preset]
        self.preset = preset
        self.provider = p["provider"]
        self.provider_label = p["label"]
        self.web = Path(web).resolve()
        self.fabsim = Path(fabsim)
        self.smt2020 = Path(smt2020)
        self.key_file = Path(key_file if key_file is not None else p["key_file"]).expanduser()
        self.jobs_dir = Path(jobs)
        self.quick = quick
        self.base_url = base_url or p["base_url"]
        self.model_name = model or p["model"]
        self.reasoning_effort = p["reasoning_effort"]
        self.meter = spend.Meter(spend.price(self.provider, self.model_name), cap_usd=spend_cap,
                                 path=self.jobs_dir.parent / "spend.json")
        self.threads = threads
        self.groups = ask.load_groups(self.web / "data" / "areas.tsv")
        self.jobs = {}
        self.lock = threading.Lock()
        self.fab_lock = threading.Lock()
        self.ids = itertools.count(1)

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

    def _start(self, job, work):
        with self.lock:
            if self.busy():
                return {"error": "One question runs at a time; wait for the one running now.", "busy": True}
            jid = str(next(self.ids))
            job.update({"id": jid, "stage": "queued", "started": time.time(), "report": None, "error": None})
            self.jobs[jid] = job
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
        return self._start({"question": None, "answer_source": "hand", "answer": None, "scenario": text}, "text")

    def _run(self, jid, work):
        job = self.jobs[jid]
        try:
            if work == "model":
                job["stage"] = "asking the model"
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
            job["report"] = self._score(jid, job["scenario"])
            job["stage"] = "done"
        except Exception as e:  # shown to the person; never holds the key
            job["error"] = str(e)
            job["stage"] = "failed"
        job["seconds"] = round(time.time() - job["started"], 1)

    def _score(self, jid, text):
        d = self.jobs_dir / jid
        d.mkdir(parents=True, exist_ok=True)
        f = d / "scenario.txt"
        f.write_text(text)
        cmd = ["nice", "-n", "10", str(self.fabsim), "score", str(f), str(self.smt2020), "--threads", str(self.threads),
               "--layout-cache", str(ROOT / "data" / "ask" / "layouts")]
        if self.quick:
            cmd += QUICK
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            msg = (p.stderr.strip().splitlines() or ["the simulator stopped"])[-1]
            raise ValueError(msg.removeprefix("refused: "))
        (d / "report.json").write_text(p.stdout)
        return json.loads(p.stdout)

    def job(self, jid):
        j = self.jobs.get(jid)
        if j is None:
            return None
        out = {k: v for k, v in j.items() if k != "report"}
        out["elapsed"] = round(time.time() - j["started"], 1)
        rep = j.get("report")
        if rep is not None:
            rep = dict(rep)
            rep["arms"] = [{k: v for k, v in a.items() if k != "shop"} | {"shop_url": f"/api/job/{jid}/arm/{i}"}
                           for i, a in enumerate(rep.get("arms", []))]
        out["report"] = rep
        return out

    # ------------------------------------------------------------------ signing (docs/FLOOR-UI.md)

    @staticmethod
    def _hashes(job):
        return {k: hashlib.sha256(v.encode()).hexdigest() for k, v in (
            ("question", job.get("question") or ""), ("scenario", job.get("scenario") or ""),
            ("report", json.dumps(job.get("report"), sort_keys=True)))}

    def sign(self, jid, name):
        """A person signs a finished answer: their name, the time and SHA-256 of question, scenario and report."""
        j = self.jobs.get(jid)
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
        d = self.jobs_dir / jid; d.mkdir(parents=True, exist_ok=True)
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
        f.write_text(text)
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

    def fab_run(self, text, seed=1, days=2.0, every=60.0, overrides=None):
        """The checks, then, with no errors, a run's moods (`fabsim moods`), niced, one at a time."""
        r, err = self._fab_cmd(text, overrides, ["moods", str(seed), "--until", str(days * 1440.0), "--every", str(every)])
        if err:
            return err
        return {"moods": r[0], "checks": r[1], "seconds": r[2]}

    def fab_replay(self, text, seed=1, start=0.0, minutes=30.0, overrides=None):
        """Every vehicle's stays on the rail between START and START+MINUTES (`fabsim replay`), for the page to draw."""
        r, err = self._fab_cmd(text, overrides, ["replay", str(seed), "--from", str(start), "--to", str(start + minutes)])
        if err:
            return err
        return {**r[0], "seconds": r[2]}

    def arm_shop(self, jid, k):
        j = self.jobs.get(jid)
        arms = (j or {}).get("report", {}) or {}
        arms = arms.get("arms", [])
        return arms[k]["shop"] if 0 <= k < len(arms) else None


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
                if len(parts) == 6 and parts[4] == "arm" and parts[5].isdigit():
                    t = h.arm_shop(parts[3], int(parts[5]))
                    return self._send(200, t, "text/plain") if t else self._send(404, {"error": "no such arm"})
                j = h.job(parts[3])
                return self._send(200, j) if j else self._send(404, {"error": "no such job"})
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
                              every=float(body.get("every", 60)), overrides=body.get("overrides"))
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
    o = a.parse_args()
    h = Helper(smt2020=o.smt2020, quick=o.quick, preset=o.preset, spend_cap=o.spend_cap)
    srv = serve(h, o.port)
    state = f"{h.model_name} on {h.provider_label}" if h.model_connected() else "not connected: examples and hand-written scenarios only"
    s = h.meter.summary()
    print(f"Fab Gym on http://127.0.0.1:{o.port}  (model {state}; spent ${s['usd']:.4f} of ${s['cap_usd']:g} in {s['calls']} calls)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
