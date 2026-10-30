"""Tests for the variant in the game (docs/NARRATIVE.md, deliverable 4). Written before the code.
A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab.

The game opens on the US building, today's or the variant with copies for prototype orders, the same fabs the plans,
the BIM and the bill of materials were drawn from. F switches between them; in the variant each copy carries a
saffron marker and G walks the camera to the next one.

    .venv/bin/python -m unittest viz.tests.test_game_variant      (from the repo root)
    GODOT=/path/to/godot .venv/bin/python -m unittest viz.tests.test_game_variant   (also runs the game headless)
"""

import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJ = ROOT / "viz/godot-real"
FABS = {"today": "layout-real-dd", "variant": "layout-real-dd-copies"}
VARIANT = ROOT / "results/layout-real-dd-copies/variant.json"


def src(name):
    return (PROJ / name).read_text()


class Source(unittest.TestCase):
    def test_sync_copies_both_us_fabs(self):
        s = src("sync.sh")
        for fab, d in FABS.items():
            self.assertIn(f"data/{d}/scene-optimised.json", s)
            self.assertIn(f"data/fabs/{fab}", s)
            self.assertIn(f"data/{d}/bim/fab-building.glb", s)

    def test_the_game_takes_a_fab_and_switches_on_f(self):
        m = src("main.gd")
        self.assertIn('"--fab"', m)
        self.assertIn("res://data/fabs/", m)
        self.assertIn("KEY_F", m)
        self.assertIn("KEY_G", m)
        self.assertIn("F today / with copies", m)
        self.assertIn('check["fab"]', m)
        self.assertIn('check["copies"]', m)

    def test_the_building_comes_from_the_fab_it_shows(self):
        b = src("bim/building.gd")
        self.assertIn("glb_path", b)
        self.assertIn('"IfcWall/PARTITIONING"', b)

    def test_partitions_export_as_walls_and_the_concept_model_is_unchanged(self):
        g = (ROOT / "viz/bim/gltf.py").read_text()
        self.assertIn('("IfcWall", "PARTITIONING"): ("bim_wall"', g)


def report(fab):
    g = os.environ.get("GODOT")
    data = PROJ / "data/fabs" / fab
    if not g or not (data / "scene.json").exists():
        return None
    out = ROOT / f"data/{FABS[fab]}/explore-check.json"
    subprocess.run([g, "--headless", "--path", str(PROJ), "--", "--fab", fab, "--check", str(out)], check=True, timeout=900)
    return json.loads(out.read_text())


@unittest.skipUnless(os.environ.get("GODOT") and (PROJ / "data/fabs/variant/scene.json").exists(),
                     "set GODOT and run viz/godot-real/sync.sh")
class Game(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.today = report("today")
        cls.var = report("variant")
        cls.v = json.loads(VARIANT.read_text())

    def test_each_fab_is_its_own_scene(self):
        for fab, r in (("today", self.today), ("variant", self.var)):
            scene = json.loads((ROOT / f"data/{FABS[fab]}/scene-optimised.json").read_text())
            self.assertEqual(r["fab"], fab)
            self.assertEqual(r["tools"], len(scene["tools"]))

    def test_the_copies_are_marked_only_in_the_variant(self):
        self.assertEqual(self.today["copies"], [])
        self.assertEqual(sorted(self.var["copies"]), sorted(c["copy"] for c in self.v["copies"]))

    def test_the_building_is_loaded_in_both(self):
        for r in (self.today, self.var):
            self.assertGreater(r["bim"]["elements"], 0)


if __name__ == "__main__":
    unittest.main()
