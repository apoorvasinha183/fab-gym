"""One bar for anything (docs/ONE-BAR.md, OB7). Written before the code. An unsure question goes to Muse Spark, which
only rephrases it into the bar's own words; the helper keeps a pick only when it reads. No network: recorded picks."""

import json
import tempfile
import unittest
from pathlib import Path

from agent import helper

ROOT = Path(__file__).resolve().parents[2]


class Bar(unittest.TestCase):
    def route(self, pick, stand_in=True):
        with tempfile.TemporaryDirectory() as d:
            s = None
            if stand_in:
                s = Path(d) / "stand"
                s.mkdir()
                (s / "bar-route.json").write_text(json.dumps({"pick": pick}))
            h = helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True, stand_in=s)
            return h.bar_route({"question": "how is the fab feeling about its lots"})

    def test_ob7_a_pick_is_kept_only_when_it_reads(self):
        self.assertEqual(self.route({"kind": "now", "term": "WIP"})["pick"], {"kind": "now", "term": "WIP"})
        self.assertEqual(self.route({"kind": "words"})["pick"], {"kind": "words"})
        self.assertEqual(self.route({"kind": "go", "to": "open challenge 2"})["pick"], {"kind": "go", "to": "open challenge 2"})
        self.assertEqual(self.route({"kind": "change", "change": "double the breakdowns"})["pick"]["kind"], "change")
        self.assertEqual(self.route({"kind": "whatif", "question": "What if demand rises?"})["pick"]["kind"], "whatif")
        for bad in ({"kind": "dance"}, {"kind": "now", "term": "Happiness"}, {"kind": "change", "change": "make it nice"},
                    {"kind": "go", "to": "the moon"}, "not even an object"):
            self.assertEqual(self.route(bad)["pick"], {"kind": "none"}, bad)
        r = self.route(None, stand_in=False)
        self.assertEqual(r["pick"], {"kind": "none"})
        self.assertTrue(r["no_model"])


class Measure(unittest.TestCase):
    """Part 2, measure first: one line a question, and a report of how often the rules miss."""

    def helper(self, d, pick=None):
        s = None
        if pick is not None:
            s = Path(d) / "stand"
            s.mkdir(exist_ok=True)
            (s / "bar-route.json").write_text(json.dumps({"pick": pick}))
        return helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True, stand_in=s)

    def lines(self, d):
        p = Path(d) / "bar-log.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def test_ob8_one_line_a_question(self):
        with tempfile.TemporaryDirectory() as d:
            self.helper(d, {"kind": "now", "term": "WIP"}).bar_route({"question": "how is the fab feeling about its lots"})
            h = self.helper(d)
            h.bar_route({"question": "make the fab sing"})
            self.assertEqual(h.bar_log({"question": "double the breakdowns", "by": "rules", "kind": "change",
                                        "detail": "Breakdowns ×2"}), {"ok": True})
            for bad in ({"question": "", "by": "rules", "kind": "now"}, {"question": "x y", "by": "elves", "kind": "now"},
                        {"question": "x y", "by": "rules", "kind": "dance"}):
                self.assertIn("error", h.bar_log(bad), bad)
            got = self.lines(d)
            self.assertEqual([(x["by"], x["kind"]) for x in got], [("stand-in", "now"), ("none", "none"), ("rules", "change")])
            self.assertEqual(got[0]["question"], "how is the fab feeling about its lots")
            self.assertEqual(got[0]["detail"], "WIP")
            self.assertEqual(got[0]["cost_usd"], 0)
            self.assertEqual(got[2]["detail"], "Breakdowns ×2")
            self.assertTrue(all("t" in x for x in got))

    def test_ob9_the_report(self):
        from agent import bar_route
        rows = [
            {"t": "2026-11-01T10:00:00", "question": "how many lots are waiting?", "by": "rules", "kind": "now", "detail": "WIP", "cost_usd": 0},
            {"t": "2026-11-01T10:01:00", "question": "double the breakdowns", "by": "rules", "kind": "change", "detail": "Breakdowns ×2", "cost_usd": 0},
            {"t": "2026-11-01T10:02:00", "question": "what's a WIP cap?", "by": "rules", "kind": "words", "detail": "", "cost_usd": 0},
            {"t": "2026-11-01T10:03:00", "question": "how's the fab holding up", "by": "model", "kind": "now", "detail": "WIP", "cost_usd": 0.0004},
            {"t": "2026-11-01T10:04:00", "question": "make it sing", "by": "model", "kind": "none", "detail": "", "cost_usd": 0.0003},
        ]
        r = bar_route.report(rows)
        self.assertEqual(r["questions"], 5)
        self.assertEqual(r["by_rules"], 3)
        self.assertEqual(r["rules_kinds"], {"now": 1, "change": 1, "words": 1})
        self.assertEqual(r["misses"], 2)
        self.assertEqual(r["model_picks"], {"now": 1, "none": 1})
        self.assertAlmostEqual(r["cost_usd"], 0.0007)
        self.assertEqual([m["question"] for m in r["missed"]], ["make it sing", "how's the fab holding up"])
        text = bar_route.report_text(r)
        self.assertIn("3 of 5", text)
        self.assertIn("make it sing", text)


if __name__ == "__main__":
    unittest.main()
