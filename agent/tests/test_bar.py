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


if __name__ == "__main__":
    unittest.main()
