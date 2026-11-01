"""Ask the glossary (docs/GLOSSARY-PLUS.md, part 3: GE1 to GE5). Written before the code. No network: the model is a
recorded reply or a function the test writes; a helper here runs with no model."""

import json
import tempfile
import unittest
from pathlib import Path

from agent import glossary_ask, helper

ROOT = Path(__file__).resolve().parents[2]
STAND_IN = ROOT / "web" / "tests" / "fixtures" / "glossary"
QUESTION = "Why do lots wait so long at the polisher?"


class GlossaryAsk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.terms = glossary_ask.terms()

    def test_ge1_the_entries_share_the_questions_words(self):
        picked = [t["term"] for t in glossary_ask.related(QUESTION, self.terms)]
        self.assertTrue(0 < len(picked) <= 6, picked)
        self.assertEqual(picked[0], "Polishing (CMP)", f"the term's own names count most: {picked}")
        self.assertEqual(glossary_ask.related("Zebras xylophone quokka?", self.terms), [])

    def test_ge2_only_the_entries_sent_are_cited(self):
        sent = [t for t in self.terms if t["term"] in ("Polishing (CMP)", "Lot", "WIP cap")]
        r = glossary_ask.answer(QUESTION, sent, lambda messages: "They wait [[Lot]] at the polisher [[Polishing (CMP)]] by [[A made-up law]].")
        self.assertEqual(r["cites"], ["Lot", "Polishing (CMP)"])
        self.assertIn("A made-up law", r["answer"], "its words stay")
        self.assertNotIn("[[A made-up law]]", r["answer"], "without brackets")
        self.assertTrue(r["covered"])
        self.assertEqual(r["entries"], ["Polishing (CMP)", "Lot", "WIP cap"])
        none = glossary_ask.answer(QUESTION, sent, lambda messages: "The glossary does not cover this.")
        self.assertEqual((none["cites"], none["covered"]), ([], False))
        # the question and only the entries sent go to the model
        seen = {}
        glossary_ask.answer(QUESTION, sent, lambda messages: seen.setdefault("m", messages) and "x")
        text = json.dumps(seen["m"])
        self.assertIn(QUESTION, text)
        self.assertIn("Polishing (CMP)", text)
        self.assertNotIn("Bonferroni", text)

    def helper(self, d, **kw):
        return helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True, **kw)

    def test_ge3_a_recorded_reply_answers_and_costs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            h = self.helper(d, stand_in=STAND_IN)
            r = h.glossary_ask({"question": QUESTION})
            self.assertEqual(r["model"], "stand-in")
            self.assertEqual(r["cost_usd"], 0)
            self.assertTrue(r["cites"] and set(r["cites"]) <= set(r["entries"]), r)
            self.assertNotIn("Polisher queue law", r["cites"])
            self.assertEqual(h.glossary_meter.usd, 0.0)

    def test_ge4_no_model_lists_the_closest_entries(self):
        with tempfile.TemporaryDirectory() as d:
            h = self.helper(d)
            r = h.glossary_ask({"question": QUESTION})
            self.assertTrue(r.get("no_model"), r)
            self.assertEqual(r["entries"][0], "Polishing (CMP)")
            self.assertIsNone(r.get("answer"))
            self.assertEqual(h.glossary_meter.usd, 0.0, "nothing spent")

    def test_ge5_at_the_cap_nothing_is_asked(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "spend-glossary.json").write_text(json.dumps({"calls": 1, "usd": 5.0}))
            key = Path(d) / "fake.key"
            key.write_text("not-a-real-key")
            # a key file the test names, and a server that is not there: a call would fail with a connection error
            h = self.helper(d, meta_key_file=key, meta_base_url="http://127.0.0.1:9")
            r = h.glossary_ask({"question": QUESTION})
            self.assertIn("budget", (r.get("error") or "").lower(), r)
            self.assertEqual(h.glossary_meter.usd, 5.0)


if __name__ == "__main__":
    unittest.main()
