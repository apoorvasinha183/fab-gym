"""The cinema laid out from rules (docs/FAB-3D.md, F11). Written before the code. From the SMT2020 testbed's campus,
our own design; not a real building. Standard library only:

    python3 -m unittest viz.tests.test_cinema      (from the repo root)
"""

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from viz.cinema import plan as cin  # noqa: E402

IN = 0.0254
FOOT = (40.0, -122.0, 76.0, -98.0)


def boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Cinema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = cin.layout(seats_target=100, sprinklered=True, rake="stadium")
        cls.c = cin.check(cls.p)
        cls.by = {r["rule"]: r for r in cls.c["rules"]}

    def test_f11_it_fits_the_campus_footprint_and_the_hall_is_deeper_than_wide(self):
        x0, y0, x1, y1 = self.p["footprint"]
        self.assertEqual((x0, y0, x1, y1), FOOT)
        for room in self.p["rooms"]:
            b = room["box"]
            self.assertTrue(x0 <= b[0] < b[2] <= x1 and y0 <= b[1] < b[3] <= y1, room)
        hall = next(r for r in self.p["rooms"] if r["name"] == "hall")["box"]
        depth = hall[2] - hall[0] if self.p["screen"]["wall"] in ("west", "east") else hall[3] - hall[1]
        width = hall[3] - hall[1] if self.p["screen"]["wall"] in ("west", "east") else hall[2] - hall[0]
        self.assertGreater(depth, width)

    def test_f11_about_100_occupants(self):
        occ = self.p["occupants"]
        self.assertEqual(occ, len(self.p["seats"]) + 2 * len(self.p["wheelchair"]))
        self.assertTrue(96 <= occ <= 110, occ)

    def test_f11_two_exits_far_enough_apart(self):
        exits = [d for d in self.p["doors"] if d.get("exit")]
        self.assertGreaterEqual(len(exits), 2)
        hall = next(r for r in self.p["rooms"] if r["name"] == "hall")["box"]
        diag = math.hypot(hall[2] - hall[0], hall[3] - hall[1])
        best = max(math.dist(a["at"], b["at"]) for a in exits for b in exits)
        self.assertGreaterEqual(best, diag / 3)
        for d in exits:
            self.assertGreaterEqual(d["clear_m"], 32 * IN)

    def test_f11_every_seat_within_the_paths_limits(self):
        for s in self.p["seats"]:
            self.assertLessEqual(s["common_path_m"], 30 * 0.3048 + 1e-6, s)
            self.assertLessEqual(s["travel_m"], 250 * 0.3048, s)

    def test_f11_aisles_rows_and_steps(self):
        for a in self.p["aisles"]:
            need = {"stepped_both": 48, "stepped_one": 36, "level_both": 42, "level_one": 36}[a["kind"]]
            if a["serves"] < 50 and a["kind"] in ("stepped_both", "level_both"):
                need = 36
            self.assertGreaterEqual(a["width_m"] + 1e-9, need * IN, a)
            self.assertLessEqual(a.get("dead_end_m", 0.0), 20 * 0.3048, a)
            if a["kind"].startswith("stepped"):
                self.assertTrue(4 * IN - 1e-9 <= a["riser_m"] <= 8 * IN + 1e-9, a)
                self.assertGreaterEqual(a["tread_m"] + 1e-9, 11 * IN, a)
                self.assertTrue(a["handrail"], a)
        for row in self.p["rows"]:
            per = row["seats_in_row_block_max"]
            need = 12 + (0.3 * max(0, per - 14) if row["access"] == "dual" else 0.6 * max(0, per - 7))
            self.assertGreaterEqual(row["clear_m"] + 1e-9, min(22, need) * IN, row)

    def test_f11_wheelchair_spaces(self):
        w = self.p["wheelchair"]
        self.assertEqual(len(w), 4)
        self.assertEqual(len({round(s["level"], 3) for s in w}), 2)               # two levels: vertical dispersion
        for lvl in {round(s["level"], 3) for s in w}:
            xs = [s for s in w if round(s["level"], 3) == lvl]
            self.assertGreaterEqual(len(xs), 2)
            self.assertGreater(abs(xs[0]["box"][1] - xs[1]["box"][1]) + abs(xs[0]["box"][0] - xs[1]["box"][0]), 3.0)  # spread across
        for s in w:
            b = s["box"]
            sides = sorted([b[2] - b[0], b[3] - b[1]])
            self.assertGreaterEqual(sides[0] + 1e-9, 0.915)
            self.assertGreaterEqual(sides[1] + 1e-9, 1.220)
            self.assertTrue(s["on_cross_aisle"])
            self.assertTrue(s["companion_seat"])
            for a in self.p["cross_aisles"]:
                self.assertFalse(boxes_overlap(b, a["clear_path"]), (s, a))

    def test_f11_doors_into_cross_aisles_open_onto_the_clear_path(self):
        # a door onto a cross aisle lands on its clear path, never across a wheelchair space
        for d in self.p["doors"]:
            if d["name"] not in ("front passage door", "ramp door"):
                continue
            ca = min(self.p["cross_aisles"], key=lambda a: abs(a["level"] - d["level"]))
            cp = ca["clear_path"]
            self.assertTrue(cp[0] <= d["at"][0] - d["clear_m"] / 2 and d["at"][0] + d["clear_m"] / 2 <= cp[2], (d, cp))

    def test_f11_every_rule_is_met_or_says_cannot_say(self):
        self.assertTrue(self.c["rules"])
        for r in self.c["rules"]:
            self.assertIn(r["status"], ("met", "cannot say"), r)
            self.assertTrue(r["cite"], r)
        reg = json.loads((ROOT / "viz/permit/codes/us-2024.json").read_text())["sections"]
        for r in self.c["rules"]:
            if r["status"] == "met":
                for c in r["cite"]:
                    self.assertIn(c, reg, r)
