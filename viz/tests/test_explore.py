"""Tests for the explore scene (viz/godot-real): the realistic fab in Godot, walk and fly.

A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. The scene is
built from the same parts as the film (data/layout-real/models.json) and the same scene
(data/layout-real/scene-optimised.json). Standard library only:

    python3 -m unittest viz.tests.test_explore      (from the repo root)

The headless check runs Godot when GODOT names it; otherwise it reads the report the check
wrote on a machine that has Godot (data/layout-real/explore-check.json), and skips if neither.

    godot --headless --path viz/godot-real -- --check OUT.json
"""

import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJ = ROOT / "viz/godot-real"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
MODELS = ROOT / "data/layout-real/models.json"
REPORT = ROOT / "data/layout-real/explore-check.json"
GLB = ROOT / "data/layout-real/bim/fab-building.glb"
BIM_MATERIALS = ["bim_wall", "bim_column", "bim_slab_floor", "bim_slab_roof", "bim_covering_flooring",
                 "bim_covering_ceiling"]

BRANDS = ["ASML", "TSMC", "Tokyo Electron", "Applied Materials", "Lam Research", "KLA", "Daifuku", "Murata",
          "Samsung", "Intel", "TWINSCAN"]


def source():
    return (PROJ / "main.gd").read_text()


class Project(unittest.TestCase):
    def test_the_project_opens_on_its_scene(self):
        p = (PROJ / "project.godot").read_text()
        self.assertIn('run/main_scene="res://main.tscn"', p)
        self.assertIn("res://main.gd", (PROJ / "main.tscn").read_text())
        self.assertIn("data/", (PROJ / ".gitignore").read_text(), "the copied data stays out of git")

    def test_it_reads_the_films_parts_and_scene(self):
        s = source()
        self.assertIn("res://data/scene.json", s)
        self.assertIn("res://data/models.json", s)
        # tools are drawn from the kit's parts, never from shapes typed into the script
        for key in ('["kinds"]', '["min"]', '["max"]', '["shape"]', '["role"]', '["materials"]'):
            self.assertIn(key, s, key)

    def test_walk_fly_and_the_rest_are_on_keys(self):
        s = source()
        for words in ("walk", "fly", "Tab", "follow", "pause", "cut away"):
            self.assertIn(words, s, words)

    def test_it_says_what_it_is(self):
        s = source()
        self.assertIn("from the SMT2020 testbed", s)
        self.assertIn("not a real fab", s)
        for b in BRANDS:
            self.assertNotIn(b, s, b)


class Building(unittest.TestCase):
    """The structure comes from the IFC model (docs/BIM-3D.md)."""

    def test_the_building_scene_and_its_assets(self):
        tscn = (PROJ / "bim/building.tscn").read_text()
        self.assertIn("res://bim/building.gd", tscn)
        self.assertIn("res://data/fab-building.glb", tscn + (PROJ / "bim/building.gd").read_text())
        for m in BIM_MATERIALS:
            self.assertTrue((PROJ / f"bim/materials/{m}.tres").exists(), m)
        wall = (PROJ / "bim/materials/bim_wall.tres").read_text()
        self.assertIn("ShaderMaterial", wall)
        self.assertIn("res://bim/wall_cut.gdshader", wall)
        shader = (PROJ / "bim/wall_cut.gdshader").read_text()
        self.assertIn("bim_cut_z", shader)
        self.assertIn("bim_cut_z", (PROJ / "project.godot").read_text(), "the cut height is a global shader uniform")
        self.assertIn("fab-building.glb", (PROJ / "sync.sh").read_text())

    def test_main_no_longer_types_the_structure_in(self):
        s = source()
        self.assertIn("res://bim/building.tscn", s)
        for gone in ("sb.box(M_SLAB, x - 0.4", "wb.box(M_SLAB, X0, Y0, SUPPORT_TOP", "wb.box(M_TILE",
                     "rb.box(M_ROOF, X0, Y0, AIR_TOP", "low.box(M_FACADE", "ce.box(M_FFU_TOP"):
            self.assertNotIn(gone, s, gone)


def report():
    g = os.environ.get("GODOT")
    if g and SCENE.exists() and MODELS.exists():
        data = PROJ / "data"
        data.mkdir(exist_ok=True)
        (data / "scene.json").write_bytes(SCENE.read_bytes())
        (data / "models.json").write_bytes(MODELS.read_bytes())
        if GLB.exists():
            (data / "fab-building.glb").write_bytes(GLB.read_bytes())
        subprocess.run([g, "--headless", "--path", str(PROJ), "--import"], timeout=600)
        out = ROOT / "data/layout-real/explore-check.json"
        # the concept campus: the game opens on the US fab by default since docs/NARRATIVE.md, deliverable 4
        subprocess.run([g, "--headless", "--path", str(PROJ), "--", "--fab", "concept", "--check", str(out)], check=True, timeout=600)
        return json.loads(out.read_text())
    if REPORT.exists():
        return json.loads(REPORT.read_text())
    return None


