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
PERMIT = ROOT / "data/layout-real-dd/permit-cd/us/boxes.json"
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

    def test_f11_the_cinema_floor_follows_the_built_steps(self):
        # the visitor's floor is read from the built model (data/cinema/built.json), so the camera never sinks
        # into a tier, the ramp, the exit stair or the projection room
        c = R["cinema"]
        self.assertTrue(c["floor_map"])
        self.assertAlmostEqual(c["floor_mid_aisle"], 1.24, delta=0.03)
        self.assertAlmostEqual(c["floor_row5"], 1.84, delta=0.03)
        self.assertAlmostEqual(c["floor_stair_top"], 2.44, delta=0.03)
        self.assertAlmostEqual(c["floor_projection"], 3.2, delta=0.03)
        self.assertAlmostEqual(c["floor_ramp_top"], 1.26, delta=0.03)

    def test_f11_doorways_are_open_and_walls_are_solid(self):
        c = R["cinema"]
        self.assertGreaterEqual(c["doorways"], 5)          # four doors and the sliding entrance
        self.assertEqual(c["doorways_blocked"], [])
        self.assertEqual(c["guide_legs_blocked"], [])      # the guide's body never passes through anything solid
        self.assertTrue(c["through_ramp_door"])
        self.assertFalse(c["walked_into_wall"])

    def test_f11_a_visitor_takes_a_seat_and_plays_the_film_full_screen(self):
        c = R["cinema"]
        self.assertEqual(c["seats"], 96)
        self.assertFalse(c["film_started_by_walking_in"])
        self.assertTrue(c["seated"])
        self.assertAlmostEqual(c["seated_eye_over_floor"], 1.15, delta=0.03)
        self.assertTrue(c["fullscreen"])

    def test_f11_a_few_people_already_sit_in_the_hall_and_the_lobby_has_posters(self):
        self.assertTrue(2 <= R["cinema"]["people"] <= 6, R["cinema"])
        self.assertEqual(R["cinema"]["posters"], 4)


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


def _hits(seg, box, z):
    """Does the leg seg = ((x0, y0), (x1, y1)) at height z pass through the box [x0, y0, z0, x1, y1, z1]?"""
    bx0, by0, bz0, bx1, by1, bz1 = box
    if not (bz0 <= z + 0.5 <= bz1):
        return False
    (ax, ay), (cx, cy) = seg
    t0, t1 = 0.0, 1.0
    for p, q, lo, hi in ((ax, cx - ax, bx0, bx1), (ay, cy - ay, by0, by1)):
        if abs(q) < 1e-12:
            if p <= lo or p >= hi:
                return False
            continue
        u, v = (lo - p) / q, (hi - p) / q
        t0, t1 = max(t0, min(u, v)), min(t1, max(u, v))
        if t0 >= t1:
            return False
    return True


