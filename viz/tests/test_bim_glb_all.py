"""Tests for every element of the faithful BIM as glTF (docs/BIM-FAITHFUL.md, "The model to glTF"). Written before
the code. A gigafab-style layout of our own design on the SMT2020 model; not a real fab.

    .venv/bin/python -m unittest viz.tests.test_bim_glb_all      (from the repo root)

Needs the cross aisle scene and IfcOpenShell in the repo's .venv; skips without them.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
SCENE = ROOT / "data/layout-real-dd/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real-dd/layout.json"
SCENE0 = ROOT / "data/layout-real/scene-optimised.json"
LAYOUT0 = ROOT / "results/layout-real/layout.json"
RUN = ROOT / "viz/permit/run.py"
BLUEPRINT = ROOT / "viz/blueprint/blueprint.py"
GLTF = ROOT / "viz/bim/gltf.py"
# the structure-only GLB of the blueprint's IFC before this work (28 Oct 2026, fab-gym 7ffad51)
DEFAULT_SHA = "19d905da3e30e76bca31d1b656bfaa9e3928ef91248d6d23bc5eeebcfb159e7e"
TOL = 1e-3

try:
    import ifcopenshell
    import ifcopenshell.util.element as uel
    import bimgeo as G
    from test_bim_gltf import read_glb
    HAVE = True
except ImportError:
    HAVE = False


def run(args):
    p = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout + p.stderr)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def yup(lo, hi):
    """IFC (x, y, z) bounds as glTF (x, z, -y) bounds."""
    return np.array([lo[0], lo[2], -hi[1]]), np.array([hi[0], hi[2], -lo[1]])


@unittest.skipUnless(SCENE.exists() and HAVE, "needs the cross aisle scene and IfcOpenShell (.venv)")
class GlbAll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        run([RUN, "--place", "us", "--stage", "cd", "--scene", SCENE, "--layout", LAYOUT, "--out", cls.tmp / "us", "--no-pdf"])
        cls.ifc = cls.tmp / "us" / "fab-permit.ifc"
        cls.glb = cls.tmp / "all.glb"
        run([GLTF, "--all", "--ifc", cls.ifc, "--out", cls.glb])
        cls.doc, cls.bin = read_glb(cls.glb)
        cls.f = ifcopenshell.open(str(cls.ifc))
        cls.nodes = cls.doc["nodes"]
        cls.by_name = {n["name"]: i for i, n in enumerate(cls.nodes)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def acc(self, i):
        a = self.doc["accessors"][i]
        v = self.doc["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[a["type"]]
        return np.frombuffer(self.bin, dtype="<f4", count=a["count"] * n,
                             offset=v["byteOffset"] + a.get("byteOffset", 0)).reshape(-1, n)

    def products(self):
        return [e for e in self.f.by_type("IfcProduct") if e.Representation and not e.is_a("IfcOpeningElement")]

    def test_one_node_per_element(self):
        want = {f"{e.is_a()}_{e.GlobalId}" for e in self.products()}
        want |= {f"{e.is_a()}_{e.GlobalId}" for e in self.f.by_type("IfcElement") if e.IsDecomposedBy}
        got = {n["name"] for n in self.nodes if n.get("extras", {}).get("GlobalId")}
        spatial = {f"{e.is_a()}_{e.GlobalId}" for c in ("IfcSite", "IfcBuilding", "IfcBuildingStorey") for e in self.f.by_type(c)}
        self.assertEqual(got - spatial, want)
        self.assertTrue(spatial <= got)

    def test_tree(self):
        parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                self.assertNotIn(c, parent)
                parent[c] = i
        for e in self.products():
            i = self.by_name[f"{e.is_a()}_{e.GlobalId}"]
            agg = [r.RelatingObject for r in e.Decomposes]
            if agg and not agg[0].is_a("IfcSpatialStructureElement"):
                self.assertEqual(self.nodes[parent[i]]["name"], f"{agg[0].is_a()}_{agg[0].GlobalId}", e.Name)
                continue
            up = self.nodes[parent[i]]["extras"]
            self.assertIn(up.get("Class"), ("IfcBuildingStorey", "IfcSite"), e.Name)

    def test_extras(self):
        for e in self.products()[::25]:
            x = self.nodes[self.by_name[f"{e.is_a()}_{e.GlobalId}"]]["extras"]
            for k in ("GlobalId", "Name", "Class", "PredefinedType", "ObjectType", "Storey"):
                self.assertIn(k, x, e.Name)
            for pset, props in uel.get_psets(e).items():
                for k, v in props.items():
                    if k == "id":
                        continue
                    self.assertEqual(x.get(f"{pset}.{k}"), v, (e.Name, pset, k))

    def test_materials(self):
        names = {m["name"] for m in self.doc["materials"]}
        used = set()
        for e in self.products():
            if e.is_a("IfcSpace"):
                continue
            m = uel.get_material(e)
            if m is not None and m.is_a("IfcMaterialConstituentSet"):
                used |= {c.Material.Name for c in m.MaterialConstituents}
            elif m is not None:
                used.add(m.Name)
        self.assertEqual(used - names, set())

    def test_instances(self):
        self.assertIn("EXT_mesh_gpu_instancing", self.doc.get("extensionsUsed", []))
        self.assertNotIn("EXT_mesh_gpu_instancing", self.doc.get("extensionsRequired", []))
        for e in [e for e in self.products() if G.is_mapped(e)]:
            n = self.nodes[self.by_name[f"{e.is_a()}_{e.GlobalId}"]]
            kids = [self.nodes[c] for c in n.get("children", [])]
            inst = [k for k in kids if "EXT_mesh_gpu_instancing" in k.get("extensions", {})]
            self.assertTrue(inst, e.Name)
            count = sum(self.doc["accessors"][k["extensions"]["EXT_mesh_gpu_instancing"]["attributes"]["TRANSLATION"]]["count"]
                        for k in inst)
            self.assertEqual(count, len(G.items(e)), e.Name)

    def test_bounds(self):
        prods = self.products()
        plain = [e for e in prods if not G.is_mapped(e)][::40]
        b, _ = G.world_bounds(self.f, plain)
        for e in plain:
            n = self.nodes[self.by_name[f"{e.is_a()}_{e.GlobalId}"]]
            self.assertIn("mesh", n, e.Name)
            pos = np.vstack([self.acc(p["attributes"]["POSITION"]) for p in self.doc["meshes"][n["mesh"]]["primitives"]])
            lo, hi = yup(*b[e.GlobalId])
            self.assertTrue(np.allclose(pos.min(0), lo, atol=TOL) and np.allclose(pos.max(0), hi, atol=TOL), e.Name)
        for e in [e for e in prods if G.is_mapped(e)][::50]:
            ib = G.instance_boxes(e)
            lo, hi = yup(ib[:, 0].min(0), ib[:, 1].max(0))
            n = self.nodes[self.by_name[f"{e.is_a()}_{e.GlobalId}"]]
            glo, ghi = np.full(3, np.inf), np.full(3, -np.inf)
            for c in n["children"]:
                k = self.nodes[c]
                if "EXT_mesh_gpu_instancing" not in k.get("extensions", {}):
                    continue
                pos = np.vstack([self.acc(p["attributes"]["POSITION"]) for p in self.doc["meshes"][k["mesh"]]["primitives"]])
                at = k["extensions"]["EXT_mesh_gpu_instancing"]["attributes"]
                tr = self.acc(at["TRANSLATION"])
                rot = self.acc(at["ROTATION"]) if "ROTATION" in at else None
                for i, t in enumerate(tr):
                    p = pos
                    if rot is not None:
                        x, y, z, w = rot[i]
                        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
                        p = pos @ R.T
                    glo, ghi = np.minimum(glo, (p + t).min(0)), np.maximum(ghi, (p + t).max(0))
            self.assertTrue(np.allclose(glo, lo, atol=TOL) and np.allclose(ghi, hi, atol=TOL), e.Name)

    def test_same_bytes_and_default_mode(self):
        again = self.tmp / "again.glb"
        run([GLTF, "--all", "--ifc", self.ifc, "--out", again])
        self.assertEqual(sha(again), sha(self.glb))
        run([BLUEPRINT, "--scene", SCENE0, "--layout", LAYOUT0, "--out", self.tmp / "bp", "--no-pdf"])
        run([GLTF, "--ifc", self.tmp / "bp" / "fab-model.ifc", "--out", self.tmp / "default.glb"])
        self.assertEqual(sha(self.tmp / "default.glb"), DEFAULT_SHA)
        self.assertNotIn(b"TSMC", self.glb.read_bytes())
        self.assertIn("Not a real fab", json.dumps(self.doc["scenes"]) + json.dumps(self.nodes[self.doc["scenes"][0]["nodes"][0]]))


if __name__ == "__main__":
    unittest.main()
