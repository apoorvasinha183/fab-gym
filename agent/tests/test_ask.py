"""Ask the fab, with two families (docs/ASK-FAMILIES.md, parts 3 and 4). Written before the code.
Run: python3 -m unittest agent.tests.test_ask  (from the repo root).

From the SMT2020 testbed, a published set of a fab's tool groups, routes and times; not a real fab, not real data."""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agent import ask, helper

ROOT = Path(__file__).resolve().parents[2]
SMT = ROOT / "data" / "smt2020" / "hvlm"
FABSIM = ROOT / "target" / "release" / "fabsim"
GROUPS = ask.load_groups(ROOT / "web" / "data" / "areas.tsv")


def good():
    return {
        "question": "Prototype orders double. A wing, or first in line?",
        "family": {"share": 2, "said": True},
        "shocks": [{"kind": "breakdowns", "value": 1.5, "said": False, "range": [1.0, 2.0]}],
        "candidates": [
            {"name": "wing", "floor": "wing"},
            {"name": "first", "policy": "bfirst"},
            {"name": "copies-capped", "floor": "copies", "policy": "cap"},
        ],
    }


class Checker(unittest.TestCase):
    def test_groups_are_read(self):
        self.assertGreater(len(GROUPS), 100)
        self.assertIn("Planar_FE_79", GROUPS)

    def test_a_good_answer_passes_and_becomes_text(self):
        a = good()
        self.assertEqual(ask.check(a, GROUPS), [])
        text = ask.to_scenario(a)
        self.assertEqual(
            text,
            "fabgym-scenario 1\n"
            "question\tPrototype orders double. A wing, or first in line?\n"
            "family\tshare\t2\tsaid\n"
            "shock\tbreakdowns\t1.5\tassumed\n"
            "candidate\twing\tfloor\twing\n"
            "candidate\tfirst\tpolicy\tbfirst\n"
            "candidate\tcopies-capped\tfloor\tcopies\n"
            "candidate\tcopies-capped\tpolicy\tcap\n",
        )

    def test_each_fault_is_refused_with_a_reason(self):
        faults = []
        a = good(); a["shocks"][0]["kind"] = "earthquake"; faults.append(a)
        a = good(); a["shocks"] = [{"kind": "outage", "group": "Nowhere_9", "from_hours": 30, "hours": 8, "said": True}]; faults.append(a)
        a = good(); a["shocks"][0]["value"] = 50; faults.append(a)
        a = good(); del a["shocks"][0]["range"]; faults.append(a)  # assumed without a range
        a = good(); a["shocks"][0]["range"] = [2.0, 3.0]; faults.append(a)  # range does not hold the value
        a = good(); a["candidates"] = [{"name": f"c{i}", "policy": "cap"} for i in range(7)]; faults.append(a)
        a = good(); del a["family"]; faults.append(a)  # floor or policy without family
        a = good(); a["family"]["share"] = 40; faults.append(a)
        a = good(); a["candidates"][1]["rule"] = "fifo"; faults.append(a)  # B first with another rule
        a = good(); a["candidates"][0]["floor"] = "basement"; faults.append(a)
        a = good(); a["candidates"][0]["teleport"] = True; faults.append(a)  # unknown key
        a = good(); a["candidates"][1]["name"] = "wing"; faults.append(a)  # two candidates, one name
        a = good(); a["candidates"][0]["spare"] = [["Nowhere_9", 1]]; faults.append(a)
        for i, f in enumerate(faults):
            with self.subTest(fault=i):
                reasons = ask.check(f, GROUPS)
                self.assertTrue(reasons, f"fault {i} passed")
                self.assertTrue(all(isinstance(r, str) and r for r in reasons))

    def test_model_replies_are_read_with_or_without_fences(self):
        a = good()
        for reply in (json.dumps(a), "```json\n" + json.dumps(a) + "\n```", "Here it is:\n```\n" + json.dumps(a) + "\n```"):
            self.assertEqual(ask.read_reply(reply), a)
        with self.assertRaises(ValueError):
            ask.read_reply("I think you should buy more tools.")

    def test_examples_are_marked_and_valid(self):
        ex = ask.examples()
        self.assertGreaterEqual(len(ex), 3)
        for e in ex:
            self.assertIs(e["example"], True)
            self.assertEqual(ask.check(e["answer"], GROUPS), [], e["question"])
            text = ask.to_scenario(e["answer"])
            self.assertTrue(text.startswith("fabgym-scenario 1\nquestion\t"))
        self.assertTrue(any("family" in e["answer"] for e in ex))
        self.assertTrue(any("family" not in e["answer"] for e in ex))

    def test_the_prompt_says_what_it_must(self):
        p = ask.prompt(GROUPS)
        for must in ("SMT2020", "not a real fab", "said", "assumed", "range", "bfirst", "wing", "Planar_FE_79", "JSON"):
            self.assertIn(must, p)


