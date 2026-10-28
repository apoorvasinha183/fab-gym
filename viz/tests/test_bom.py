"""Tests for the bill of materials read from the faithful BIM (docs/BOM.md). Written before the code.
A gigafab-style layout of our own design on the SMT2020 model; not a real fab. NOT FOR CONSTRUCTION.

    .venv/bin/python -m unittest viz.tests.test_bom      (from the repo root)

Needs the cross aisle scene and IfcOpenShell in the repo's .venv; skips without them.
"""

import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "data/layout-real-dd/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real-dd/layout.json"
RUN = ROOT / "viz/permit/run.py"
BOM = ROOT / "viz/bim/bom.py"
UNITS = {"m", "m3", "each"}
SECTIONS = {"structure", "architecture", "mechanical", "piping", "fire", "electrical", "process equipment", "site"}
SKIP = ("IfcSpace", "IfcOpeningElement")

try:
    import ifcopenshell
    HAVE = True
except ImportError:
    HAVE = False


def run(args):
    p = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)


def items(e):
    return [i for r in e.Representation.Representations for i in r.Items]


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the cross aisle scene and IfcOpenShell (.venv)")
class Bom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        run([RUN, "--place", "us", "--stage", "cd", "--scene", SCENE, "--layout", LAYOUT, "--out", cls.tmp / "us", "--no-pdf"])
        cls.ifc = cls.tmp / "us" / "fab-permit.ifc"
        run([BOM, "--ifc", cls.ifc, "--out", cls.tmp / "bom"])
        cls.B = json.loads((cls.tmp / "bom" / "bom.json").read_text())
        cls.f = ifcopenshell.open(str(cls.ifc))
        cls.prods = [e for e in cls.f.by_type("IfcProduct") if e.Representation and not any(e.is_a(s) for s in SKIP)]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def lines(self, cls):
        return [ln for ln in self.B["lines"] if ln["class"] == cls]

    def test_every_element_once(self):
        self.assertEqual(sum(ln["elements"] for ln in self.B["lines"]), len(self.prods))

    def test_units_add_up(self):
        want = sum(sum(1 for i in items(e) if i.is_a("IfcMappedItem")) or 1 for e in self.prods)
        self.assertEqual(sum(ln["units"] for ln in self.B["lines"]), want)

    def test_pipe_length_and_footing_volume(self):
        depth = sum(i.Depth for e in self.f.by_type("IfcPipeSegment") for i in items(e) if i.is_a("IfcExtrudedAreaSolid"))
        got = sum(ln["quantity"] for ln in self.lines("IfcPipeSegment"))
        self.assertTrue(all(ln["unit"] == "m" for ln in self.lines("IfcPipeSegment")))
        self.assertTrue(math.isclose(got, depth, rel_tol=1e-6), (got, depth))
        vol = 0.0
        for e in self.f.by_type("IfcFooting"):
            for i in items(e):
                if i.is_a("IfcExtrudedAreaSolid"):
                    p = i.SweptArea
                    self.assertTrue(p.is_a("IfcRectangleProfileDef"), p.is_a())
                    vol += p.XDim * p.YDim * i.Depth
        got = sum(ln["quantity"] for ln in self.lines("IfcFooting"))
        self.assertTrue(all(ln["unit"] == "m3" for ln in self.lines("IfcFooting")))
        self.assertTrue(math.isclose(got, vol, rel_tol=1e-6), (got, vol))

    def test_filter_units(self):
        # the arrays hold 38,546 (docs/BIM-FAITHFUL.md); bay 09 is drawn unit by unit; blank panels count apart
        arrays = [ln for ln in self.lines("IfcAirTerminal") if ln["type"] == "fan filter unit array"]
        self.assertTrue(arrays)
        self.assertEqual(sum(ln["units"] for ln in arrays), 38546)
        self.assertTrue(all(ln["unit"] == "each" and ln["quantity"] == ln["units"] for ln in arrays))
        single = [ln for ln in self.lines("IfcAirTerminal") if ln["type"] == "fan filter unit"]
        self.assertTrue(single and all(ln["units"] == ln["elements"] for ln in single))
        blank = [ln for ln in self.lines("IfcAirTerminal") if "blank panel" in ln["type"]]
        self.assertTrue(blank and all(ln["units"] == ln["elements"] for ln in blank))

    def test_formats_and_bytes(self):
        for ln in self.B["lines"]:
            self.assertIn(ln["unit"], UNITS, ln)
            self.assertIn(ln["section"], SECTIONS, ln)
            self.assertGreater(ln["quantity"], 0, ln)
        rows = list(csv.DictReader((self.tmp / "bom" / "bom.csv").open()))
        self.assertEqual(len(rows), len(self.B["lines"]))
        md = (self.tmp / "bom" / "bom.md").read_text()
        self.assertIn("On the SMT2020 model", md)
        self.assertIn("NOT FOR CONSTRUCTION", md)
        self.assertNotIn("TSMC", md)
        again = self.tmp / "bom2"
        run([BOM, "--ifc", self.ifc, "--out", again])
        for name in ("bom.json", "bom.csv", "bom.md"):
            a = hashlib.sha256((self.tmp / "bom" / name).read_bytes()).hexdigest()
            b = hashlib.sha256((again / name).read_bytes()).hexdigest()
            self.assertEqual(a, b, name)


if __name__ == "__main__":
    unittest.main()
