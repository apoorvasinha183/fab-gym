"""The map editor's helper endpoints (docs/EDITOR.md): the base shop, the checks and a run with moods, all from the
real simulator. Written before the code. Run: python3 -m unittest agent.tests.test_editor (from the repo root).
From the SMT2020 testbed and a small fab of our own; not a real fab."""

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from agent import helper

ROOT = Path(__file__).resolve().parents[2]
FABSIM = ROOT / "target" / "release" / "fabsim"

OWN = """fabgym-shop 1
transport\t0.0\t0.0
fleet\t6\t3.0\t1.0\t2\t60.0\tnearest
group\tA\t1\t0.0\t0.0\t-\t-\t-
group\tB\t1\t0.0\t0.0\t-\t-\t-
route\tr
step\tA\tlot\t5.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t5.0\t0.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t1.0\t15.0\t0.0\t-\tL
node\te\t0.0\t0.0
node\ta\t10.0\t0.0
node\tb\t30.0\t0.0
node\tx\t40.0\t0.0
node\tv\t0.0\t10.0
link\te\ta\t10.0
link\ta\tb\t20.0
link\tb\tx\t10.0
link\tx\tv\t41.3
link\tv\te\t10.0
stop\tA\t0\ta
stop\tB\t0\tb
entry\te
exit\tx
"""


@unittest.skipUnless(FABSIM.exists(), "needs cargo build --release")
class Editor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        key = self.tmp / "none.key"
        self.h = helper.Helper(web=ROOT / "web", key_file=key, jobs=self.tmp / "jobs", quick=True)

    def test_a_good_fab_passes_and_a_bad_one_is_named(self):
        ok = self.h.fab_check(OWN)
        self.assertTrue(ok["ok"])
        self.assertEqual([i for i in ok["issues"] if i["severity"] == "error"], [])
        bad = self.h.fab_check(OWN.replace("exit\tx\n", ""))
        self.assertFalse(bad["ok"])
        self.assertIn("no_exit", [i["code"] for i in bad["issues"]])

    def test_a_run_gives_moods_frames(self):
        r = self.h.fab_run(OWN, seed=1, days=0.5, every=60)
        self.assertNotIn("error", r)
        self.assertEqual(len(r["moods"]["frames"]), 13)
        self.assertEqual(r["moods"]["tools"], ["A#1", "B#1"])
        self.assertIn("checks", r)

    def test_a_fab_with_errors_is_not_run(self):
        r = self.h.fab_run(OWN.replace("exit\tx\n", ""), seed=1, days=0.5, every=60)
        self.assertIn("error", r)
        self.assertNotIn("moods", r)

    def test_text_that_is_not_a_fab_is_refused_plainly(self):
        r = self.h.fab_check("hello")
        self.assertFalse(r["ok"])
        self.assertIn("error", r)

    @unittest.skipUnless((ROOT / "web" / "data" / "shop.txt").exists(), "needs web/build.sh")
    def test_the_base_shop_is_served(self):
        b = self.h.fab_base("smt2020")
        self.assertTrue(b["shop"].startswith("fabgym-shop 1"))
        self.assertIn("Delay_32", b["areas"])

    def test_the_endpoints_answer_over_http(self):
        srv = helper.serve(self.h, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/fab/check", data=json.dumps({"fab": OWN}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.assertTrue(json.loads(r.read())["ok"])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/editor.html", timeout=10) as r:
            self.assertIn("Fab Gym", r.read().decode())


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(FABSIM.exists(), "needs cargo build --release")
class TakeTwo(unittest.TestCase):
    """Editor take two (docs/EDITOR-TAKE-TWO.md): runs take an overrides file, and a replay window comes back."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.h = helper.Helper(web=ROOT / "web", key_file=self.tmp / "none.key", jobs=self.tmp / "jobs", quick=True)

    def test_a_run_takes_an_overrides_file(self):
        ov = {"fabgym-overrides": 1, "groups": {"A": {"breakdowns": {"kind": "random", "mttf_minutes": 30, "mttr_minutes": 30}}}}
        plain = self.h.fab_run(OWN, seed=1, days=0.5, every=60)
        broken = self.h.fab_run(OWN, seed=1, days=0.5, every=60, overrides=ov)
        self.assertNotIn("error", broken)
        self.assertLess(broken["moods"]["score"]["wafers_per_day"], plain["moods"]["score"]["wafers_per_day"])

    def test_a_bad_overrides_file_is_refused_plainly(self):
        r = self.h.fab_run(OWN, seed=1, days=0.5, every=60, overrides={"fabgym-overrides": 1, "groups": {"Nope": {}}})
        self.assertIn("error", r)
        self.assertIn("Nope", r["error"])

    def test_a_replay_window_comes_back(self):
        r = self.h.fab_replay(OWN, seed=1, start=300, minutes=15)
        self.assertNotIn("error", r)
        self.assertTrue(r["stays"])
        self.assertEqual(r["fields"][:3], ["vehicle", "from", "to"])
