"""Tests for the IFC model as glTF (docs/BIM-3D.md). Written before the code. A gigafab-style layout of our own
design from the SMT2020 testbed; not a real fab.

    .venv/bin/python -m unittest viz.tests.test_bim_gltf      (from the repo root)

Needs the scene file (viz/prep.py --real) and IfcOpenShell in the repo's .venv; skips without them.
"""

import collections
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "data/layout-real/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real/layout.json"
BLUEPRINT = ROOT / "viz/blueprint/blueprint.py"
GLTF = ROOT / "viz/bim/gltf.py"
CLASSES = ["IfcWall", "IfcColumn", "IfcSlab", "IfcCovering"]
MATERIALS = {("IfcWall", "SOLIDWALL"): "bim_wall", ("IfcColumn", "COLUMN"): "bim_column",
             ("IfcSlab", "FLOOR"): "bim_slab_floor", ("IfcSlab", "ROOF"): "bim_slab_roof",
             ("IfcCovering", "FLOORING"): "bim_covering_flooring", ("IfcCovering", "CEILING"): "bim_covering_ceiling"}
TOL = 1e-3

try:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as uel
    HAVE = True
except ImportError:
    HAVE = False


def run(args):
    p = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)


def read_glb(path):
    b = Path(path).read_bytes()
    magic, version, length = struct.unpack_from("<4sII", b, 0)
    assert magic == b"glTF" and version == 2 and length == len(b), (magic, version, length, len(b))
    jlen, jtype = struct.unpack_from("<I4s", b, 12)
    assert jtype == b"JSON"
    doc = json.loads(b[20:20 + jlen])
    off = 20 + jlen
    blen, btype = struct.unpack_from("<I4s", b, off)
    assert btype == b"BIN\x00"
    return doc, b[off + 8:off + 8 + blen]


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the scene file and IfcOpenShell (.venv)")
class Glb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        run([BLUEPRINT, "--scene", SCENE, "--layout", LAYOUT, "--out", cls.tmp / "bp", "--no-pdf"])
        cls.ifc = cls.tmp / "bp" / "fab-model.ifc"
        cls.glb = cls.tmp / "a.glb"
        run([GLTF, "--ifc", cls.ifc, "--out", cls.glb])
        cls.doc, cls.bin = read_glb(cls.glb)
        cls.f = ifcopenshell.open(str(cls.ifc))
        sys.path.insert(0, str(ROOT / "viz/blueprint"))
        import model
        cls.model = model.build(json.loads(SCENE.read_text()))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def nodes(self):
        return [n for n in self.doc["nodes"] if "mesh" in n]

    def test_one_node_per_structural_element(self):
        want = collections.Counter()
        guids = set()
        for c in CLASSES:
            for e in self.f.by_type(c):
                want[c] += 1
                guids.add(e.GlobalId)
        got = collections.Counter(n["extras"]["Class"] for n in self.nodes())
        self.assertEqual(got, want)
        self.assertEqual({n["extras"]["GlobalId"] for n in self.nodes()}, guids)
        for n in self.nodes():
            self.assertEqual(n["name"], f"{n['extras']['Class']}_{n['extras']['GlobalId']}")
        names = [n["name"] for n in self.nodes()]
        self.assertEqual(names, sorted(names, key=lambda s: s.split("_", 1)[1]), "nodes sorted by GlobalId")
        self.assertEqual(self.doc["asset"]["version"], "2.0")

    def test_bounds_match_ifc_and_model(self):
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        boxes = {}
        for e in self.model["elements"]:
            boxes[e["name"]] = e["box"]
        for i, n in enumerate(self.nodes()):
            prim = self.doc["meshes"][n["mesh"]]["primitives"][0]
            acc = self.doc["accessors"][prim["attributes"]["POSITION"]]
            lo, hi = acc["min"], acc["max"]
            if i % 7 == 0:
                e = self.f.by_guid(n["extras"]["GlobalId"])
                v = ifcopenshell.geom.create_shape(settings, e).geometry.verts
                xs, ys, zs = v[0::3], v[1::3], v[2::3]
                want_lo = [min(xs), min(zs), -max(ys)]
                want_hi = [max(xs), max(zs), -min(ys)]
                for a, b in zip(lo + hi, want_lo + want_hi):
                    self.assertAlmostEqual(a, b, delta=TOL, msg=n["name"])
            x0, y0, z0, x1, y1, z1 = boxes[n["extras"]["Name"]]
            for a, b in zip(lo + hi, [x0, z0, -y1, x1, z1, -y0]):
                self.assertAlmostEqual(a, b, delta=TOL, msg=n["name"])
            # the accessor's bounds are the data's bounds
            bv = self.doc["bufferViews"][acc["bufferView"]]
            data = struct.unpack_from(f"<{acc['count'] * 3}f", self.bin, bv.get("byteOffset", 0) + acc.get("byteOffset", 0))
            for k in range(3):
                self.assertAlmostEqual(min(data[k::3]), lo[k], places=4)
                self.assertAlmostEqual(max(data[k::3]), hi[k], places=4)

    def test_extras_and_materials(self):
        mats = [m["name"] for m in self.doc["materials"]]
        self.assertEqual(sorted(mats), sorted(MATERIALS.values()))
        for n in self.nodes():
            x = n["extras"]
            for k in ("GlobalId", "Name", "Class", "PredefinedType", "Storey", "Basis", "Status", "NumbersFrom"):
                self.assertIn(k, x, n["name"])
            self.assertIn("Not a real fab", x["Basis"])
            self.assertIn("NOT FOR CONSTRUCTION", x["Status"])
            e = self.f.by_guid(x["GlobalId"])
            self.assertEqual(x["Name"], e.Name)
            self.assertEqual(x["PredefinedType"], e.PredefinedType)
            self.assertEqual(x["NumbersFrom"], uel.get_psets(e)["FabGym_Basis"]["NumbersFrom"])
            prim = self.doc["meshes"][n["mesh"]]["primitives"][0]
            self.assertEqual(mats[prim["material"]], MATERIALS[(x["Class"], x["PredefinedType"])], n["name"])

    def test_same_bytes_and_clean_text(self):
        b = self.tmp / "b.glb"
        run([GLTF, "--ifc", self.ifc, "--out", b])
        self.assertEqual(self.glb.read_bytes(), b.read_bytes())
        txt = json.dumps(self.doc)
        self.assertTrue(txt.isascii())
        self.assertNotIn("TSMC", txt)


if __name__ == "__main__":
    unittest.main()
