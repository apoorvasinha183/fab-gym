"""Runs you can watch and find again (docs/RUNS.md, part 1: RN2 to RN4). Written before the code. The helper runs the
simulator in its short smoke mode; nothing is spent. On a teaching fab of our own and the SMT2020 testbed; not a real
fab."""

import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agent import helper

ROOT = Path(__file__).resolve().parents[2]
SMT = ROOT / "data" / "smt2020" / "hvlm"
FABSIM = ROOT / "target" / "release" / "fabsim"
ONE = "fabgym-scenario 1\nquestion\tIs first come, first served better today?\ncandidate\tfifo\trule\tfifo\n"
TWO = "fabgym-scenario 1\nquestion\tPrototypes doubled: first in line?\nfamily\tshare\t2\tsaid\ncandidate\tfirst\tpolicy\tbfirst\n"
COPIES = "fabgym-scenario 1\nquestion\tPrototypes doubled: copies in the halls?\nfamily\tshare\t2\tsaid\ncandidate\tcopies\tfloor\tcopies\n"


@unittest.skipUnless(SMT.exists() and FABSIM.exists(), "needs the SMT2020 files and a release build")
class Runs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.servers = []
        self.port = self.start()

    def tearDown(self):
        for s in self.servers:
            s.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self):
        """A helper on the test's folders; a second call is a restart on the same folders."""
        h = helper.Helper(web=ROOT / "web", fabsim=FABSIM, smt2020=SMT, key_file=self.tmp / "missing.key",
                          jobs=self.tmp / "jobs", runs=self.tmp / "runs", quick=True)
        s = helper.serve(h, port=0)
        self.servers.append(s)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        return s.server_address[1]

    def call(self, path, body=None, port=None):
        url = f"http://127.0.0.1:{port or self.port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode() or "{}")

    def raw(self, path, port=None):
        with urllib.request.urlopen(f"http://127.0.0.1:{port or self.port}{path}", timeout=30) as r:
            return r.read().decode()

    def run_text(self, text, port=None):
        code, j = self.call("/api/run", {"scenario": text}, port)
        self.assertEqual(code, 200, j)
        rid = j["job"]
        t0 = time.time()
        while time.time() - t0 < 600:
            _, j = self.call(f"/api/job/{rid}", port=port)
            if j["stage"] in ("done", "failed"):
                self.assertEqual(j["stage"], "done", j.get("error"))
                return rid, j
            time.sleep(0.5)
        self.fail("the run did not finish")

    def test_rn2_numbers_are_permanent_and_never_reused(self):
        a, _ = self.run_text(ONE)
        b, _ = self.run_text(ONE)
        self.assertEqual((a, b), ("Q-0001", "Q-0002"))
        first = (self.tmp / "runs" / "Q-0001" / "report.json").read_bytes()
        # a restart on the same folders goes on from the runs on disk
        port2 = self.start()
        c, _ = self.run_text(ONE, port2)
        self.assertEqual(c, "Q-0003")
        self.assertEqual((self.tmp / "runs" / "Q-0001" / "report.json").read_bytes(), first, "Q-0001 is never written again")
        for r in ("Q-0001", "Q-0002", "Q-0003"):
            d = self.tmp / "runs" / r
            for f in ("scenario.txt", "log.jsonl", "report.json", "run.json"):
                self.assertTrue((d / f).is_file(), f"{r}/{f}")

    def test_rn3_the_log_is_kept_and_served_from_any_point(self):
        rid, j = self.run_text(TWO)
        lines = [json.loads(x) for x in (self.tmp / "runs" / rid / "log.jsonl").read_text().splitlines()]
        kinds = [e["e"] for e in lines]
        self.assertEqual(kinds[0], "start")
        self.assertEqual(kinds[-1], "end")
        self.assertIn("floor", kinds)
        self.assertEqual(kinds.count("run"), lines[0]["runs"])
        for e in lines:
            self.assertIsInstance(e["t"], (int, float), "each event has its seconds since the start")
        ts = [e["t"] for e in lines]
        self.assertEqual(ts, sorted(ts))
        self.assertEqual(j["runs_done"], j["runs_total"])
        self.assertEqual(j["runs_total"], lines[0]["runs"])
        self.assertEqual(len(j["events"]), len(lines), "the whole log without since")
        _, part = self.call(f"/api/job/{rid}?since=3")
        self.assertEqual(part["events"], j["events"][3:], "only the events after the third")
        self.assertEqual(part["since"], 3)

    def test_rn4_the_list_reads_the_runs_on_disk(self):
        a, _ = self.run_text(ONE)
        b, _ = self.run_text(TWO)
        _, lst = self.call("/api/runs")
        rows = lst["runs"]
        self.assertEqual([r["id"] for r in rows], [b, a], "newest first")
        for r in rows:
            for k in ("id", "kind", "question", "started", "status", "runs_done", "runs_total", "leader"):
                self.assertIn(k, r)
            self.assertEqual(r["kind"], "question")
            self.assertEqual(r["status"], "done")
        self.assertEqual(rows[0]["question"], "Prototypes doubled: first in line?")
        # after a restart the list is the same
        port2 = self.start()
        _, again = self.call("/api/runs", port=port2)
        self.assertEqual([r["id"] for r in again["runs"]], [b, a])
        _, j = self.call(f"/api/job/{a}", port=port2)
        self.assertEqual(j["stage"], "done", "a finished run opens after a restart")
        self.assertIsNotNone(j["report"])


    def test_rn10_setups_carry_their_plan_and_file(self):
        """docs/RUNS.md, part 2: each setup's floor as a plan, and every setup's fab file, for one family too."""
        rid, j = self.run_text(COPIES)
        arms = j["report"]["arms"]
        self.assertEqual([a["name"] for a in arms], ["today", "copies"])
        for a in arms:
            plan = a["plan"]
            self.assertTrue(plan["phases"], f"{a['name']}: the phases' lengths")
            self.assertTrue(plan["groups"], f"{a['name']}: the placed groups")
            for g in plan["groups"]:
                for k in ("g", "phase", "side", "bay", "x", "y", "tools"):
                    self.assertIn(k, g)
            places = {l.split("\t")[1] for l in self.raw(a["shop_url"]).splitlines() if l.startswith("place\t") and len(l.split("\t")) == 7}
            self.assertEqual({g["g"] for g in plan["groups"]}, places, f"{a['name']}: the plan is the file's places")
        today, cp = arms[0]["plan"], arms[1]["plan"]
        self.assertEqual((today["copies"], today["moved"]), ([], []), "today is today")
        self.assertTrue(cp["copies"] and all(c.endswith("@B") for c in cp["copies"]), cp["copies"])
        self.assertTrue(set(cp["copies"]) <= {g["g"] for g in cp["groups"]})
        was = {g["g"]: (g["phase"], g["side"], g["bay"]) for g in today["groups"]}
        moved = sorted(g["g"] for g in cp["groups"] if g["g"] in was and was[g["g"]] != (g["phase"], g["side"], g["bay"]))
        self.assertEqual(sorted(cp["moved"]), moved, "moved: the groups standing elsewhere than in today's floor")
        # one family: a file for every setup, its rule in it, and no plan
        rid2, j2 = self.run_text(ONE)
        arms2 = j2["report"]["arms"]
        self.assertEqual([a["name"] for a in arms2], ["today", "fifo"])
        for a in arms2:
            self.assertIsNone(a["plan"])
        self.assertIn("dispatch\tfifo", self.raw(arms2[1]["shop_url"]).splitlines())


    # ------------------------------------------------------------------ part 3 (docs/RUNS.md): every kind of run

    def record(self, body, port=None):
        code, j = self.call("/api/runs/record", body, port)
        self.assertEqual(code, 200, j)
        return j["id"]

    def test_rn14_settings_and_floor_runs_are_numbered_and_listed(self):
        rows = [{"arm": a, "seed": s, "values": {"wafers_out": v, "moves": 10 * v}} for a, s, v in
                (("today", 100, 900), ("change", 100, 860), ("today", 101, 910), ("change", 101, 850))]
        S = {"kind": "settings", "title": "Simulation settings: breakdowns ×2", "settings": [["Change", "breakdowns ×2"]],
             "seeds": [100, 101], "arms": ["today", "change"], "measure": "wafers_out", "runs": rows,
             "summary": {"columns": ["Measure", "Today's fab", "Change", "95% interval", "Verdict"], "rows": [["Wafers out", "905", "−50", "−90 to −10", "worse"]]},
             "link": "index.html#floor"}
        F = {"kind": "floor", "key": "floor|shop|7|3", "title": "Today's fab, run #7", "link": "index.html?run=7#floor",
             "summary": {"rows": [["Lots finished", "40"]]}}
        self.assertEqual(self.record(S), "S-0001")
        self.assertEqual(self.record(S), "S-0002", "a comparison with no key is a new run")
        self.assertEqual(self.record(F), "F-0001")
        self.assertEqual(self.record(F), "F-0001", "the same run sent again keeps its number")
        port2 = self.start()
        self.assertEqual(self.record(S, port2), "S-0003", "numbers go on after a restart")
        q, _ = self.run_text(ONE, port2)
        self.assertEqual(q, "Q-0001", "the questions' numbers are their own")
        _, lst = self.call("/api/runs", port=port2)
        kinds = {r["id"]: r["kind"] for r in lst["runs"]}
        self.assertEqual(kinds, {"S-0001": "settings", "S-0002": "settings", "S-0003": "settings", "F-0001": "floor", "Q-0001": "question"})
        titles = {r["id"]: r["title"] for r in lst["runs"]}
        self.assertEqual(titles["F-0001"], "Today's fab, run #7")
        _, j = self.call("/api/job/S-0001", port=port2)
        self.assertEqual((j["kind"], j["stage"]), ("settings", "done"))
        self.assertEqual(j["record"]["settings"], S["settings"])
        runs = [e for e in j["events"] if e["e"] == "run"]
        self.assertEqual([(e["arm"], e["seed"], e["value"]) for e in runs], [(r["arm"], r["seed"], r["values"]["wafers_out"]) for r in rows])
        self.assertEqual(j["events"][0]["e"], "start")

    def test_rn15_build_runs_keep_their_layout(self):
        import subprocess
        made = subprocess.run(["node", "-e", 'const E=require("./web/editor-core.js"); const st={...E.template("teaching"),inports:2};'
                               'process.stdout.write(JSON.stringify({fab: E.fabText(E.TEACHING_SHOP, st, {vehicles: st.vehicles}), state: st}))'],
                              cwd=ROOT, capture_output=True, text=True, check=True)
        got = json.loads(made.stdout)
        body = {"fab": got["fab"], "seed": 1, "days": 1, "every": 60, "record": {"title": "Free build", "state": got["state"], "template": "teaching", "challenge": None}}
        code, r = self.call("/api/fab/run", body)
        self.assertEqual(code, 200, r)
        self.assertEqual(r["run"], "B-0001")
        d = self.tmp / "runs" / "B-0001"
        self.assertEqual((d / "fab.txt").read_text(), got["fab"])
        self.assertEqual(json.loads((d / "state.json").read_text()), got["state"])
        _, again = self.call("/api/fab/run", body)
        self.assertEqual(again["run"], "B-0001", "the same layout on the same random run is the same run")
        _, other = self.call("/api/fab/run", {**body, "seed": 2})
        self.assertEqual(other["run"], "B-0002")
        _, j = self.call("/api/job/B-0001")
        self.assertEqual(j["kind"], "build")
        self.assertEqual(j["record"]["score"]["wafers_per_day"], r["moods"]["score"]["wafers_per_day"])
        self.assertEqual(j["record"]["state"], got["state"])
        self.assertEqual(self.raw(j["record"]["fab_url"]), got["fab"])
        _, plain = self.call("/api/fab/run", {k: v for k, v in body.items() if k != "record"})
        self.assertNotIn("run", plain, "a run asked for without record is not kept")


if __name__ == "__main__":
    unittest.main()