@unittest.skipUnless(PERMIT.exists() and BUILDING.exists(), "needs the permit set and the building")
class Entrance(unittest.TestCase):
    """F9: from the parking lot to the cleanroom."""

    @classmethod
    def setUpClass(cls):
        cls.permit = json.loads(PERMIT.read_text())
        cls.by_key = {e["key"]: e for e in cls.permit.values()}
        cls.e = fab3d.entrance(cls.permit)

    def test_f9_the_permit_sets_rooms_and_fittings_are_used_unchanged(self):
        e = self.e
        for name, key in (("lift", "permit/lift/P1"), ("room", "permit/room/P1-GW1"), ("entry_door", "permit/door/P1-GW1/in"),
                          ("clean_door", "permit/door/P1-GW1"), ("air_shower", "permit/bim/airshower/P1-GW1"),
                          ("bench", "permit/bim/bench/P1-GW1"), ("rack", "permit/bim/rack/P1-GW1")):
            self.assertEqual(e["permit"][name]["key"], key)
            self.assertEqual(e["permit"][name]["box"], self.by_key[key]["box"], name)
        self.assertEqual(len(e["permit"]["lockers"]), 8)
        for lk in e["permit"]["lockers"]:
            self.assertEqual(lk["box"], self.by_key[lk["key"]]["box"])
        for name in ("lot", "pavilion", "ground_door", "lobby_walls"):
            self.assertIn(name, e["assumed"])
        self.assertIn("assumed", e["about"].lower())

    def test_f9_the_route_goes_from_the_lot_to_the_spine_in_order(self):
        r = self.e["route"]
        said = [s["kind"] for s in r if not s.get("via")]
        self.assertEqual(said, ["lot", "pavilion", "lift", "gowning", "air_shower", "cleanroom"])
        self.assertLess(r[0]["at"][2], 1.0)
        lot = self.e["assumed"]["lot"]
        self.assertTrue(lot[0] <= r[0]["at"][0] <= lot[2] and lot[1] <= r[0]["at"][1] <= lot[3])
        end = r[-1]["at"]
        self.assertAlmostEqual(end[2], 7.5)
        self.assertLessEqual(abs(end[1]), 3.6)       # on the spine
        self.assertGreater(end[0], 0.0)

    def test_f9_no_leg_goes_through_a_wall_a_column_or_a_tool(self):
        r = self.e["route"]
        lift = self.e["permit"]["lift"]["box"]
        blockers = [e["box"] for e in self.permit.values()
                    if e["cls"] in ("IfcWall", "IfcColumn", "IfcBuildingElementProxy", "IfcUnitaryEquipment", "IfcFurniture")
                    and e["key"] != "permit/bim/airshower/P1-GW1"]
        blockers += self.e["assumed"]["lobby_walls"]
        doors = [e["box"] for e in self.permit.values() if e["cls"] == "IfcDoor"] + [o["box"] for o in self.e["openings"]]
        for a, b in zip(r, r[1:]):
            (ax, ay, az), (bx, by, bz) = a["at"], b["at"]
            if b.get("ride"):
                self.assertEqual((ax, ay), (bx, by))
                self.assertTrue(lift[0] < ax < lift[3] and lift[1] < ay < lift[4], b)
                continue
            self.assertAlmostEqual(az, bz, msg=(a, b))
            seg = ((ax, ay), (bx, by))
            for box in blockers:
                if _hits(seg, box, az):
                    through = any(_hits(seg, d, az) for d in doors)
                    self.assertTrue(through, f"{a['kind']} -> {b['kind']} crosses {box}")

    def test_f9_each_opening_meets_what_it_opens(self):
        walls = [e["box"] for e in self.permit.values() if e["cls"] in ("IfcWall", "IfcSlab", "IfcCovering")]
        walls += [[-6.0, -70.0, 0.0, -5.7, 70.0, 18.5]]      # phase 1's west wall
        def meets(a, b):
            return all(a[i] < b[i + 3] and b[i] < a[i + 3] for i in range(3))
        names = {o["name"] for o in self.e["openings"]}
        self.assertTrue({"ground door", "entry door", "cleanroom door", "lift shaft"} <= names, names)
        for o in self.e["openings"]:
            self.assertTrue(any(meets(o["box"], w) for w in walls), o)
        shaft = next(o for o in self.e["openings"] if o["name"] == "lift shaft")["box"]
        lift = self.e["permit"]["lift"]["box"]
        self.assertEqual((shaft[0], shaft[1], shaft[3], shaft[4]), (lift[0], lift[1], lift[3], lift[4]))

    def test_f9_the_check_reports_the_entrance_and_the_tour_starts_in_the_lot(self):
        if not CHECK.exists():
            self.skipTest("no headless check report yet")
        c = json.loads(CHECK.read_text())
        self.assertTrue(c.get("entrance", {}).get("scene"))
        self.assertTrue(c.get("entrance", {}).get("lift_car"))
        self.assertEqual(c.get("tour_first"), "lot")


def _catmull(keys, t):
    """The camera point at time t on the Catmull-Rom curve through the keys' points (the scene flies the same)."""
    ts = [k["t"] for k in keys]
    i = max(0, min(len(keys) - 2, next((j for j in range(len(ts) - 1) if ts[j] <= t <= ts[j + 1]), len(ts) - 2)))
    p0, p1, p2, p3 = (keys[max(0, i - 1)]["at"], keys[i]["at"], keys[i + 1]["at"], keys[min(len(keys) - 1, i + 2)]["at"])
    u = (t - ts[i]) / (ts[i + 1] - ts[i])
    return [0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * u + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * u * u
                   + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * u * u * u) for c in range(3)]


SHOP = ROOT / "web/data/shop-real.txt"


