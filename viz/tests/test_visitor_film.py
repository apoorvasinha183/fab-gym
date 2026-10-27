"""Tests for the visitor film's plan ("A Walk Through the Fab", the Blender film): viz/visitor/film_plan.py.

A gigafab-style layout of our own design on the SMT2020 model; not a real fab. The founder on the
first, Godot cut (27 Oct): "unnatural walking, clanker walking indoors weirdly. Weird wall
trajectory". So this plan is held to how people move:

- he speeds up and slows down (no instant starts or stops), slows into curves, and never slides:
  every change of heading while standing is made by stepping (his gait distance grows with it);
- indoors he keeps clear of walls and furniture and goes through doors square on, in the middle;
- the way in is the one people take: the car park, the lobby turnstile with a badge tap, a lift,
  the bridge, the gowning room (sit on the bench over the line, then a time-lapse into the suit,
  a mirror check), the air shower, the clean floor;
- the camera never sits inside a wall, a tool or a piece of furniture, and keeps him in frame.

From the clean floor on, the run decides where he goes, scored as in plan.py. He is drawn only:
he is not in the model and no number comes from him. Standard library only:

    python3 -m unittest viz.tests.test_visitor_film      (from the repo root)

Units: fab time in minutes of the run, film time in seconds, plan metres (x east, y north, z up),
yaw in radians (0 faces +x, counter-clockwise).
"""

import ast
import json
import math
import subprocess
import sys
import tempfile
import unittest
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "viz/visitor/film_plan.py"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
TRACE = ROOT / "data/layout-real/trace-optimised.json"

STAGES = ["outside", "lobby", "lift", "bridge", "gowning", "air shower", "clean floor"]
WAY_IN = STAGES[:-1]
ACTS = {"walk", "stand", "turn", "interact", "sit_enter", "sit_idle", "lift", "mirror", "shower", "watch", "close"}
STILL = {"stand", "interact", "sit_enter", "sit_idle", "lift", "mirror", "shower", "watch", "close"}
KINDS = {"breakdown", "maintenance", "queue", "hot", "hoist"}
EYE = 1.6
DT = 0.125


def run_plan(out, seed=7):
    subprocess.run([sys.executable, str(PLAN), str(SCENE), str(TRACE), str(out), "--seed", str(seed)],
                   check=True, timeout=900)
    return json.loads(Path(out).read_text())


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def angle(a, b):
    return abs(wrap(a - b))


def ang3(u, v):
    nu = math.sqrt(sum(c * c for c in u))
    nv = math.sqrt(sum(c * c for c in v))
    c = sum(p * q for p, q in zip(u, v)) / (nu * nv)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def inside(box, x, y, pad=0.0):
    return box["x0"] - pad < x < box["x1"] + pad and box["y0"] - pad < y < box["y1"] + pad


def box_dist(b, x, y):
    dx = max(b["x0"] - x, 0.0, x - b["x1"])
    dy = max(b["y0"] - y, 0.0, y - b["y1"])
    return math.hypot(dx, dy)


def walls(room):
    """Each wall as (side, fixed coordinate, axis along, lo, hi, outward normal)."""
    return [("n", room["y1"], 0, room["x0"], room["x1"], (0, 1)), ("s", room["y0"], 0, room["x0"], room["x1"], (0, -1)),
            ("e", room["x1"], 1, room["y0"], room["y1"], (1, 0)), ("w", room["x0"], 1, room["y0"], room["y1"], (-1, 0))]


def in_room(room, x, y, z):
    return room["x0"] <= x <= room["x1"] and room["y0"] <= y <= room["y1"] and room["z0"] - 0.05 <= z < room["z1"]


def clock_at(knots, s):
    for a, b in zip(knots, knots[1:]):
        if a[0] <= s <= b[0]:
            return a[1] + (b[1] - a[1]) * (s - a[0]) / (b[0] - a[0])
    raise AssertionError(f"film time {s} is off the clock")


