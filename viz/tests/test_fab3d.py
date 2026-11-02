"""The 3D fab and its guide (docs/FAB-3D.md, F1 and F5 to F8). Written before the code. From the SMT2020 testbed; a
gigafab-style layout of our own design; not a real fab. Standard library only:

    python3 -m unittest viz.tests.test_fab3d      (from the repo root)

The headless check runs Godot when GODOT names it; otherwise it reads the report a machine with Godot wrote
(data/fab3d/check.json), and skips if neither. The frame-rate bar (F8) reads data/fab3d/perf.json and fails until a
timed run on this laptop has written it.
"""

import json
import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import fab3d  # noqa: E402

PROJ = ROOT / "viz/fab3d"
BUILDING = ROOT / "web/data/building.json"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
CHECK = ROOT / "data/fab3d/check.json"
PERF = ROOT / "data/fab3d/perf.json"
MODELS = ROOT / "data/fab3d/models"
KINDS = ["deposition", "epitaxy", "etch", "furnace", "implanter", "inspection", "metrology", "polisher", "scanner",
         "track", "wet_bench"]
OTHERS = ["stocker", "carrier_standard", "carrier_copper"]
BRANDS = ["ASML", "TSMC", "Tokyo Electron", "Applied Materials", "Lam Research", "KLA", "Daifuku", "Murata",
          "Samsung", "Intel", "TWINSCAN"]


def sources():
    return {p: p.read_text() for p in sorted(PROJ.rglob("*")) if p.suffix in (".gd", ".tscn", ".cfg") and "addons" not in p.parts}


class Cells(unittest.TestCase):
    def test_f1_every_tool_in_one_cell_every_stretch_in_some_cell(self):
        b = json.loads(BUILDING.read_text())
        c = fab3d.cells(b)
        self.assertEqual(c["size"], 24.0)
        seen = [i for cell in c["cells"].values() for i in cell["tools"]]
        self.assertEqual(sorted(seen), list(range(len(b["tools"]))), "each tool exactly once")
        stretches = {s for cell in c["cells"].values() for s in cell["stretches"]}
        for a, z, _ in b["track"]["edges"]:
            self.assertIn(f"n{a}>n{z}", stretches)
        xs = [v for f in b["fabs"] for v in f[:2]]
        ys = [v for f in b["fabs"] for v in f[2:4]]
        for cell in c["cells"].values():
            x0, x1, y0, y1 = cell["bounds"]
            self.assertTrue(min(xs) - 24 <= x0 and x1 <= max(xs) + 24 and min(ys) - 24 <= y0 and y1 <= max(ys) + 24, cell["bounds"])

    def test_f1_every_kind_has_a_scene(self):
        b = json.loads(BUILDING.read_text())
        for k in sorted({t[5] for t in b["tools"]}):
            self.assertTrue((PROJ / "tools" / f"{k}.tscn").exists(), k)
        self.assertTrue((PROJ / "tools/stocker.tscn").exists())
        for k in ("standard", "copper"):
            self.assertTrue((PROJ / "carriers" / f"{k}.tscn").exists(), k)
        self.assertTrue((PROJ / "guide/ceo.tscn").exists())
        self.assertTrue((PROJ / "cinema/cinema.tscn").exists())


class Words(unittest.TestCase):
    def test_f5_it_says_what_it_is_and_names_no_maker(self):
        text = "\n".join(sources().values())
        self.assertIn("SMT2020 testbed", text)
        self.assertIn("not a real fab", text)
        for b in BRANDS:
            self.assertNotIn(b, text, b)
        self.assertIn('run/main_scene="res://main.tscn"', (PROJ / "project.godot").read_text())
        self.assertIn("data/", (PROJ / ".gitignore").read_text(), "the copied data stays out of git")


def report():
    g = os.environ.get("GODOT")
    if g and PROJ.exists():
        subprocess.run([sys.executable, str(PROJ / "prep.py")], check=True, timeout=600)
        subprocess.run([g, "--headless", "--path", str(PROJ), "--import"], timeout=900)
        CHECK.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([g, "--headless", "--path", str(PROJ), "--", "--check", str(CHECK)], check=True, timeout=900)
        return json.loads(CHECK.read_text())
    if CHECK.exists():
        return json.loads(CHECK.read_text())
    return None


R = report()


@unittest.skipIf(R is None, "no Godot here and no check report")
class Headless(unittest.TestCase):
    def test_f6_the_scene_opens_with_everything_saved(self):
        self.assertTrue(R["opened"])
        self.assertEqual(sorted(R["kinds"]), sorted(KINDS))
        for k in ("stocker", "carrier_standard", "carrier_copper", "guide", "cinema"):
            self.assertIn(k, R["scenes"], k)

    def test_f6_only_cells_near_the_viewer_are_loaded(self):
        self.assertEqual(R["viewer_at"], "bridge")
        self.assertGreater(R["cells_loaded"], 0)
        self.assertLessEqual(R["farthest_loaded_m"], 120.0)
        self.assertLess(R["cells_loaded"], R["cells_total"])

    def test_f6_the_cinema_holds_the_film(self):
        self.assertTrue(R["cinema_film"].endswith("from-sand-to-chip.ogv"), R["cinema_film"])


def glb_footprint(path):
    """Footprint (x by z extent, metres) of a glTF binary: the union of its POSITION accessors' bounds."""
    b = path.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    lo, hi = [1e9] * 3, [-1e9] * 3
    for m in j.get("meshes", []):
        for p in m["primitives"]:
            a = j["accessors"][p["attributes"]["POSITION"]]
            lo = [min(u, v) for u, v in zip(lo, a["min"])]
            hi = [max(u, v) for u, v in zip(hi, a["max"])]
    return hi[0] - lo[0], hi[2] - lo[2]


class Models(unittest.TestCase):
    def test_f7_each_kind_has_a_blender_script_and_a_model_at_its_size(self):
        kinds = json.loads(SCENE.read_text())["kinds"]
        for k in KINDS:
            self.assertTrue((ROOT / "viz/blender/tools" / f"{k}.py").exists(), k)
            glb = MODELS / f"{k}.glb"
            self.assertTrue(glb.exists(), k)
            w, d = glb_footprint(glb)
            want = sorted([kinds[k]["w"], kinds[k]["d"]])
            got = sorted([w, d])
            for g, x in zip(got, want):
                self.assertLessEqual(abs(g - x) / x, 0.05, f"{k}: {got} against {want}")
        for k in OTHERS:
            self.assertTrue((ROOT / "viz/blender/tools" / f"{k}.py").exists(), k)
            self.assertTrue((MODELS / f"{k}.glb").exists(), k)


class FrameRate(unittest.TestCase):
    def test_f8_sixty_frames_a_second_on_the_tour(self):
        self.assertTrue(PERF.exists(), "no timed run yet: data/fab3d/perf.json")
        p = json.loads(PERF.read_text())
        self.assertEqual(p["width"], 1920)
        self.assertEqual(p["height"], 1080)
        self.assertGreaterEqual(p["drawn_share"], 0.99)
        self.assertLessEqual(p["p99_ms"], 16.7)


if __name__ == "__main__":
    unittest.main()
