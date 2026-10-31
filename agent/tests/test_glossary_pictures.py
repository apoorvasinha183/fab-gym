"""The glossary's pictures and newcomer lines (docs/GLOSSARY-PLUS.md, GP7 and GP8). Written before the code. Nothing is
spent: the model is a stand-in. On a teaching fab of our own and the SMT2020 testbed; not a real fab."""

import json
import tempfile
import unittest
from pathlib import Path

from agent import glossary_pictures as gp
from agent import spend

KEY = "sk-test-NOT-A-REAL-KEY-123"
# the smallest valid WebP (1 x 1, lossless)
TINY = bytes.fromhex("524946461a000000574542505650384c0d0000002f0000001007101111888808")


class Pictures(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "glossary"
        self.out.mkdir()
        self.meter = spend.Meter({}, cap_usd=0.03, path=self.tmp / "spend-glossary.json")
        self.asked = []

    def call(self, prompt):
        self.asked.append(prompt)
        return TINY

    def jobs(self, n):
        return {f"Term {i}": {"prompt": f"Draw term {i} as a cartoon, in the cast's style, with no words.", "file": f"glossary/term-{i}.webp"}
                for i in range(n)}

    def test_gp7_makes_only_missing_pictures_and_counts_each(self):
        (self.out / "term-0.webp").write_bytes(TINY)
        r = gp.make_pictures(self.jobs(3), self.tmp, self.meter, self.call, key=KEY, save=lambda data, path: path.write_bytes(data))
        self.assertEqual(r["skipped"], ["Term 0"])
        self.assertEqual(r["made"], ["Term 1", "Term 2"])
        self.assertEqual(len(self.asked), 2)
        self.assertAlmostEqual(self.meter.usd, 2 * gp.PRICE_USD)
        self.assertTrue((self.out / "term-2.webp").is_file())

    def test_gp7_stops_at_the_cap_with_a_plain_message(self):
        r = gp.make_pictures(self.jobs(5), self.tmp, self.meter, self.call, key=KEY, save=lambda data, path: path.write_bytes(data))
        self.assertEqual(len(r["made"]), 3)
        self.assertLessEqual(self.meter.usd, self.meter.cap_usd + 1e-9)
        self.assertIn("budget", r["stopped"])
        self.assertNotIn("spend cap", r["stopped"])

    def test_gp7_never_writes_the_key(self):
        def fails(prompt):
            raise RuntimeError(f"401 for Bearer {KEY}")
        log = self.tmp / "log.json"
        r = gp.make_pictures(self.jobs(1), self.tmp, self.meter, fails, key=KEY, save=lambda data, path: path.write_bytes(data), log_path=log)
        self.assertEqual(r["made"], [])
        self.assertNotIn(KEY, json.dumps(r))
        self.assertNotIn(KEY, log.read_text())
        self.assertEqual(self.meter.usd, 0)

    def test_gp7_the_glossary_meter(self):
        m = gp.glossary_meter(self.tmp)
        self.assertEqual(m.path, self.tmp / "spend-glossary.json")
        self.assertEqual(m.cap_usd, 5.0)


class NewcomerLines(unittest.TestCase):
    TERMS = [{"term": "Lot", "meaning": "A box of wafers that travel together.", "here": "Volume lots hold 25 wafers.",
              "example": "Each small box is one lot.", "source": {"kind": "published", "text": "SMT2020"}, "see": ["Wafer"]},
             {"term": "Seed", "meaning": "A number that fixes the random draws.", "here": "Each run has one.",
              "example": "Run #12 uses seed 12.", "source": {"kind": "choice", "text": "ours"}, "see": []}]

    def test_gp8_sends_only_the_glossary_text_and_reads_one_line_a_term(self):
        sent = []

        def complete(messages):
            sent.append(messages)
            return json.dumps({"Lot": "A box of wafers that moves through the fab together.",
                               "Seed": "A number that makes a random run repeat exactly."})
        lines = gp.draft_plain(self.TERMS, complete)
        self.assertEqual(set(lines), {"Lot", "Seed"})
        text = json.dumps(sent)
        for t in self.TERMS:
            self.assertIn(t["meaning"], text)
        self.assertNotIn("SMT2020", text.replace("SMT2020 testbed", ""))  # no source text is sent
        self.assertEqual(len(sent), 1)

    def test_gp8_too_long_or_missing_lines_are_flagged(self):
        def complete(messages):
            return json.dumps({"Lot": " ".join(["word"] * 25) + "."})
        lines = gp.draft_plain(self.TERMS, complete)
        self.assertEqual(lines["Lot"], None)
        self.assertEqual(lines["Seed"], None)

    def test_gp8_counts_tokens_on_the_glossary_meter(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "key").write_text("stand-in")
        (tmp / "key").chmod(0o600)
        m = gp.plain_model(tmp, key_file=tmp / "key")
        self.assertEqual(m.meter.path, tmp / "spend-glossary.json")


if __name__ == "__main__":
    unittest.main()
