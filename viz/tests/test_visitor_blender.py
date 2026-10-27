"""Tests for the visitor film in Blender ("A Walk Through the Fab"): a person who walks like one,
in rooms and colours that make sense. A gigafab-style layout of our own design on the SMT2020
model; the visitor is drawn only and no number comes from him.

The plan (viz/visitor/film_plan.py -> data/layout-real/visitor-film.json) decides where he is, what
he does, where he looks and where the camera is. viz/blender/visitor.py builds the film from the
film's saved fab.blend, our person asset (viz/blender/people.py) and our prop asset
(viz/blender/props.py), and with --report writes what Blender actually made, frame by frame,
to data/layout-real/visitor-blender-report.json. These tests read that report against the plan
and the run. Standard library only; they skip while the report is missing.

    python3 -m unittest viz.tests.test_visitor_blender
"""

import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "data/layout-real/visitor-film.json"
REPORT = ROOT / "data/layout-real/visitor-blender-report.json"
SCENE = ROOT / "data/layout-real/scene-optimised.json"

FPS = 24
STATE_RGBA = {0: (0, 1, 0, 0), 1: (0, 0, 0, 1), 2: (0, 0, 1, 0), 3: (1, 0, 0, 0)}
WALKING = {"walk"}
STILL = {"stand", "interact", "lift", "mirror", "shower", "watch", "close"}
SUIT = {"coverall", "hood", "mask", "goggles", "gloves", "booties"}
STREET = {"shirt", "trousers", "shoes", "hair"}


def load(p):
    return json.loads(p.read_text()) if p.exists() else None


P, R, S = load(PLAN), load(REPORT), load(SCENE)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def angle(a, b):
    return abs(wrap(a - b))


def lerp_row(rows, s, cols):
    """The plan's row at film second s, columns cols interpolated (rows every dt)."""
    dt = P["dt"]
    i = min(int(s / dt + 1e-9), len(rows) - 2)
    a, b = rows[i], rows[i + 1]
    u = min(max((s - a[0]) / (b[0] - a[0]), 0.0), 1.0)
    return [a[c] + (b[c] - a[c]) * u for c in cols], a, b, u


def lerp_angle(a, b, u):
    return a + wrap(b - a) * u


def act_at(s):
    for a in P["acts"]:
        if a["s0"] <= s < a["s1"]:
            return a
    return P["acts"][-1]


def clock_at(s):
    k = P["clock"]
    for a, b in zip(k, k[1:]):
        if a[0] <= s <= b[0]:
            return a[1] + (b[1] - a[1]) * (s - a[0]) / (b[0] - a[0])
    return k[-1][1]


def floor_z(s):
    stage = [st for st in P["stages"] if st["s0"] <= s < st["s1"] or st is P["stages"][-1]][0]["name"]
    return 0.0 if stage in ("outside", "lobby", "lift") else S["clean_z"]


