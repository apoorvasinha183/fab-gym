"""Tests for the faithful BIM in Blender (docs/BIM-FAITHFUL.md, "Into Blender"). Written before the code.
A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab.

    BLENDER=~/Applications/Blender.app/Contents/MacOS/Blender .venv/bin/python -m unittest viz.tests.test_bim_blender

Runs Blender headless on the faithful GLB; skips without Blender, the cross aisle scene or IfcOpenShell.
viz/blender/bim.py writes report.json beside the .blend: what it built, read back from Blender's own data.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
SCENE = ROOT / "data/layout-real-dd/scene-optimised.json"
LAYOUT = ROOT / "results/layout-real-dd/layout.json"
MODELS = ROOT / "data/layout-real/models.json"
RUN = ROOT / "viz/permit/run.py"
GLTF = ROOT / "viz/bim/gltf.py"
BIM = ROOT / "viz/blender/bim.py"
BLENDER = Path(os.environ.get("BLENDER", Path.home() / "Applications/Blender.app/Contents/MacOS/Blender")).expanduser()
TRUTH = "From the SMT2020 testbed. A layout of our own design. Not a real fab."
TRADES = {"Architecture", "Structure", "Mechanical", "Plumbing", "Fire", "Electrical", "Process", "Site"}

try:
    import ifcopenshell  # noqa: F401
    from test_bim_gltf import read_glb
    HAVE = True
except ImportError:
    HAVE = False


def run(args, exe=sys.executable):
    p = subprocess.run([str(exe), *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(p.stdout[-4000:] + p.stderr[-4000:])
    return p.stdout


def png_rows(path):
    """Width, height and the raw filtered rows of an 8-bit RGB or RGBA PNG (enough to tell blank from not)."""
    b = Path(path).read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    i, idat = 8, b""
    w = h = None
    while i < len(b):
        n, kind = struct.unpack(">I4s", b[i:i + 8])
        data = b[i + 8:i + 8 + n]
        if kind == b"IHDR":
            w, h = struct.unpack(">II", data[:8])
        elif kind == b"IDAT":
            idat += data
        i += 12 + n
    return w, h, zlib.decompress(idat)


@unittest.skipUnless(BLENDER.exists() and SCENE.exists() and MODELS.exists() and HAVE,
                     "needs Blender, the cross aisle scene, the film's tool models and IfcOpenShell (.venv)")
class InBlender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        run([RUN, "--place", "us", "--stage", "cd", "--scene", SCENE, "--layout", LAYOUT, "--out", cls.tmp / "us", "--no-pdf"])
        cls.boxes = json.loads((cls.tmp / "us" / "boxes.json").read_text())
        cls.glb = cls.tmp / "all.glb"
        run([GLTF, "--all", "--ifc", cls.tmp / "us" / "fab-permit.ifc", "--out", cls.glb])
        cls.doc, _ = read_glb(cls.glb)
        cls.out = cls.tmp / "blend"
        run(["-b", "--factory-startup", "-P", BIM, "--", cls.glb, SCENE, MODELS, cls.out, "--still", "campus",
             "--res", "640x360", "--samples", "4"], exe=BLENDER)
        cls.R = json.loads((cls.out / "report.json").read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_objects_and_instances(self):
        elements = [n for n in self.doc["nodes"] if "GlobalId" in n.get("extras", {})
                    and n["extras"]["Class"] not in ("IfcSite", "IfcBuilding", "IfcBuildingStorey")]
        self.assertEqual(self.R["elements"], len(elements))
        inst = sum(self.doc["accessors"][n["extensions"]["EXT_mesh_gpu_instancing"]["attributes"]["TRANSLATION"]]["count"]
                   for n in self.doc["nodes"] if "EXT_mesh_gpu_instancing" in n.get("extensions", {}))
        self.assertEqual(self.R["instances"], inst)
        self.assertEqual(self.R["global_ids"], len(elements))     # every element object carries its GlobalId

    def test_collections(self):
        tree = self.R["collections"]
        self.assertEqual(set(tree), {"P1", "P2", "Site"})
        for b in ("P1", "P2"):
            self.assertTrue(tree[b], b)
            for storey, trades in tree[b].items():
                self.assertTrue(set(trades) <= TRADES | {"Spaces"}, (b, storey, trades))
        self.assertTrue(self.R["spaces_hidden"])

    def test_tool_dressing(self):
        d = self.R["dressing"]
        self.assertEqual(d["collection"], "Dressing (not in the IFC)")
        self.assertEqual(len(d["tools"]), len(json.loads(SCENE.read_text())["tools"]))
        for t in d["tools"]:
            b = self.boxes[t["GlobalId"]]["box"]
            for k in range(3):
                self.assertGreaterEqual(t["lo"][k], b[k] - 0.05, t)
                self.assertLessEqual(t["hi"][k], b[k + 3] + 0.05, t)
        self.assertTrue(d["boxes_hidden"])

    def test_still(self):
        self.assertTrue((self.out / "fab-bim.blend").exists())
        s = self.R["stills"]["campus"]
        self.assertEqual(s["caption"], TRUTH)
        w, h, raw = png_rows(self.out / s["file"])
        self.assertEqual((w, h), (640, 360))
        self.assertGreater(len(set(raw[1:4096])), 20)    # not one flat colour


if __name__ == "__main__":
    unittest.main()
