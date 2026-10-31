"""Signing an answer (docs/FLOOR-UI.md, test 8). Written before the code.
Run: python3 -m unittest agent.tests.test_sign  (from the repo root).

From the SMT2020 testbed, a published set of a fab's tool groups, routes and times; not a real fab."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent import helper

ROOT = Path(__file__).resolve().parents[2]


class Sign(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.h = helper.Helper(web=ROOT / "web", key_file=self.tmp / "none.key", jobs=self.tmp / "jobs", runs=self.tmp / "runs", quick=True)
        # a finished job, as the helper keeps it
        self.h.jobs["7"] = {"id": "7", "stage": "done", "question": "Own wing, or first in line?", "scenario": "fabgym-scenario 1\nquestion\tq\n",
                            "report": {"best": None, "real_fab": "Real-fab effect: cannot say"}, "started": 0.0}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_signature_holds_the_name_the_time_and_the_hashes(self):
        r = self.h.sign("7", "Operations head")
        self.assertTrue(r["signed"])
        card = r["card"]
        self.assertEqual(card["name"], "Operations head")
        self.assertIn("at", card)
        want = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in (
            ("question", "Own wing, or first in line?"), ("scenario", "fabgym-scenario 1\nquestion\tq\n"),
            ("report", json.dumps(self.h.jobs["7"]["report"], sort_keys=True)))}
        self.assertEqual(card["sha256"], want)
        self.assertTrue((self.tmp / "jobs" / "7" / "signed.json").exists())
        self.assertTrue(self.h.verify("7"))

    def test_signing_twice_or_unfinished_or_nameless_is_refused(self):
        self.h.sign("7", "Operations head")
        self.assertFalse(self.h.sign("7", "Someone else")["signed"])
        self.h.jobs["8"] = {"id": "8", "stage": "laying out and simulating", "question": "q", "scenario": "s", "report": None, "started": 0.0}
        self.assertFalse(self.h.sign("8", "Operations head")["signed"])
        self.h.jobs["9"] = dict(self.h.jobs["7"], id="9")
        self.assertFalse(self.h.sign("9", "   ")["signed"])
        self.assertFalse(self.h.sign("nope", "Operations head")["signed"])

    def test_a_changed_report_no_longer_matches(self):
        self.h.sign("7", "Operations head")
        self.h.jobs["7"]["report"]["best"] = "own-wing"
        self.assertFalse(self.h.verify("7"))


if __name__ == "__main__":
    unittest.main()