R = report() if SCENE.exists() else None


def state_at(scene, t):
    st = [1] * len(scene["tools"])
    for tt, i, code in scene["states"]:
        if tt > t:
            break
        st[i] = code
    return st


def lot_at(keys, t):
    if t < keys[0][0] or t > keys[-1][0]:
        return None
    for a, b in zip(keys, keys[1:]):
        if a[0] <= t <= b[0]:
            u = 0.0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
            return [a[i] + (b[i] - a[i]) * u for i in (1, 2, 3)]
    return keys[-1][1:4]


@unittest.skipUnless(R is not None, "no Godot and no check report")
class Headless(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = json.loads(SCENE.read_text())
        cls.m = json.loads(MODELS.read_text())

    def test_every_tool_is_drawn_from_its_kind(self):
        self.assertEqual(R["tools"], len(self.s["tools"]))
        per = {}
        for t in self.s["tools"]:
            per[t["kind"]] = per.get(t["kind"], 0) + 1
        self.assertEqual(R["per_kind"], per)
        for kind, parts in self.m["kinds"].items():
            mats = {p["mat"] for p in parts if p["role"] != "light"}
            self.assertEqual(R["surfaces"][kind], len(mats), kind)

    def test_status_lights_follow_the_run(self):
        self.assertEqual(R["lamps"], state_at(self.s, R["t"]))

    def test_lots_ride_where_the_run_puts_them(self):
        lots = self.s["lots"]
        vis = sum(1 for L in lots if lot_at(L["k"], R["t"]) is not None)
        self.assertEqual(R["lots_visible"], vis)
        self.assertGreaterEqual(len(R["lot_samples"]), 20)
        for i, x, y, z in R["lot_samples"]:
            want = lot_at(lots[i]["k"], R["t"])
            self.assertIsNotNone(want, i)
            for a, b in zip((x, y, z), want):
                self.assertAlmostEqual(a, b, delta=1e-3)

    def test_walking_stops_at_a_tool(self):
        w = R["walk"]
        t = self.s["tools"][w["tool"]]
        self.assertAlmostEqual(w["eye"], self.s["clean_z"] + 1.6, delta=0.05)
        ex, ey = w["end"][0], w["end"][1]
        inside = t["x0"] <= ex <= t["x1"] and t["y0"] <= ey <= t["y1"]
        self.assertFalse(inside, "the walker went into the tool")
        self.assertGreater(abs(w["end"][0] - w["start"][0]), 0.5, "the walker moved")

    def test_flying_passes_through(self):
        f = R["fly"]
        t = self.s["tools"][R["walk"]["tool"]]
        lo, hi = sorted((f["start"][0], f["end"][0]))
        self.assertTrue(lo < t["x0"] and hi > t["x1"], "the flyer crossed the tool")

    def test_the_structure_is_the_ifc_models(self):
        import sys
        sys.path.insert(0, str(ROOT / "viz/blueprint"))
        import model
        m = model.build(self.s)
        want, boxes = {}, {}
        for e in m["elements"]:
            if e["cls"] in ("IfcWall", "IfcColumn", "IfcSlab", "IfcCovering"):
                want[e["cls"]] = want.get(e["cls"], 0) + 1
                boxes[e["name"]] = e["box"]
        b = R["bim"]
        self.assertEqual(b["nodes"], want)
        self.assertEqual(b["colliders"], sum(want.values()))
        self.assertGreaterEqual(len(b["samples"]), 20)
        for name, lo, hi in b["samples"]:
            x0, y0, z0, x1, y1, z1 = boxes[name]
            for a, c in zip(lo + hi, [x0, z0, -y1, x1, z1, -y0]):
                self.assertAlmostEqual(a, c, delta=1e-3, msg=name)
        fl = {f["name"]: f for f in self.s["floors"]}
        self.assertAlmostEqual(b["cut"]["on"], fl["cleanroom"]["z1"], delta=0.01)
        self.assertGreater(b["cut"]["off"], fl["roof"]["z1"])

    def test_the_badge(self):
        self.assertIn("from the SMT2020 testbed", R["badge"])
        self.assertIn("not a real fab", R["badge"])


if __name__ == "__main__":
    unittest.main()
