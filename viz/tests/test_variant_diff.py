"""Tests for the difference sheet between today's fab and the variant with copies (docs/NARRATIVE.md, deliverable 3).
Written before the code. A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab.
NOT FOR CONSTRUCTION.

    .venv/bin/python -m unittest viz.tests.test_variant_diff      (from the repo root)

Needs both fabs built (today's construction documents and the variant's, docs/NARRATIVE.md); skips without them.
"""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIFF = ROOT / "viz/variant/diff.py"
TODAY = {"layout": ROOT / "results/layout-real-dd/layout.json", "scene": ROOT / "data/layout-real-dd/scene-optimised.json",
         "dd": ROOT / "data/layout-real-dd/permit/us", "cd": ROOT / "data/layout-real-dd/permit-cd/us"}
VAR = {"layout": ROOT / "results/layout-real-dd-copies/layout.json",
       "scene": ROOT / "data/layout-real-dd-copies/scene-optimised.json",
       "dd": ROOT / "data/layout-real-dd-copies/permit/us", "cd": ROOT / "data/layout-real-dd-copies/permit-cd/us",
       "variant": ROOT / "results/layout-real-dd-copies/variant.json"}
NEED = [*TODAY.values(), *VAR.values(), TODAY["cd"] / "bom/bom.json", VAR["cd"] / "bom/bom.json"]


def build(out):
    p = subprocess.run([sys.executable, str(DIFF), "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)
    return json.loads((out / "difference.json").read_text())


def masked(path):
    # a sheet's title block names its source file and hash; those differ for every sheet
    t = path.read_text()
    return re.sub(r"[0-9a-f]{12,64}", "HASH", t).replace("layout-real-dd-copies", "layout-real-dd")


@unittest.skipUnless(all(p.exists() for p in NEED), "build both fabs first (docs/NARRATIVE.md)")
class Difference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "a"
        cls.d = build(cls.out)
        cls.v = json.loads(VAR["variant"].read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_copies_capital_and_travel_come_from_the_variant(self):
        self.assertEqual([c["copy"] for c in self.d["copies"]], [c["copy"] for c in self.v["copies"]])
        self.assertEqual(self.d["capital"], self.v["capital"])
        self.assertEqual(self.d["travel"]["before"], self.v["travel"]["before"])
        self.assertEqual(self.d["travel"]["after"], self.v["travel"]["after"])

    def test_every_code_check_reruns_and_every_change_is_listed(self):
        for stage in ("dd", "cd"):
            a = {(x["rule"], x["scope"]): x for x in json.loads((TODAY[stage] / "verdicts.json").read_text())}
            b = {(x["rule"], x["scope"]): x for x in json.loads((VAR[stage] / "verdicts.json").read_text())}
            c = self.d["checks"][stage]
            self.assertEqual(c["today"], len(a))
            self.assertEqual(c["variant"], len(b))
            self.assertEqual(sorted(tuple(x) for x in c["only_today"]), sorted(set(a) - set(b)))
            self.assertEqual(sorted(tuple(x) for x in c["only_variant"]), sorted(set(b) - set(a)))
            want = sorted(k for k in a if k in b and (a[k]["verdict"], a[k]["why"]) != (b[k]["verdict"], b[k]["why"]))
            self.assertEqual(sorted((x["rule"], x["scope"]) for x in c["changed"]), want)
            for x in c["changed"]:
                k = (x["rule"], x["scope"])
                self.assertEqual((x["before"]["verdict"], x["after"]["verdict"]), (a[k]["verdict"], b[k]["verdict"]))

    def test_the_bill_of_materials_difference_adds_the_copied_tools(self):
        lines = self.d["bom"]
        tools = sum(x["after"] - x["before"] for x in lines if x["section"] == "process equipment" and x["unit"] == "each")
        self.assertEqual(tools, sum(c["tools"] for c in self.v["copies"]))
        for x in lines:
            self.assertNotEqual(x["before"], x["after"], "only lines that change are listed")

    def test_the_sheets_listed_are_exactly_those_that_change(self):
        for stage in ("dd", "cd"):
            a, b = TODAY[stage] / "sheets", VAR[stage] / "sheets"
            names = sorted(p.name for p in a.glob("*.svg"))
            self.assertEqual(names, sorted(p.name for p in b.glob("*.svg")), "the same sheets in both sets")
            want = [n for n in names if masked(a / n) != masked(b / n)]
            self.assertEqual(self.d["sheets"][stage]["changed"], want)
            self.assertEqual(self.d["sheets"][stage]["total"], len(names))

    def test_tools_that_stay_put_are_at_the_same_place(self):
        a = json.loads(TODAY["scene"].read_text())
        b = json.loads(VAR["scene"].read_text())
        name_a = [g["name"] for g in a["groups"]]
        name_b = [g["name"] for g in b["groups"]]
        def places(s, names):
            seen, out = {}, {}
            for t in s["tools"]:
                n = names[t["g"]]
                i = seen.get(n, 0)
                seen[n] = i + 1
                out[(n, i)] = (t["bay"], round(t["x0"], 3), round(t["y0"], 3))
            return out
        pa, pb = places(a, name_a), places(b, name_b)
        copies = {c["copy"] for c in self.v["copies"]}
        self.assertEqual({k for k in pb if k[0] in copies}, {(c, 0) for c in copies})
        moved = {tuple(m) for m in self.d["tools"]["moved"]}
        for k in pa:
            if k not in moved:
                self.assertEqual(pa[k], pb[k], f"{k} did not move")
        self.assertEqual(self.d["tools"]["today"], len(pa))
        self.assertEqual(self.d["tools"]["variant"], len(pb))

    def test_the_sheet_is_drawn_and_labelled(self):
        svg = (self.out / "X-001.svg").read_text()
        for c in self.v["copies"]:
            self.assertIn(c["copy"], svg)
        self.assertIn("NOT FOR CONSTRUCTION", svg)
        self.assertIn("SMT2020 testbed", svg)
        md = (self.out / "difference.md").read_text()
        self.assertIn("SMT2020 testbed", md)

    def test_the_same_inputs_give_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "b"
            build(out)
            for name in ("difference.json", "difference.md", "X-001.svg"):
                h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
                self.assertEqual(h(self.out / name), h(out / name), name)


if __name__ == "__main__":
    unittest.main()
