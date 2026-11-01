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


if __name__ == "__main__":
    unittest.main()