SECRET = "sk-test-0123456789-never-show"


class Helper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.key = cls.tmp / "baseten.key"
        cls.h = helper.Helper(web=ROOT / "web", fabsim=FABSIM, smt2020=SMT, key_file=cls.tmp / "missing.key",
                              jobs=cls.tmp / "jobs", quick=True)
        cls.server = helper.serve(cls.h, port=0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def call(self, path, body=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def wait(self, job, limit=600):
        t0 = time.time()
        while time.time() - t0 < limit:
            code, body = self.call(f"/api/job/{job}")
            j = json.loads(body)
            if j["stage"] in ("done", "failed"):
                return j
            time.sleep(0.5)
        self.fail("the job did not finish")

    def test_serves_the_page_on_localhost_only(self):
        code, body = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn("Fab Gym", body)
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_without_a_key_an_example_answers_and_others_are_told(self):
        code, body = self.call("/api/status")
        st = json.loads(body)
        self.assertFalse(st["model_connected"])
        self.assertGreaterEqual(len(st["examples"]), 3)
        code, body = self.call("/api/ask", {"question": "Will it rain on the fab?"})
        j = json.loads(body)
        self.assertTrue(j["no_model"])
        self.assertIn("examples", j)

    def test_the_key_never_reaches_the_page(self):
        self.key.write_text(SECRET)
        h = helper.Helper(web=ROOT / "web", fabsim=FABSIM, smt2020=SMT, key_file=self.key, jobs=self.tmp / "jobs2", quick=True)
        st = h.status()
        self.assertTrue(st["model_connected"])
        self.assertNotIn(SECRET, json.dumps(st))
        self.assertNotIn(SECRET, repr(h))

    def test_a_refused_scenario_runs_nothing(self):
        code, body = self.call("/api/run", {"scenario": "fabgym-scenario 1\nquestion\tq\ncandidate\tc\tfloor\twing\n"})
        j = self.wait(json.loads(body)["job"])
        self.assertEqual(j["stage"], "failed")
        self.assertIn("family", j["error"])
        self.assertIsNone(j.get("report"))

    @unittest.skipUnless(SMT.exists() and FABSIM.exists(), "needs the SMT2020 files and a release build")
    def test_an_example_runs_end_to_end(self):
        ex = [e for e in ask.examples() if "family" not in e["answer"]][0]
        code, body = self.call("/api/ask", {"question": ex["question"]})
        j = self.wait(json.loads(body)["job"])
        self.assertEqual(j["stage"], "done", j.get("error"))
        self.assertEqual(j["answer_source"], "example")
        self.assertIn("Real-fab effect", json.dumps(j["report"]))
        self.assertEqual(len(j["report"]["candidates"]), len(ex["answer"]["candidates"]))

    @unittest.skipUnless(SMT.exists() and FABSIM.exists(), "needs the SMT2020 files and a release build")
    def test_a_hand_written_two_family_scenario_runs_with_arms(self):
        text = "fabgym-scenario 1\nquestion\tq\nfamily\tshare\t2\tsaid\ncandidate\tfirst\tpolicy\tbfirst\n"
        code, body = self.call("/api/run", {"scenario": text})
        j = self.wait(json.loads(body)["job"])
        self.assertEqual(j["stage"], "done", j.get("error"))
        self.assertEqual(j["answer_source"], "hand")
        self.assertTrue(j["report"]["families"])
        self.assertEqual([a["name"] for a in j["report"]["arms"]], ["today", "first"])


if __name__ == "__main__":
    unittest.main()