@unittest.skipIf(P is None or R is None or S is None, "run viz/blender/visitor.py --report first")
class Visitor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = R["person"]["frames"]  # [f, x, y, z, yaw, ball_l xyz, ball_r xyz, head_yaw, head_pitch]
        cls.end = P["path"][-1][0]

    def s_of(self, f):
        return (f - 1) / FPS

    # the film

    def test_frames_cover_the_plan(self):
        self.assertEqual(R["fps"], FPS)
        self.assertEqual(R["frames"][0], 1)
        self.assertEqual(R["frames"][1], int(round(self.end * FPS)) + 1)
        self.assertEqual([r[0] for r in self.frames], list(range(R["frames"][0], R["frames"][1] + 1)))
        self.assertIn("SMT2020", R["badge"])

    def test_film_only_things_are_gone(self):
        gone = R["removed"]
        self.assertEqual(gone["left"], [], "the film's hero lot, its camera moves and workers are not in this film")
        self.assertEqual(gone["hidden_ever"], [], "nothing of the fab vanishes or slides away on this film's clock")

    # his body

    def test_he_is_where_the_plan_puts_him(self):
        for r in self.frames:
            s = self.s_of(r[0])
            (x, y, z), a, bb, u = lerp_row(P["path"], s, (1, 2, 3))
            if any(a[0] < c <= bb[0] + 1e-9 for c in P["cuts"]) and 0 < u < 1:
                # across a cut he is in one shot or the other, never between
                self.assertTrue(any(math.hypot(r[1] - q[1], r[2] - q[2]) < 0.01 and angle(r[4], q[4]) < math.radians(1)
                                    for q in (a, bb)), f"between two shots at {s:.3f} s")
                continue
            b = lerp_angle(a[4], bb[4], u)
            self.assertLess(math.hypot(r[1] - x, r[2] - y), 0.01, f"off the plan at {s:.3f} s")
            self.assertAlmostEqual(r[3], z, delta=0.01)
            self.assertLess(angle(r[4], b), math.radians(1.0), f"facing the wrong way at {s:.3f} s")

    def test_he_is_a_person_sized_person(self):
        self.assertTrue(1.65 <= R["person"]["height"] <= 1.90, R["person"]["height"])
        self.assertTrue(1.50 <= R["person"]["eye"] <= 1.80)

    def test_his_feet_stay_planted_while_he_walks(self):
        """While he walks at speed, the foot on the ground does not skate: its ball moves under 0.25 m/s."""
        slips = []
        for a, b in zip(self.frames, self.frames[1:]):
            s = self.s_of(a[0])
            if act_at(s)["act"] not in WALKING or act_at(self.s_of(b[0]))["act"] not in WALKING:
                continue
            if any(s < c <= self.s_of(b[0]) + 1e-9 for c in P["cuts"]):
                continue
            speed = math.hypot(b[1] - a[1], b[2] - a[2]) * FPS
            if speed < 0.5:
                continue
            fz = floor_z(s)
            for k in (5, 8):
                if a[k + 2] <= fz + 0.04 and b[k + 2] <= fz + 0.04:
                    v = math.hypot(b[k] - a[k], b[k + 1] - a[k + 1]) * FPS
                    if v > 0.25:
                        slips.append((round(s, 3), "left" if k == 5 else "right", round(v, 2), round(speed, 2)))
        self.assertLessEqual(len(slips), 0.02 * len(self.frames), f"feet skate: {slips[:10]}")

    def test_his_feet_rest_when_he_stands(self):
        for a, b in zip(self.frames, self.frames[1:]):
            s = self.s_of(a[0])
            if act_at(s)["act"] not in STILL or act_at(self.s_of(b[0]))["act"] not in STILL:
                continue
            if any(s < c <= self.s_of(b[0]) + 1e-9 for c in P["cuts"]):
                continue
            for k in (5, 8):
                v = math.hypot(b[k] - a[k], b[k + 1] - a[k + 1]) * FPS
                self.assertLess(v, 0.15, f"a foot shuffles at {s:.3f} s")

    def test_he_stands_on_the_floor(self):
        """One foot is always on the floor: never floating, never sunk."""
        for r in self.frames:
            s = self.s_of(r[0])
            if act_at(s)["act"] in ("sit_enter", "sit_idle"):
                continue
            low = min(r[7], r[10]) - floor_z(s)
            self.assertTrue(-0.03 <= low <= 0.06, f"lowest foot {low:+.3f} m off the floor at {s:.3f} s")

    def test_he_looks_where_the_plan_looks(self):
        for r in self.frames:
            s = self.s_of(r[0])
            if act_at(s)["act"] != "watch":
                continue
            sight = [x for x in P["sights"] if x["arrive_s"] + 1.0 <= s <= x["leave_s"]]
            if not sight:
                continue
            (p,), a, b, u = lerp_row(P["path"], s, (6,))
            h = lerp_angle(a[5], b[5], u)
            self.assertLess(angle(r[11], h), math.radians(15), f"his face is not on it at {s:.3f} s")
            self.assertLess(abs(r[12] - p), math.radians(15), f"he looks too high or low at {s:.3f} s")

    def test_his_head_turns_like_a_head(self):
        for a, b in zip(self.frames, self.frames[1:]):
            s = self.s_of(a[0])
            if any(s < c <= self.s_of(b[0]) + 1e-9 for c in P["cuts"]):
                continue
            self.assertLess(angle(a[11], a[4]), math.radians(105), f"head turned past his shoulder at {s:.3f} s")
            self.assertLess(angle(b[11], a[11]) * FPS, math.radians(300), f"head snaps at {s:.3f} s")

    def test_he_does_what_the_plan_says(self):
        """Each act plays its own clip: sitting on the bench, a hand to the reader, standing still."""
        clips = R["person"]["clips"]  # per frame: the clip with most weight
        want = {"walk": {"Walk_Loop"}, "turn": {"Walk_Loop", "Idle_Loop"}, "interact": {"Interact", "Idle_Loop"},
                "sit_enter": {"Sitting_Enter"}, "sit_idle": {"Sitting_Idle_Loop"},
                "stand": {"Idle_Loop"}, "lift": {"Idle_Loop"}, "mirror": {"Idle_Loop"}, "shower": {"Idle_Loop"},
                "watch": {"Idle_Loop"}, "close": {"Idle_Loop"}}
        for (f, clip) in clips:
            a = act_at(self.s_of(f))
            if self.s_of(f) - a["s0"] < 0.3:  # a short blend from the last act
                continue
            self.assertIn(clip, want[a["act"]], f"{clip} during {a['act']} at {self.s_of(f):.3f} s")
        acts = {act_at(self.s_of(f))["act"] for f, c in clips if c == "Interact"}
        self.assertIn("interact", acts, "his hand goes to the reader and the lift button")

    # what he wears

    def test_street_clothes_then_the_full_suit(self):
        lapse = [o["s"] for o in P["outfit"] if o["wear"] == "suit"][0]
        g = R["garments"]
        self.assertEqual(set(g), SUIT | STREET)
        for name, x in g.items():
            for f, shown in x["shown"]:
                s = self.s_of(f)
                if abs(s - lapse) < 1.0 / FPS:
                    continue
                self.assertEqual(shown, (s >= lapse) == (name in SUIT), f"{name} at {s:.3f} s")
        # colours that make sense: a white coverall, hood and booties, blue nitrile gloves, a pale mask,
        # dark glasses; ordinary street clothes
        def rgb(h):
            return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]

        for name in ("coverall", "hood", "booties"):
            c = rgb(g[name]["colour"])
            self.assertTrue(min(c) >= 0.85, f"{name} is not white: {g[name]['colour']}")
        c = rgb(g["gloves"]["colour"])
        self.assertTrue(c[2] > c[0] and c[2] > c[1] and c[2] > 0.5, "gloves are nitrile blue or violet")
        self.assertTrue(min(rgb(g["mask"]["colour"])) >= 0.7, "the mask is pale")
        self.assertTrue(max(rgb(g["goggles"]["colour"])) <= 0.45, "the glasses are dark and clear-tinted")
        for name in STREET:
            c = rgb(g[name]["colour"])
            sat = max(c) - min(c)
            self.assertLessEqual(sat, 0.45, f"{name} is a loud colour: {g[name]['colour']}")

    # the camera

    def test_the_camera_is_the_plans(self):
        cams = {r[0]: r for r in R["camera"]}
        self.assertEqual(R["fov_v"], P["fov_v"])
        cut_s = P["camera_cuts"]
        for row in P["camera"]:
            f = int(round(row[0] * FPS)) + 1
            if f not in cams:
                continue
            c = cams[f]
            self.assertLess(math.dist(c[1:4], row[1:4]), 0.01, f"camera at {row[0]:.3f} s")
            want = [row[4 + i] - row[1 + i] for i in range(3)]
            n = math.sqrt(sum(v * v for v in want))
            dot = sum(c[4 + i] * want[i] / n for i in range(3))
            self.assertGreater(dot, math.cos(math.radians(0.5)), f"camera looks away at {row[0]:.3f} s")
        # between samples it never slides across a cut
        for f, c in cams.items():
            s = self.s_of(f)
            (x, y, z), a, b, u = lerp_row(P["camera"], s, (1, 2, 3))
            if any(a[0] < cc <= b[0] + 1e-9 for cc in cut_s) and 0 < u < 1:
                self.assertTrue(math.dist(c[1:4], a[1:4]) < 0.01 or math.dist(c[1:4], b[1:4]) < 0.01,
                                f"camera between two shots at {s:.3f} s")

    # the fab, on this film's clock

    def test_tool_lamps_follow_the_run_on_this_clock(self):
        seq = {}
        for t, ti, code in S["states"]:
            seq.setdefault(ti, []).append((t, code))
        for ti, f, rgba in R["lamps"]:
            t = clock_at(self.s_of(f))
            st = [c for (tt, c) in seq.get(ti, [(S["from"], 1)]) if tt <= t + 1e-6]
            want = STATE_RGBA[st[-1] if st else seq[ti][0][1]]
            self.assertEqual(tuple(round(v) for v in rgba), want, f"tool {ti} at {self.s_of(f):.2f} s")
        self.assertGreaterEqual(len({x[0] for x in R["lamps"]}), 100)

    def test_lots_follow_the_run_on_this_clock(self):
        lots = {L["id"]: L["k"] for L in S["lots"]}
        n = 0
        for lid, f, x, y, z, shown in R["lots"]:
            k = lots[lid]
            t = clock_at(self.s_of(f))
            if not (k[0][0] <= t <= k[-1][0]):
                self.assertFalse(shown, f"lot {lid} shown outside its life at {self.s_of(f):.2f} s")
                continue
            self.assertTrue(shown)
            for a, b in zip(k, k[1:]):
                if a[0] <= t <= b[0]:
                    u = 0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
                    want = [a[i] + (b[i] - a[i]) * u for i in (1, 2, 3)]
                    break
            self.assertLess(math.dist((x, y, z), want), 0.05, f"lot {lid} at {self.s_of(f):.2f} s")
            n += 1
        self.assertGreaterEqual(n, 200)

    # the rooms of the way in

    def test_rooms_are_built_as_the_plan_draws_them(self):
        built = {r["name"]: r for r in R["rooms"]}
        for r in P["rooms"]:
            if r["kind"] == "walkway":
                continue
            b = built[r["name"]]
            for k in ("x0", "x1", "y0", "y1", "z0"):
                self.assertAlmostEqual(b["inside"][k], r[k], delta=0.03, msg=f"{r['name']} {k}")
            self.assertEqual(sorted((d["wall"], round(d["at"], 2), round(d["w"], 2)) for d in b["openings"]),
                             sorted((d["wall"], round(d["at"], 2), round(d["w"], 2)) for d in r["doors"]), r["name"])

    def test_props_stand_where_the_plan_puts_them(self):
        placed = {p["id"]: p for p in R["props"]}
        for r in P["rooms"]:
            for f in r.get("furniture", []):
                if f["kind"] == "mark":
                    continue
                p = placed[f["id"]]
                self.assertEqual(p["kind"], f["kind"])
                for k, i in (("x0", 0), ("y0", 1), ("z0", 2)):
                    self.assertAlmostEqual(p["min"][i], f[k], delta=0.05, msg=f"{f['id']} {k}")
                for k, i in (("x1", 0), ("y1", 1), ("z1", 2)):
                    self.assertAlmostEqual(p["max"][i], f[k], delta=0.05, msg=f"{f['id']} {k}")
                self.assertTrue(p["asset"], f"{f['id']} is an instance of a prop asset")

    def test_doors_open_before_he_reaches_them(self):
        """Every door on his way slides or swings open before he is within 0.6 m of it, and is open as he passes."""
        for d in R["doors"]:
            for s_pass, open_at in d["passes"]:
                self.assertLessEqual(open_at, s_pass - 0.6 / P["speed"] + 1e-6, f"{d['id']} opens late")
        self.assertGreaterEqual(sum(len(d["passes"]) for d in R["doors"]), 4)

    # colours that make sense

    def test_signs_are_white_with_the_area_colour_as_a_stripe(self):
        for area, x in R["signs"].items():
            face = [int(x["face"][i:i + 2], 16) for i in (1, 3, 5)]
            self.assertGreaterEqual(min(face), 225, f"{area}'s sign is not white")
            self.assertEqual(x["stripe"].lower(), S["areas"][area]["colour"].lower())
            self.assertLessEqual(x["emit"], 0.3, f"{area}'s sign glows")

    def test_lithography_works_under_yellow_light(self):
        self.assertTrue(R["light"]["litho"]["yellow"])
        self.assertFalse(R["light"]["other"]["yellow"])


if __name__ == "__main__":
    unittest.main()
