"""Tests for the architectural construction documents of the whole fab (docs/ARCH-DOCS.md). Written before the code.
A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. Every sheet stays NOT FOR CONSTRUCTION.

    .venv/bin/python -m unittest viz.tests.test_arch_cd      (from the repo root)

Needs the cross aisle scene (docs/DESIGN-DEV.md, DD2) and IfcOpenShell in the repo's .venv; skips without them.
"""

import json
import math
import re
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
TRUTH = "From the SMT2020 testbed. A layout of our own design. Not a real fab."
ARCH = ["A-001", "A-100", "A-111", "A-112", "A-121", "A-122", "A-131", "A-132", "A-141", "A-142", "A-202", "A-311",
        "A-411", "A-412", "A-413", "A-414", "A-521", "A-531", "A-541", "A-551", "A-611", "A-612", "A-613", "A-614",
        "A-701", "A-702"]
PLANS = {"A-111": ("P1", "support floor"), "A-112": ("P1", "clean floor"), "A-121": ("P2", "support floor"),
         "A-122": ("P2", "clean floor")}

sys.path.insert(0, str(ROOT / "viz/blueprint"))

try:
    import ifcopenshell
    import ifcopenshell.util.element as uel
    import ifcopenshell.validate
    HAVE = True
except ImportError:
    HAVE = False


def load(p):
    return json.loads(Path(p).read_text())


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the cross aisle scene and IfcOpenShell (.venv)")
class Architecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "us"
        p = subprocess.run([sys.executable, str(RUN), "--place", "us", "--stage", "cd", "--scene", str(SCENE), "--layout",
                            str(LAYOUT), "--out", str(cls.out)], cwd=ROOT, capture_output=True, text=True)
        if p.returncode != 0:
            raise AssertionError(p.stdout + p.stderr)
        cls.P = load(cls.out / "permit.json")
        cls.A = cls.P["arch"]
        cls.S = load(SCENE)
        cls.f = ifcopenshell.open(str(cls.out / "fab-permit.ifc"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def svg(self, sid):
        return (self.out / "sheets" / f"{sid}.svg").read_text()

    def test_doors(self):
        doors = self.A["doors"]
        nos = [d["no"] for d in doors]
        self.assertEqual(len(nos), len(set(nos)))
        for d in doors:
            self.assertRegex(d["no"], r"^P[12]-[SCR]-\d{3}$")
        ifc_doors = [e for e in self.f.by_type("IfcDoor") if "FabGym_Permit" in uel.get_psets(e)]
        self.assertEqual(len(doors), len(ifc_doors))
        sets = self.A["hardware_sets"]
        rated = {d["key"]: d["rating_h"] for d in self.P["doors"]}
        sched = self.svg("A-611") + self.svg("A-612")
        for d in doors:
            self.assertIn(d["hardware"], sets, d["no"])
            if d["key"] in rated:
                self.assertEqual(d["rating_h"], rated[d["key"]], d["no"])
            self.assertIn(d["no"], sched, d["no"])
        for name in sets:
            self.assertIn(name, self.svg("A-614"))

    def test_rooms(self):
        rooms = self.A["rooms"]
        nos = [r["no"] for r in rooms]
        self.assertEqual(len(nos), len(set(nos)))
        spaces = [e for e in self.f.by_type("IfcSpace")]
        self.assertEqual(len(rooms), len(spaces))
        sched = self.svg("A-613")
        for r in rooms:
            for k in ("floor", "base", "walls", "ceiling"):
                self.assertTrue(r[k], (r["no"], k))
            self.assertGreater(r["ceiling_height_m"], 0, r["no"])
            self.assertIn(r["no"], sched, r["no"])

    def test_plan_dimensions(self):
        blds = {b["name"]: b for b in self.S["campus"] if b["kind"] == "fab"}
        for sid, (k, floor) in PLANS.items():
            d = self.A["dims"][sid]
            b = blds[k]
            self.assertEqual((d["building"], d["floor"]), (k, floor))
            self.assertAlmostEqual(d["overall_x_m"], b["x1"] - b["x0"], places=3)
            self.assertAlmostEqual(d["overall_y_m"], b["y1"] - b["y0"], places=3)
            self.assertAlmostEqual(sum(d["grid_x_m"]), d["overall_x_m"], places=3)
            self.assertAlmostEqual(sum(d["grid_y_m"]), d["overall_y_m"], places=3)
            svg = self.svg(sid)
            for door in self.A["doors"]:
                if door["building"] == k and door["floor"] == floor:
                    self.assertIn(door["no"], svg, (sid, door["no"]))

    def test_roofs(self):
        R = self.A["roof"]
        for k in ("P1", "P2"):
            r = R[k]
            self.assertGreaterEqual(r["drains"], math.ceil(r["area_m2"] / 900.0), k)
            self.assertGreaterEqual(r["hatches"], 1, k)
            self.assertGreater(r["parapet_m"], 0, k)
            self.assertEqual(r["curbs"], r["plant_units"], k)
        names = [e.Name or "" for e in self.f.by_type("IfcWall")]
        self.assertTrue(any(n.startswith("Parapet") for n in names))
        self.assertGreater(len(self.f.by_type("IfcWasteTerminal")), 0)

    def test_set(self):
        idx = [s["id"] for s in load(self.out / "index.json")]
        self.assertEqual(idx[-len(ARCH):], ARCH)
        self.assertEqual(len(idx), 73)
        for sid in idx:
            svg = self.svg(sid)
            self.assertIn(TRUTH, svg, sid)
            self.assertIn("NOT FOR CONSTRUCTION", svg, sid)
            self.assertIn('viewBox="0 0 1066.8 762"', svg, sid)
        self.assertEqual(self.P["clashes"], [])
        L = load(self.out / "ledger.json")
        self.assertEqual(L["counts"].get("missing", 0), 0, [i["id"] for i in L["items"] if i["status"] == "missing"])
        self.assertTrue(any(i["id"].startswith("AD.") for i in L["items"]))
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(self.f, logger)
        self.assertEqual([s for s in logger.statements if s.get("level", "").lower() == "error"], [])
        pdf = (self.out / "permit-set.pdf").read_bytes()
        self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", pdf)), 73)
        for p in self.out.rglob("*"):
            if p.suffix in (".svg", ".json", ".md", ".ifc"):
                self.assertNotIn("TSMC", p.read_text(), p.name)


if __name__ == "__main__":
    unittest.main()
