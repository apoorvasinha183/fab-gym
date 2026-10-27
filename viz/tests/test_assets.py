"""Tests for the outside assets in the realistic film (viz/blender/real.py) and the explore scene.

A gigafab-style layout of our own design on the SMT2020 model; not a real fab. The sky, four
ground textures, the cars and the people come from CC0 sets (docs/ASSETS.md). The tools, the
carriers, the hoist and the buildings stay our own. Workers and cars are drawn only: they are not
in the model and no number comes from them. Standard library only:

    python3 -m unittest viz.tests.test_assets      (from the repo root)

The report is written on the machine with Blender and copied home:

    Blender -b -P viz/blender/real.py -- SCENE MODELS FILM OUT --assets DIR --report OUT/real-check.json
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "viz/blender/real.py"
PUSH = ROOT / "viz/blender/push_assets.sh"
DOC = ROOT / "docs/ASSETS.md"
COMPOSE = ROOT / "viz/film/compose.py"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
REPORT = ROOT / "data/layout-real/real-check.json"
SOURCES = ("polyhaven", "ambientcg", "kenney", "quaternius")


class Sources(unittest.TestCase):
    def test_every_staged_file_comes_from_a_listed_source(self):
        push = PUSH.read_text()
        doc = DOC.read_text()
        used = set(re.findall(r'\$A/([a-z]+)/', push))
        self.assertTrue(used, "the push script copies from data/assets")
        for d in used:
            self.assertIn(d, SOURCES, d)
            self.assertIn(f"`{d}/", doc, f"{d} is listed in docs/ASSETS.md")

    def test_the_licences_are_cc0(self):
        doc = DOC.read_text()
        for name in ("Poly Haven", "ambientCG", "Kenney", "Quaternius"):
            row = [x for x in doc.splitlines() if name in x and x.startswith("|")]
            self.assertTrue(row, name)
            self.assertIn("CC0", row[0], name)


class Script(unittest.TestCase):
    def test_it_reads_only_the_staged_names(self):
        s = REAL.read_text()
        self.assertIn('opt("--assets")', s)
        for name in ("sky.hdr", "_color.jpg", "_height.jpg", "_rough.jpg", "cars", "ual.glb", "Walk_Loop"):
            self.assertIn(name, s, name)

    def test_it_falls_back_without_assets(self):
        s = REAL.read_text()
        # every textured material names the procedural one it replaces
        self.assertIn("fallback=", s)
        self.assertIn("if ASSETS", s)

    def test_drawn_only_is_said(self):
        doc = REAL.read_text().split('"""')[1]
        self.assertIn("Workers", doc)
        self.assertIn("drawn only", doc)

    def test_the_end_card_credits_each_source(self):
        c = COMPOSE.read_text()
        for name in ("Poly Haven", "ambientCG", "Kenney", "Quaternius", "CC0"):
            self.assertIn(name, c, name)
        self.assertIn("our own design", c)


R = json.loads(REPORT.read_text()) if REPORT.exists() else None


@unittest.skipUnless(R is not None and SCENE.exists(), "no Blender report")
class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = json.loads(SCENE.read_text())

    def test_the_sky_is_seen_and_the_sun_still_lights(self):
        self.assertEqual(R["sky"]["image"], "sky.hdr")
        self.assertTrue(R["sky"]["camera_only"], "the cloud sky is what the camera sees; the keyed sun lights")
        self.assertEqual(sorted(R["textures"]), ["asphalt", "concrete", "grass", "metal"])

    def test_workers_walk_the_aisles_on_the_clean_floor(self):
        w = R["workers"]
        self.assertGreaterEqual(len(w), 20)
        self.assertGreaterEqual(sum(1 for k in w if k["bay"] is None), 6, "some walk the spine, where the camera rides")
        cz = self.s["clean_z"]
        tools = self.s["tools"]
        bays = self.s["bays"]
        sp = self.s["spine"]
        stockers = self.s["stockers"]
        for k in w:
            for x, y, z in k["samples"]:
                self.assertAlmostEqual(z, cz, delta=0.01)
                if k["bay"] is None:  # on the spine, beside the stockers
                    ph = k["phase"]
                    x0, x1 = self.s["offsets"][ph], self.s["offsets"][ph] + self.s["lengths"][ph]
                    self.assertTrue(x0 < x < x1 and abs(y) < sp / 2 - 0.5, (ph, x, y))
                    for st in stockers:
                        self.assertFalse(st["x0"] - 0.3 < x < st["x1"] + 0.3 and st["y0"] - 0.3 < y < st["y1"] + 0.3, (x, y))
                    continue
                b = bays[k["bay"]]
                self.assertTrue(b["x0"] < x < b["x1"] and b["y0"] <= y <= b["y1"], (k["bay"], x, y))
                for t in tools:
                    inside = t["x0"] - 0.3 < x < t["x1"] + 0.3 and t["y0"] - 0.3 < y < t["y1"] + 0.3
                    self.assertFalse(inside, f"worker in bay {k['bay']} walks into a tool at {x:.2f}, {y:.2f}")

    def test_workers_face_the_way_they_walk(self):
        self.assertGreaterEqual(R["facing_ok"], 0.97)

    def test_the_visor_is_at_the_eyes_and_looks_ahead(self):
        # measured in Blender: from the head bone to the visor, against the way the plan faces him
        self.assertGreaterEqual(len(R["visor"]), 5)
        for fr, i, dot, z in R["visor"]:
            self.assertGreaterEqual(dot, 0.8, f"worker {i} at frame {fr} looks away from his way")
            self.assertTrue(1.4 < z < 1.85, f"worker {i}'s visor is {z} m up")

    def test_workers_are_seen(self):
        # frames of the film in which a worker stands in front of the camera, within 40 m
        self.assertGreaterEqual(R["frames_with_a_worker"], 24 * 20)

    def test_blender_puts_them_where_the_plan_says(self):
        self.assertGreaterEqual(len(R["placed"]), 5)
        for fr, i, got, want in R["placed"]:
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b, delta=0.02, msg=f"worker {i} at frame {fr}")

    def test_the_camera_never_meets_a_worker(self):
        self.assertGreaterEqual(R["camera_min_m"], 1.5)

    def test_cars_park_in_the_car_park_and_face_the_road(self):
        park = [c for c in self.s["campus"] if c["kind"] == "parking"][0]
        self.assertGreater(len(R["parked"]), 50)
        for x, y in R["parked"]:
            self.assertTrue(park["x0"] < x < park["x1"] and park["y0"] < y < park["y1"], (x, y))
        for c in R["moving"]:
            self.assertGreaterEqual(c["heading_dot"], 0.99, c)


if __name__ == "__main__":
    unittest.main()