class World:
    """The run, read the way the planner must read it."""

    def __init__(self, s, tr):
        self.s = s
        self.cz = s["clean_z"]
        cr = [f for f in s["floors"] if f["name"] == "cleanroom"][0]
        self.ceil = self.cz + cr["z1"] - cr["z0"]
        self.states = {}
        for t, i, code in s["states"]:
            self.states.setdefault(i, []).append((t, code))
        self.steps = {}
        for L in tr["lots"]:
            for a, st, e, tool, g in L["steps"]:
                self.steps.setdefault(g, []).append((a, st, L["id"], L["hot"]))

    def state(self, tool, t):
        ch = self.states.get(tool, [])
        k = bisect_right([c[0] for c in ch], t)
        return ch[k - 1][1] if k else 1

    def waiting(self, g, t):
        return sum(1 for a, st, _, _ in self.steps.get(g, []) if a <= t < st)

    def hot_waiting(self, g, t):
        return sorted(lid for a, st, lid, hot in self.steps.get(g, []) if hot and a <= t < st)

    def riding(self, x, t):
        n = 0
        for L in self.s["lots"]:
            k = L["k"]
            if not (k[0][0] <= t <= k[-1][0]):
                continue
            for a, b in zip(k, k[1:]):
                if a[0] <= t <= b[0]:
                    u = 0.0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
                    p = [a[i] + (b[i] - a[i]) * u for i in (1, 2, 3)]
                    if a[1:4] != b[1:4] and p[2] >= self.s["ride_z"] - 0.01 and abs(p[0] - x) <= 15.0:
                        n += 1
                    break
        return n


P = W = None
if PLAN.exists() and SCENE.exists() and TRACE.exists():
    _tmp = tempfile.mkdtemp()
    P = run_plan(Path(_tmp) / "visitor-film.json")
    W = World(json.loads(SCENE.read_text()), json.loads(TRACE.read_text()))


