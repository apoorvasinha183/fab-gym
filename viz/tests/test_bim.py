"""Tests for the IFC model of the campus (docs/BIM.md). Written before the code. A gigafab-style layout of our own
design from the SMT2020 testbed; not a real fab.

    .venv/bin/python -m unittest viz.tests.test_bim      (from the repo root)

Needs the scene file (viz/prep.py --real) and IfcOpenShell in the repo's .venv; skips without them.
"""

import collections
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "data/layout-real/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real/layout.json"
SCRIPT = ROOT / "viz/blueprint/blueprint.py"
GRID = 12.0
TOL = 1e-3

try:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as uel
    import ifcopenshell.validate
    HAVE = True
except ImportError:
    HAVE = False


def build(out):
    p = subprocess.run([sys.executable, str(SCRIPT), "--scene", str(SCENE), "--layout", str(LAYOUT), "--out", str(out),
                        "--no-pdf"], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)


def grid_count(scene, b):
    """Columns at every crossing of the 12 m grid: x lines from the building's west wall (and its east wall),
    y lines from each spine edge outward to the bays' end."""
    xs, x = [], b["x0"]
    while x <= b["x1"] + 1e-6:
        xs.append(x)
        x += GRID
    if abs(xs[-1] - b["x1"]) > 1e-6:
        xs.append(b["x1"])
    ys, y = 0, scene["spine"] / 2
    while y <= scene["spine"] / 2 + scene["depth"] + 1e-6:
        ys += 2
        y += GRID
    return len(xs) * ys


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the scene file and IfcOpenShell (.venv)")
class Ifc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        build(cls.tmp / "a")
        cls.path = cls.tmp / "a" / "fab-model.ifc"
        cls.f = ifcopenshell.open(str(cls.path))
        cls.scene = json.loads(SCENE.read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_schema_valid(self):
        self.assertEqual(self.f.schema, "IFC4")
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(self.f, logger)
        self.assertEqual(logger.statements, [], logger.statements[:5])

    def test_spatial_structure(self):
        f, S = self.f, self.scene
        self.assertEqual(len(f.by_type("IfcProject")), 1)
        self.assertEqual(len(f.by_type("IfcSite")), 1)
        bs = sorted(f.by_type("IfcBuilding"), key=lambda b: b.Name)
        self.assertEqual([b.Name for b in bs], ["Phase 1 fab", "Phase 2 fab"])
        for b in bs:
            storeys = [o for r in b.IsDecomposedBy for o in r.RelatedObjects if o.is_a("IfcBuildingStorey")]
            storeys.sort(key=lambda s: s.Elevation)
            self.assertEqual([s.Name for s in storeys], [fl["name"] for fl in S["floors"]])
            for s, fl in zip(storeys, S["floors"]):
                self.assertAlmostEqual(s.Elevation, fl["z0"], places=6)

    def test_elements(self):
        f, S = self.f, self.scene
        spaces = f.by_type("IfcSpace")
        self.assertEqual(sum(1 for s in spaces if s.Name.startswith("Bay ")), 39)
        self.assertEqual(sum(1 for s in spaces if s.Name.startswith("Spine")), 2)
        self.assertEqual(len(f.by_type("IfcWall")), 8)
        fabs = [c for c in S["campus"] if c["kind"] == "fab"]
        self.assertEqual(len(f.by_type("IfcColumn")), sum(grid_count(S, b) for b in fabs))
        proxies = f.by_type("IfcBuildingElementProxy")
        kinds = collections.Counter(p.ObjectType for p in proxies)
        want = collections.Counter(t["kind"] for t in S["tools"])
        for k, n in want.items():
            self.assertEqual(kinds[k], n, k)
        self.assertEqual(kinds["stocker"], len(S["stockers"]))
        self.assertEqual(kinds["hoist rail"], len(S["rails"]))
        self.assertEqual(sum(n for k, n in kinds.items() if k.startswith("campus ")),
                         sum(1 for c in S["campus"] if c["kind"] != "fab"))

    def test_tool_properties_and_places(self):
        S = self.scene
        tools = {}
        for p in self.f.by_type("IfcBuildingElementProxy"):
            ps = uel.get_psets(p).get("FabGym_Tool")
            if ps:
                tools[ps["SceneIndex"]] = (p, ps)
        self.assertEqual(sorted(tools), list(range(len(S["tools"]))))
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        for i, t in enumerate(S["tools"]):
            p, ps = tools[i]
            self.assertEqual(ps["ToolGroup"], S["groups"][t["g"]]["name"])
            self.assertEqual(ps["Area"], S["groups"][t["g"]]["area"])
            self.assertEqual(ps["Kind"], t["kind"])
            self.assertEqual(ps["LoadPorts"], S["kinds"][t["kind"]]["ports"])
            self.assertIn("SizeSource", ps)
            if i % 40:
                continue
            shape = ifcopenshell.geom.create_shape(settings, p)
            v = shape.geometry.verts
            xs, ys, zs = v[0::3], v[1::3], v[2::3]
            self.assertAlmostEqual(min(xs), t["x0"], delta=TOL)
            self.assertAlmostEqual(max(xs), t["x1"], delta=TOL)
            self.assertAlmostEqual(min(ys), t["y0"], delta=TOL)
            self.assertAlmostEqual(max(ys), t["y1"], delta=TOL)
            self.assertAlmostEqual(min(zs), S["clean_z"], delta=TOL)
            self.assertAlmostEqual(max(zs), S["clean_z"] + t["h"], delta=TOL)

    def test_basis_on_every_element(self):
        items = list(self.f.by_type("IfcElement")) + list(self.f.by_type("IfcSpace"))
        self.assertGreater(len(items), 1043)
        for e in items:
            b = uel.get_psets(e).get("FabGym_Basis")
            self.assertIsNotNone(b, e)
            self.assertIn("Not a real fab", b["Basis"])
            self.assertIn("NOT FOR CONSTRUCTION", b["Status"])
            self.assertIn(b["NumbersFrom"].split(":")[0], ("model", "assumed", "cited"))

    def test_ids_unique_and_stable(self):
        ids = [r.GlobalId for r in self.f.by_type("IfcRoot")]
        self.assertEqual(len(ids), len(set(ids)))
        build(self.tmp / "b")
        self.assertEqual(self.path.read_bytes(), (self.tmp / "b" / "fab-model.ifc").read_bytes())
        txt = self.path.read_text()
        self.assertNotIn("TSMC", txt)
        self.assertTrue(txt.isascii())


if __name__ == "__main__":
    unittest.main()
