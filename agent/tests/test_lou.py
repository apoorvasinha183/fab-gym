"""Lou's Meta brain (docs/FAB-3D.md, F11). Written before the code. Every test uses a recorded stand-in for Muse Spark
Open, so no test calls a network. From the SMT2020 testbed; not a real fab."""

import json
import tempfile
import unittest
from pathlib import Path

from agent import helper, lou

ROOT = Path(__file__).resolve().parents[2]
CAMPUS = ROOT / "web/data/building.json"
FABSIM = ROOT / "target/release/fabsim"


def fake_facts():
    return {"clock": "13:20", "wafers_per_day": 1263.4, "cycle_days": 60.5,
            "longest": [{"group": "Planar_FE_79", "area": "Planar", "area_name": "Polishing", "waiting": 37, "working": 4, "idle": 0, "down": 1},
                        {"group": "Litho_FE_111", "area": "Litho", "area_name": "Lithography", "waiting": 12, "working": 6, "idle": 1, "down": 0}],
            "here": {"area": "Planar", "area_name": "Polishing", "groups": [{"group": "Planar_FE_79", "waiting": 37}]},
            "areas": {"Planar": "Polishing", "Litho": "Lithography"},
            "terms": ["cycle time", "queue-time limit"]}


class Check(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()
        self.ctx = lou.Context(areas=self.f["areas"], terms=self.f["terms"], groups={"Planar_FE_79", "Litho_FE_111"})

    def test_f11b_a_grounded_reply_passes(self):
        r = {"say": "Polishing has 37 lots waiting on Planar_FE_79; 1 of its tools is down.", "walk_to": "Planar", "explain": None, "try": None}
        self.assertEqual(lou.check(r, self.f, "why is polishing slow?", self.ctx), [])

    def test_f11b_a_number_from_nowhere_is_sent_back(self):
        r = {"say": "Polishing has 52 lots waiting.", "walk_to": None, "explain": None, "try": None}
        errs = lou.check(r, self.f, "why is polishing slow?", self.ctx)
        self.assertTrue(any("52" in e for e in errs))

    def test_f11b_numbers_inside_names_and_from_the_question_are_fine(self):
        r = {"say": "With 2 more hours of watching, Planar_FE_79 still leads.", "walk_to": None, "explain": None, "try": None}
        self.assertEqual(lou.check(r, self.f, "what about 2 hours?", self.ctx), [])

    def test_f11b_unknown_places_terms_and_groups_are_sent_back(self):
        r = {"say": "Come with me.", "walk_to": "Moon", "explain": "flux capacitor", "try": {"change": "spare_tool", "group": "Nope_1"}}
        errs = lou.check(r, self.f, "show me", self.ctx)
        self.assertEqual(len(errs), 3, errs)
        r = {"say": "Try it.", "walk_to": None, "explain": None, "try": {"change": "teleport", "group": "Planar_FE_79"}}
        self.assertTrue(lou.check(r, self.f, "x", self.ctx))

    def test_f11b_a_long_say_is_sent_back(self):
        r = {"say": " ".join(["word"] * 80), "walk_to": None, "explain": None, "try": None}
        self.assertTrue(lou.check(r, self.f, "x", self.ctx))


class Ask(unittest.TestCase):
    def setUp(self):
        self.f = fake_facts()
        self.ctx = lou.Context(areas=self.f["areas"], terms=self.f["terms"], groups={"Planar_FE_79", "Litho_FE_111"})

    def test_f11b_a_wrong_first_reply_is_sent_back_once_with_its_reasons(self):
        replies = iter([json.dumps({"say": "52 lots.", "walk_to": None, "explain": None, "try": None}),
                        json.dumps({"say": "37 lots wait at Planar_FE_79.", "walk_to": "Planar", "explain": None, "try": None})])
        seen = []

        def complete(messages):
            seen.append(messages)
            return next(replies)
        r = lou.ask("why is polishing slow?", self.f, complete, self.ctx)
        self.assertTrue(r["ok"])
        self.assertEqual(r["tries"], 2)
        self.assertIn("52", seen[1][-1]["content"])
        self.assertEqual(r["walk_to"], "Planar")

    def test_f11b_two_wrong_replies_fall_back(self):
        r = lou.ask("x", self.f, lambda m: json.dumps({"say": "99 lots.", "walk_to": None, "explain": None, "try": None}), self.ctx)
        self.assertFalse(r["ok"])
        self.assertTrue(r["fallback"])
        self.assertTrue(r["errors"])

    def test_f11b_a_reply_that_is_not_json_is_sent_back(self):
        replies = iter(["Sure! Polishing is busy.", json.dumps({"say": "Polishing is busy.", "walk_to": None, "explain": None, "try": None})])
        r = lou.ask("x", self.f, lambda m: next(replies), self.ctx)
        self.assertTrue(r["ok"])


class Facts(unittest.TestCase):
    def test_f11a_facts_come_from_the_run_and_name_real_areas(self):
        campus = lou.load_campus(CAMPUS)
        moods = {"group_names": ["Planar_FE_79", "Litho_FE_111"], "tools": ["Planar_FE_79#1", "Litho_FE_111#1"],
                 "tool_moods": ["idle", "work", "hurt"], "score": {"wafers_per_day": 1263.4, "cycle_days": 60.5},
                 "frames": [{"t": 0.0, "queues": [5, 2], "tools": [1, 0]}, {"t": 800.0, "queues": [37, 12], "tools": [2, 1]}]}
        f = lou.facts(moods, 805.0, campus, near_area="Planar")
        self.assertEqual(f["clock"], "13:20")                      # t is minutes since midnight
        self.assertEqual(f["longest"][0]["group"], "Planar_FE_79")
        self.assertEqual(f["longest"][0]["waiting"], 37)
        self.assertEqual(f["longest"][0]["area_name"], campus["areas"]["Planar"])
        self.assertEqual(f["longest"][0]["down"], 1)
        self.assertEqual(f["here"]["area"], "Planar")
        self.assertIn("Planar", f["areas"])


class Helper(unittest.TestCase):
    def test_f11d_no_key_means_the_rules_answer_and_the_reply_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            h = helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True)
            r = h.lou_ask({"question": "why is polishing slow?", "run": "none", "t": 0})
            self.assertTrue(r.get("fallback"))
            self.assertIn("message", r)

    @unittest.skipUnless(FABSIM.exists(), "needs the built simulator")
    def test_f11c_a_try_is_scored_by_the_simulator_on_the_same_seed(self):
        with tempfile.TemporaryDirectory() as d:
            s = Path(d) / "stand"
            s.mkdir()
            (s / "lou.json").write_text(json.dumps({"replies": [json.dumps(
                {"say": "Let us give polishing a spare and see.", "walk_to": None, "explain": None,
                 "try": {"change": "spare_tool", "group": "Planar_FE_79"}})]}))
            h = helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True, stand_in=s)
            run = h.fab3d_run({"seed": 1, "days": 0.5})
            r = h.lou_ask({"question": "what if polishing had a spare tool?", "run": run["run"], "t": 400})
            self.assertTrue(r["ok"], r)
            card = r["try_result"]
            for k in ("before", "after", "change", "group", "seed"):
                self.assertIn(k, card)
            self.assertEqual(card["seed"], 1)
            for side in ("before", "after"):
                self.assertIn("wafers_per_day", card[side])
                self.assertIn("group_waiting", card[side])


if __name__ == "__main__":
    unittest.main()