class Source(unittest.TestCase):
    def test_standard_library_and_the_planner_only(self):
        tree = ast.parse(PLAN.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                self.assertTrue(n.split(".")[0] in sys.stdlib_module_names or n == "plan", n)

    def test_it_says_what_it_is(self):
        doc = PLAN.read_text().split('"""')[1]
        for words in ("on the SMT2020 model", "not a real fab", "drawn only"):
            self.assertIn(words, doc, words)


@unittest.skipUnless(P is not None, "no plan, scene or trace")
class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = W.s
        cls.path = P["path"]
        cls.stage = {st["name"]: st for st in P["stages"]}
        cls.rooms = {r["name"]: r for r in P["rooms"]}
        cls.cuts = set(P["cuts"])
        cls.end = cls.path[-1][0]

    def stage_of(self, s):
        for st in P["stages"]:
            if st["s0"] <= s < st["s1"] or (st is P["stages"][-1] and s == st["s1"]):
                return st["name"]
        raise AssertionError(s)

    def act_of(self, s):
        for a in P["acts"]:
            if a["s0"] <= s < a["s1"] or (a is P["acts"][-1] and s == a["s1"]):
                return a
        raise AssertionError(s)

    def pairs(self):
        """Consecutive samples with no cut between them."""
        for a, b in zip(self.path, self.path[1:]):
            if not any(a[0] < c <= b[0] + 1e-9 for c in self.cuts):
                yield a, b

    def furniture(self):
        return [f for r in P["rooms"] for f in r.get("furniture", [])]

    def furn(self, fid):
        f = [f for f in self.furniture() if f["id"] == fid]
        self.assertEqual(len(f), 1, fid)
        return f[0]

    def innermost(self, x, y, z):
        rs = [r for r in P["rooms"] if r["kind"] != "walkway" and in_room(r, x, y, z)]
        return min(rs, key=lambda r: (r["x1"] - r["x0"]) * (r["y1"] - r["y0"])) if rs else None

    # the way in

    def test_the_way_in_is_the_one_people_take(self):
        self.assertEqual([st["name"] for st in P["stages"]], STAGES)
        for a, b in zip(P["stages"], P["stages"][1:]):
            self.assertAlmostEqual(a["s1"], b["s0"])
        self.assertAlmostEqual(P["stages"][0]["s0"], 0.0)
        for name in ("lobby", "lift", "bridge", "gowning", "air shower"):
            self.assertIn(name, self.rooms)
        way_in = self.stage["clean floor"]["s0"]
        self.assertTrue(35.0 <= way_in <= 60.0, f"the way in takes {way_in:.1f} s")

    def test_he_gets_out_of_his_car_and_walks_to_the_door(self):
        park = [c for c in self.s["campus"] if c["kind"] == "parking"][0]
        office = [c for c in self.s["campus"] if c["kind"] == "office"][0]
        car = P["car"]
        self.assertTrue(inside(park, car["x"], car["y"]), "his car is in the car park")
        p0 = self.path[0]
        self.assertLess(math.hypot(p0[1] - car["x"], p0[2] - car["y"]), 3.0, "he starts beside his car")
        self.assertEqual(p0[3], 0.0)
        for p in self.path:
            if self.stage_of(p[0]) == "outside":
                self.assertFalse(inside(office, p[1], p[2], pad=-0.01), "outside he is outside")
        lobby = self.rooms["lobby"]
        self.assertTrue(inside(office, (lobby["x0"] + lobby["x1"]) / 2, (lobby["y0"] + lobby["y1"]) / 2), "the lobby is in the office")

    def test_he_badges_in_and_calls_the_lift(self):
        acts = [a for a in P["acts"] if a["act"] == "interact"]
        self.assertGreaterEqual(len(acts), 2)
        targets = {a["at"] for a in acts}
        self.assertIn("badge reader", targets)
        self.assertIn("lift panel", targets)
        line = self.furn("turnstile line")
        for a in acts:
            f = self.furn(a["at"])
            mid = [p for p in self.path if a["s0"] <= p[0] < a["s1"]][0]
            want = math.atan2((f["y0"] + f["y1"]) / 2 - mid[2], (f["x0"] + f["x1"]) / 2 - mid[1])
            self.assertLess(angle(mid[4], want), math.radians(40), f"he faces the {a['at']}")
            self.assertLess(box_dist(f, mid[1], mid[2]), 1.3, f"he reaches the {a['at']}")
            self.assertGreaterEqual(a["s1"] - a["s0"], 0.75)
        tap = [a for a in acts if a["at"] == "badge reader"][0]
        mid_line = (line["y0"] + line["y1"]) / 2
        before = [p for p in self.path if p[0] < tap["s0"] and self.stage_of(p[0]) == "lobby"]
        self.assertTrue(all(p[2] > mid_line for p in before), "he taps his badge before he passes the line")

    def test_the_lift_takes_him_up_behind_closed_doors(self):
        lift = self.stage["lift"]
        box = self.rooms["lift"]
        here = [p for p in self.path if lift["s0"] <= p[0] < lift["s1"]]
        self.assertTrue(here)
        for p in here:
            self.assertTrue(inside(box, p[1], p[2]), "he rides inside the car")
            self.assertEqual(p[3], 0.0, "the ride itself is not shown: a cut takes him up")
        self.assertIn(self.stage["bridge"]["s0"], self.cuts)
        self.assertTrue(any(a["act"] == "lift" and a["s1"] - a["s0"] >= 1.5 for a in P["acts"]))
        for p in self.path:
            if self.stage_of(p[0]) in ("bridge", "gowning", "air shower", "clean floor"):
                self.assertAlmostEqual(p[3], W.cz, places=6)

    def test_the_bridge_is_walked_down_the_middle(self):
        br = self.rooms["bridge"]
        mid = (br["x0"] + br["x1"]) / 2 if br["x1"] - br["x0"] < br["y1"] - br["y0"] else (br["y0"] + br["y1"]) / 2
        along_y = br["x1"] - br["x0"] < br["y1"] - br["y0"]
        for p in self.path:
            if self.stage_of(p[0]) == "bridge":
                self.assertTrue(inside(br, p[1], p[2]))
                self.assertLess(abs((p[1] if along_y else p[2]) - mid), 0.3, "down the middle")
        self.assertGreaterEqual(self.stage["bridge"]["s1"] - self.stage["bridge"]["s0"], 3.0)

    def test_he_gowns_up(self):
        g = self.stage["gowning"]
        acts = [a for a in P["acts"] if g["s0"] <= a["s0"] < g["s1"]]
        names = [a["act"] for a in acts]
        for want in ("sit_enter", "sit_idle", "mirror"):
            self.assertIn(want, names)
        self.assertLess(names.index("sit_enter"), names.index("sit_idle"))
        self.assertLess(names.index("sit_idle"), names.index("mirror"))
        sit = acts[names.index("sit_idle")]
        self.assertGreaterEqual(sit["s1"] - sit["s0"], 1.5)
        bench = self.furn("bench")
        bc = ((bench["x0"] + bench["x1"]) / 2, (bench["y0"] + bench["y1"]) / 2)
        for p in self.path:
            if sit["s0"] <= p[0] < sit["s1"]:
                self.assertLess(box_dist(bench, p[1], p[2]), 0.6, "he sits on the bench")
                # the bench is behind him: he sits with his back to it, his feet on the dirty side
                away = math.atan2(p[2] - bc[1], p[1] - bc[0])
                self.assertLess(angle(p[4], away), math.radians(45))
        # the time-lapse: a cut after he sits; from there he wears the suit and stands on the clean side
        lapse = [c for c in P["cuts"] if sit["s1"] - 1e-6 <= c < g["s1"]]
        self.assertEqual(len(lapse), 1, "one cut makes the time-lapse")
        wear = sorted(P["outfit"], key=lambda o: o["s"])
        self.assertEqual(wear[0]["wear"], "street")
        self.assertEqual([o["wear"] for o in wear], ["street", "suit"])
        self.assertAlmostEqual(wear[1]["s"], lapse[0])
        line_y = (bench["y0"] + bench["y1"]) / 2
        before = [p for p in self.path if g["s0"] <= p[0] < lapse[0]]
        after = [p for p in self.path if lapse[0] <= p[0] < g["s1"]]
        side = 1 if before[0][2] > line_y else -1
        self.assertTrue(all(side * (p[2] - line_y) > 0 for p in before), "in street clothes he stays on the dirty side")
        self.assertTrue(all(side * (p[2] - line_y) < 0 for p in after), "in the suit he is on the clean side")
        m = acts[names.index("mirror")]
        mirror = self.furn("mirror")
        mc = ((mirror["x0"] + mirror["x1"]) / 2, (mirror["y0"] + mirror["y1"]) / 2)
        self.assertGreaterEqual(m["s1"] - m["s0"], 1.0)
        for p in self.path:
            if m["s0"] <= p[0] < m["s1"]:
                self.assertLess(angle(p[4], math.atan2(mc[1] - p[2], mc[0] - p[1])), math.radians(25), "he faces the mirror")
                self.assertTrue(0.5 <= box_dist(mirror, p[1], p[2]) <= 1.6)
        self.assertTrue(any("shortened" in c["text"] for c in P["captions"] if c["s0"] <= lapse[0] + 1 and c["s1"] >= lapse[0]),
                        "the film says the gowning is shortened")

    def test_the_air_shower(self):
        sh = self.rooms["air shower"]
        acts = [a for a in P["acts"] if a["act"] == "shower"]
        self.assertEqual(len(acts), 1)
        a = acts[0]
        self.assertGreaterEqual(a["s1"] - a["s0"], 2.5)
        for p in self.path:
            if a["s0"] <= p[0] < a["s1"]:
                self.assertTrue(inside(sh, p[1], p[2]), "he stands inside the shower")
        cf = self.stage["clean floor"]["s0"]
        p = min(self.path, key=lambda q: abs(q[0] - cf))
        self.assertLess(box_dist(sh, p[1], p[2]), 1.5, "the clean floor starts at the shower's door")

    # how he moves

    def test_he_speeds_up_and_slows_down(self):
        sp = []
        for a, b in self.pairs():
            sp.append((a[0], math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0])))
        for s, v in sp:
            self.assertLessEqual(v, 1.45, f"{v:.2f} m/s at {s:.2f} s")
        # acceleration from speeds a sample apart (cuts excluded)
        bad = []
        prev = None
        for (s, v) in sp:
            if prev and abs(s - prev[0] - DT) < 1e-6:
                acc = (v - prev[1]) / DT
                if abs(acc) > 1.25:
                    bad.append((round(s, 3), round(acc, 2)))
            prev = (s, v)
        self.assertEqual(bad, [], "no instant starts or stops")

    def test_he_never_slides(self):
        """A turn on the spot is made of steps: his gait distance grows with the turn."""
        for a, b in self.pairs():
            d = math.hypot(b[1] - a[1], b[2] - a[2])
            dg = b[7] - a[7]
            dyaw = angle(b[4], a[4])
            self.assertGreaterEqual(dg, d - 1e-6, f"gait behind the feet at {a[0]:.2f} s")
            self.assertLessEqual(dg, d + 0.35 * dyaw + 1e-6, f"steps in place at {a[0]:.2f} s")
            if d / DT < 0.3 and dyaw / DT > 0.5:
                self.assertGreaterEqual(dg, 0.25 * dyaw - 1e-6, f"he turns without stepping at {a[0]:.2f} s")
        for a, b in zip(self.path, self.path[1:]):
            self.assertGreaterEqual(b[7], a[7] - 1e-9)

    def test_he_faces_where_he_walks_and_turns_like_a_person(self):
        n = ok = 0
        for a, b in self.pairs():
            d = math.hypot(b[1] - a[1], b[2] - a[2])
            self.assertLessEqual(angle(b[4], a[4]) / DT, math.radians(200), f"body spins at {a[0]:.2f} s")
            if d / DT > 0.3:
                n += 1
                ok += angle(a[4], math.atan2(b[2] - a[2], b[1] - a[1])) < math.radians(20)
        self.assertGreaterEqual(ok, 0.97 * n)
        # the walked heading bends, it does not snap
        trips = list(self.pairs())
        for (a, b), (c, d) in zip(trips, trips[1:]):
            if b is not c:
                continue
            v1 = math.hypot(b[1] - a[1], b[2] - a[2]) / DT
            v2 = math.hypot(d[1] - c[1], d[2] - c[2]) / DT
            if v1 > 0.4 and v2 > 0.4:
                h1 = math.atan2(b[2] - a[2], b[1] - a[1])
                h2 = math.atan2(d[2] - c[2], d[1] - c[1])
                self.assertLessEqual(angle(h1, h2) / DT, math.radians(150), f"heading snaps at {b[0]:.2f} s")

    def test_his_head_moves_like_a_head(self):
        for a, b in zip(self.path, self.path[1:]):
            self.assertLessEqual(angle(a[5], a[4]), math.radians(100) + 1e-6)
            if b[0] not in self.cuts:
                self.assertLessEqual(angle(b[5], a[5]) / DT, math.radians(240) + 1e-6, f"head snaps at {a[0]:.2f} s")

    def test_jumps_and_height_changes_only_at_cuts(self):
        for a, b in zip(self.path, self.path[1:]):
            if any(a[0] < c <= b[0] + 1e-9 for c in self.cuts):
                continue
            self.assertLess(math.hypot(b[1] - a[1], b[2] - a[2]), 0.25, f"a jump at {a[0]:.2f} s")
            self.assertEqual(a[3], b[3], f"height changes at {a[0]:.2f} s")

    def test_acts_tile_the_film_and_still_acts_stand_still(self):
        acts = P["acts"]
        self.assertAlmostEqual(acts[0]["s0"], 0.0)
        self.assertAlmostEqual(acts[-1]["s1"], self.end)
        for a, b in zip(acts, acts[1:]):
            self.assertAlmostEqual(a["s1"], b["s0"])
        for a in acts:
            self.assertIn(a["act"], ACTS)
            self.assertGreater(a["s1"], a["s0"])
        for a, b in self.pairs():
            if self.act_of(a[0])["act"] in STILL and self.act_of(b[0])["act"] in STILL:
                self.assertLess(math.hypot(b[1] - a[1], b[2] - a[2]), 1e-6, f"he moves during {self.act_of(a[0])['act']} at {a[0]:.2f}")

    # indoors: walls, doors, furniture

    def test_doors_are_walked_through_square_on_and_in_the_middle(self):
        crossed = 0
        for a, b in self.pairs():
            if self.stage_of(a[0]) not in WAY_IN and self.stage_of(b[0]) not in WAY_IN:
                continue
            for r in P["rooms"]:
                if r["kind"] == "walkway" or not (r["z0"] - 0.05 <= a[3] < r["z1"]):
                    continue
                for side, c, ax, lo, hi, nrm in walls(r):
                    pa = a[2] if ax == 0 else a[1]  # across the wall
                    pb = b[2] if ax == 0 else b[1]
                    if (pa - c) * (pb - c) >= 0 or pa == pb:
                        continue
                    u = (c - pa) / (pb - pa)
                    along = (a[1] + (b[1] - a[1]) * u) if ax == 0 else (a[2] + (b[2] - a[2]) * u)
                    if not lo <= along <= hi:
                        continue
                    crossed += 1
                    doors = [d for d in r.get("doors", []) if d["wall"] == side and abs(along - d["at"]) <= d["w"] / 2 - 0.25]
                    self.assertTrue(doors, f"through the {r['name']}'s {side} wall at {along:.2f} ({a[0]:.2f} s)")
                    h = math.atan2(b[2] - a[2], b[1] - a[1])
                    self.assertLess(min(angle(h, math.atan2(nrm[1], nrm[0])), angle(h, math.atan2(-nrm[1], -nrm[0]))),
                                    math.radians(25), f"askew through the {r['name']}'s door ({a[0]:.2f} s)")
        self.assertGreaterEqual(crossed, 6, "he goes through the doors of the way in")

    def test_he_keeps_clear_of_walls(self):
        for p in self.path:
            if self.stage_of(p[0]) not in WAY_IN or self.stage_of(p[0]) == "outside":
                continue
            r = self.innermost(p[1], p[2], p[3])
            self.assertIsNotNone(r, f"in no room at {p[0]:.2f} s")
            for side, c, ax, lo, hi, nrm in walls(r):
                across = p[2] if ax == 0 else p[1]
                along = p[1] if ax == 0 else p[2]
                if any(d["wall"] == side and abs(along - d["at"]) <= d["w"] / 2 for d in r.get("doors", [])):
                    continue
                self.assertGreaterEqual(abs(across - c), 0.35, f"{abs(across - c):.2f} m from the {r['name']}'s {side} wall at {p[0]:.2f} s")

    def test_he_keeps_clear_of_furniture(self):
        for p in self.path:
            for f in self.furniture():
                if not (f["z0"] < p[3] + 1.8 and f["z1"] > p[3]):  # beside his body, not a mark on the floor
                    continue
                if f["id"] == "bench" and self.act_of(p[0])["act"] in ("sit_enter", "sit_idle"):
                    continue
                self.assertGreaterEqual(box_dist(f, p[1], p[2]), 0.25, f"into the {f['id']} at {p[0]:.2f} s")

    # the clean floor

    def test_he_never_walks_through_a_tool(self):
        for p in self.path:
            if self.stage_of(p[0]) != "clean floor":
                continue
            for t in self.s["tools"]:
                self.assertFalse(inside(t, p[1], p[2], pad=0.5), f"within 0.5 m of a tool at {p[0]:.2f} s")
            for st in self.s["stockers"]:
                self.assertFalse(inside(st, p[1], p[2], pad=0.5), f"within 0.5 m of a stocker at {p[0]:.2f} s")

    def test_the_run_decides(self):
        sights = P["sights"]
        self.assertGreaterEqual(len(sights), 4)
        self.assertGreaterEqual(len({x["kind"] for x in sights}), 3)
        self.assertLessEqual({x["kind"] for x in sights}, KINDS)
        self.assertEqual(len({x["key"] for x in sights}), len(sights))
        seen_kinds, seen_groups, seen_places = [], set(), set()
        prev = self.stage["clean floor"]["s0"]
        for x in sights:
            if x["tool"] is not None:
                self.assertEqual(x["place"], f"bay:{self.s['tools'][x['tool']]['bay']}")
            k = seen_kinds.count(x["kind"])
            nov = (1.0 / (1 + k)) * (0.3 if x["group"] is not None and x["group"] in seen_groups else 1.0) \
                * (0.5 if x["place"] in seen_places else 1.0)
            self.assertAlmostEqual(x["novelty"], nov, places=6, msg=x["key"])
            self.assertAlmostEqual(x["score"], x["severity"] * x["novelty"] / (1 + x["walk_s"] / 15.0), places=6)
            self.assertAlmostEqual(x["walk_s"], x["arrive_s"] - prev, delta=1e-6, msg="walk_s is the walk he makes")
            c = x["candidates"]
            self.assertGreaterEqual(len(c), 2)
            self.assertEqual(c[0]["key"], x["key"])
            for o in c:
                self.assertAlmostEqual(o["score"], o["severity"] * o["novelty"] / (1 + o["walk_s"] / 15.0), places=6)
                self.assertLessEqual(o["score"], x["score"] + 1e-9)
            seen_kinds.append(x["kind"])
            seen_places.add(x["place"])
            if x["group"] is not None:
                seen_groups.add(x["group"])
            prev = x["leave_s"]

    def test_every_sight_is_in_the_run_when_he_gets_there(self):
        for x in P["sights"]:
            t = clock_at(P["clock"], x["arrive_s"])
            self.assertAlmostEqual(t, x["t_arrive"], delta=1e-3)
            n = x["numbers"]
            g = x["group"]
            if g is not None:
                self.assertEqual(n["waiting"], W.waiting(g, t), x["key"])
            k = x["kind"]
            if k == "breakdown":
                self.assertEqual(W.state(x["tool"], t), 3)
                sev = 3 + n["waiting"] / 10
            elif k == "maintenance":
                self.assertEqual(W.state(x["tool"], t), 2)
                sev = 1.5 + n["waiting"] / 10
            elif k == "queue":
                self.assertGreaterEqual(n["waiting"], 10)
                sev = n["waiting"] / 10
            elif k == "hot":
                self.assertIn(n["lot"], W.hot_waiting(g, t))
                sev = 2 + n["waiting"] / 20
            else:
                self.assertEqual(n["riding"], W.riding(x["look"][0], t))
                sev = n["riding"] / 5
            self.assertAlmostEqual(x["severity"], sev, places=6, msg=x["key"])

    def test_he_stops_to_watch_and_faces_it(self):
        for x in P["sights"]:
            self.assertGreaterEqual(x["leave_s"] - x["arrive_s"], 6.0)
            v, lk = x["view"], x["look"]
            want = math.atan2(lk[1] - v[1], lk[0] - v[0])
            for p in self.path:
                if x["arrive_s"] + 1.0 <= p[0] <= x["leave_s"]:
                    self.assertLess(math.hypot(p[1] - v[0], p[2] - v[1]), 0.05)
                    self.assertLess(angle(p[5], want), math.radians(10), "his eyes on it")
                if x["arrive_s"] + 2.0 <= p[0] <= x["leave_s"]:
                    self.assertLess(angle(p[4], want), math.radians(35), "he turns toward it")
            # his eyes get there first
            win = [p for p in self.path if x["arrive_s"] - 3 <= p[0] <= x["leave_s"]]
            th = next(p[0] for p in win if angle(p[5], want) < math.radians(10))
            tb = next(p[0] for p in win if angle(p[4], want) < math.radians(35))
            self.assertLessEqual(th, tb, x["key"])

    def test_the_clock(self):
        k = P["clock"]
        for a, b in zip(k, k[1:]):
            self.assertGreater(b[0], a[0])
            self.assertGreater(b[1], a[1])
        self.assertGreaterEqual(k[0][1], self.s["from"])
        self.assertLessEqual(k[-1][1], self.s["to"])
        self.assertGreaterEqual(k[-1][0], self.end)
        rw, rv = P["clock_rate"]["walk"] / 60.0, P["clock_rate"]["watch"] / 60.0
        for x in P["sights"]:
            d = clock_at(k, x["leave_s"]) - clock_at(k, x["arrive_s"])
            self.assertAlmostEqual(d / (x["leave_s"] - x["arrive_s"]), rv, places=6)

    # the camera

    def test_the_camera_keeps_him_in_frame(self):
        cam = P["camera"]
        self.assertEqual(len(cam), len(self.path))
        for c, p in zip(cam, self.path):
            self.assertAlmostEqual(c[0], p[0])
            self.assertIn(c[7], ("shoulder", "wide", "fixed"))
            me = (p[1], p[2], p[3] + 1.2)
            d = math.dist(c[1:4], me)
            self.assertTrue(1.4 <= d <= 16.0, f"camera {d:.1f} m from him at {c[0]:.2f} s")
            look = [c[4] - c[1], c[5] - c[2], c[6] - c[3]]
            self.assertLessEqual(ang3(look, [me[i] - c[1 + i] for i in range(3)]), 22.0, f"he is out of frame at {c[0]:.2f} s")

    def test_the_camera_glides(self):
        cam = P["camera"]
        for a, b in zip(cam, cam[1:]):
            if b[0] in self.cuts or a[7] != b[7]:
                continue
            v = math.dist(a[1:4], b[1:4]) / DT
            self.assertLessEqual(v, 3.0, f"camera jumps {v:.1f} m/s at {a[0]:.2f} s")

    def test_the_camera_stays_in_the_room_and_out_of_things(self):
        sp, depth = self.s["spine"], self.s["depth"]
        for c, p in zip(P["camera"], self.path):
            x, y, z = c[1], c[2], c[3]
            st = self.stage_of(p[0])
            for f in self.furniture():
                self.assertFalse(inside(f, x, y, pad=0.15) and f["z0"] - 0.15 <= z <= f["z1"] + 0.15, f"camera in the {f['id']} at {c[0]:.2f} s")
            if st in WAY_IN and st != "outside":
                r = self.innermost(p[1], p[2], p[3])
                self.assertTrue(r["x0"] + 0.2 <= x <= r["x1"] - 0.2 and r["y0"] + 0.2 <= y <= r["y1"] - 0.2
                                and r["z0"] + 0.3 <= z <= r["z1"] - 0.2, f"camera outside the {r['name']} at {c[0]:.2f} s")
            if st == "outside":
                for b in self.s["campus"]:
                    if b["kind"] not in ("road", "parking"):
                        self.assertFalse(inside(b, x, y), f"camera inside the {b['kind']} at {c[0]:.2f} s")
            if st == "clean floor":
                for t in self.s["tools"]:
                    if z < W.cz + t["h"] + 0.3:
                        self.assertFalse(inside(t, x, y, pad=0.25), f"camera in a tool at {c[0]:.2f} s")
                for s_ in self.s["stockers"]:
                    self.assertFalse(inside(s_, x, y, pad=0.25))
                self.assertTrue(W.cz + 0.5 <= z <= W.ceil - 0.3)
                ok = any(ox < x < ox + L and abs(y) < sp / 2 + depth for ox, L in zip(self.s["offsets"], self.s["lengths"]))
                ok = ok or any(in_room(r, x, y, z) for r in P["rooms"])
                self.assertTrue(ok, f"camera off the clean floor at {c[0]:.2f} s")

    def test_the_sight_is_in_frame_while_he_watches(self):
        for x in P["sights"]:
            for c in P["camera"]:
                if x["arrive_s"] + 1.5 <= c[0] <= x["leave_s"]:
                    look = [c[4] - c[1], c[5] - c[2], c[6] - c[3]]
                    to = [x["look"][i] - c[1 + i] for i in range(3)]
                    self.assertLessEqual(ang3(look, to), 22.0, f"{x['key']} out of frame at {c[0]:.2f} s")

    # what it says, and how long

    def test_cards_and_captions(self):
        for x in P["sights"]:
            c = [cd for cd in P["cards"] if cd["sight"] == x["key"]]
            self.assertEqual(len(c), 1)
            text = c[0]["title"] + " " + " ".join(c[0]["lines"])
            if x["group"] is not None:
                self.assertIn(self.s["groups"][x["group"]]["name"], text)
                self.assertIn(str(x["numbers"]["waiting"]), text)
            self.assertIn("SMT2020 model", text)
        for c in P["captions"]:
            self.assertLess(c["s0"], c["s1"])
            self.assertNotIn("TSMC", c["text"])
        for words in ("on the SMT2020 model", "not a real fab", "drawn only"):
            self.assertIn(words, P["badge"])

    def test_about_two_minutes(self):
        self.assertTrue(105.0 <= self.end <= 135.0, f"{self.end:.1f} s")
        self.assertEqual(P["fps"], 24)
        self.assertAlmostEqual(P["dt"], DT)

    def test_the_same_seed_gives_the_same_plan(self):
        with tempfile.TemporaryDirectory() as d:
            a = run_plan(Path(d) / "a.json")
        self.assertEqual(a, P)


if __name__ == "__main__":
    unittest.main()