@unittest.skipUnless(PERMIT.exists() and BUILDING.exists() and SCENE.exists(), "needs the permit set, the building and the scene")
class Drone(unittest.TestCase):
    """F10: the drone opening and the dressed campus."""

    @classmethod
    def setUpClass(cls):
        cls.permit = json.loads(PERMIT.read_text())
        cls.by_key = {e["key"]: e for e in cls.permit.values()}
        cls.b = json.loads(BUILDING.read_text())
        cls.x = fab3d.exterior(cls.permit)
        cls.e = fab3d.entrance(cls.permit)
        cls.d = fab3d.drone(cls.b, cls.x, cls.e, SHOP.read_text())

    def test_f10_the_permit_sets_plant_is_used_unchanged(self):
        p = self.x["permit"]
        for name, n in (("air_units", 16), ("curbs", 16), ("chillers", 27), ("transformers", 18)):
            self.assertEqual(len(p[name]), n, name)
            for it in p[name]:
                self.assertEqual(it["box"], self.by_key[it["key"]]["box"], it["key"])
        for name in ("roads", "trees", "stacks", "signs"):
            self.assertIn(name, self.x["assumed"])
        self.assertIn("assumed", self.x["about"].lower())

    def test_f10_roads_trees_and_stacks_keep_clear(self):
        fabs = [(f[0], f[2], f[1], f[3]) for f in self.b["fabs"]]
        lot = self.e["assumed"]["lot"]
        keep = fabs + [tuple(lot), (40.0, -122.0, 76.0, -98.0)]
        def over(a, r):
            return a[0] < r[2] and r[0] < a[2] and a[1] < r[3] and r[1] < a[3]
        for road in self.x["assumed"]["roads"]:
            for r in keep:
                self.assertFalse(over(road, r), (road, r))
        for x, y, rad, h in self.x["assumed"]["trees"]:
            spot = (x - rad, y - rad, x + rad, y + rad)
            for r in keep + [tuple(rd) for rd in self.x["assumed"]["roads"]]:
                self.assertFalse(over(spot, r), ((x, y), r))
        units = [it["box"] for it in self.x["permit"]["air_units"]]
        for x, y, rad, h in self.x["assumed"]["stacks"]:
            self.assertTrue(any(f[0] < x < f[2] and f[1] < y < f[3] for f in fabs[:2]), (x, y))
            for u in units:
                self.assertFalse(u[0] - 2 < x < u[3] + 2 and u[1] - 2 < y < u[4] + 2, ((x, y), u))

    def test_f10_the_flight_takes_in_the_campus_and_lands_at_the_tour(self):
        keys = self.d["keys"]
        T = keys[-1]["t"]
        self.assertTrue(25.0 <= T <= 35.0, T)
        self.assertGreaterEqual(keys[0]["at"][2], 60.0)
        for k in keys[:-2]:
            self.assertGreaterEqual(k["at"][2], 25.0, k)
        fabs = [(f[0], f[2], f[1], f[3]) for f in self.b["fabs"]]
        pts = [_catmull(keys, i * 0.1) for i in range(int(T * 10) + 1)]
        for p in pts:
            for f in fabs:
                if f[0] < p[0] < f[2] and f[1] < p[1] < f[3]:
                    self.assertGreater(p[2], 19.5 + 2.0, p)
        sights = {"phase 1": (127.9, 0.0), "phase 2": (407.0, 0.0), "bridge": (285.8, 0.0), "cinema": (58.0, -110.0),
                  "utility yard": (179.0, -170.0)}
        for name, (sx, sy) in sights.items():
            near = min(((p[0] - sx) ** 2 + (p[1] - sy) ** 2) ** 0.5 for p in pts)
            self.assertLessEqual(near, 110.0, name)
        lot = self.e["route"][0]["at"]
        end = keys[-1]["at"]
        self.assertLessEqual(((end[0] - (lot[0] - 5.0)) ** 2 + (end[1] - lot[1]) ** 2) ** 0.5, 0.5)
        self.assertAlmostEqual(end[2], 1.75, delta=0.2)

    def test_f10_its_numbers_come_from_the_data(self):
        text = " ".join(k.get("say", "") for k in self.d["keys"])
        self.assertIn(f"{len(self.b['tools']):,} tools", text)
        fleet = next(l for l in SHOP.read_text().splitlines() if l.startswith("fleet"))
        self.assertIn(f"{int(fleet.split()[1])} overhead vehicles", text)
        p1 = len({l[3] for l in self.b["labels"] if l[1] < 261.8})
        self.assertIn(f"{p1} areas", text)
        self.assertIn("SMT2020 testbed", text)
        self.assertIn("isn't a real fab", text)

    def test_f10_the_check_reports_the_drone(self):
        if not CHECK.exists():
            self.skipTest("no headless check report yet")
        c = json.loads(CHECK.read_text())
        self.assertTrue(c.get("drone", {}).get("scene"))
        self.assertGreaterEqual(c.get("drone", {}).get("keys", 0), 6)


@unittest.skipUnless(PERMIT.exists(), "needs the permit set")
class Bridge(unittest.TestCase):
    """F10: the bridge between the phases is drawn, walked and opened."""

    def test_f10_the_bridge_spans_the_gap_at_the_clean_floor_with_doorways(self):
        permit = json.loads(PERMIT.read_text())
        by = {e["key"]: e for e in permit.values()}
        br = fab3d.exterior(permit)["bridge"]
        self.assertEqual(br["outline"]["box"], by["campus/B1"]["box"])
        deck = br["deck"]
        self.assertAlmostEqual(deck[5], 7.5)
        self.assertLessEqual(deck[0], 261.8)
        self.assertGreaterEqual(deck[3], 309.8)
        self.assertGreater(br["roof_z"], 7.5 + 2.5)
        for wall, op in zip(("P1/wall/E", "P2/wall/W"), br["openings"]):
            w = by[wall]["box"]
            self.assertTrue(all(op[i] < w[i + 3] and w[i] < op[i + 3] for i in range(3)), (wall, op))
            self.assertLessEqual(op[2], 7.5)
            self.assertGreaterEqual(op[5] - 7.5, 2.4)
