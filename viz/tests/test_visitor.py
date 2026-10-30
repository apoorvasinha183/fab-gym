"""Tests for the visitor's walk-through ("A Walk Through the Fab"): viz/visitor/plan.py.

A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. A visitor parks,
walks to the office door, takes the lift, crosses the link bridge, gowns up, goes through the
air shower and steps onto the clean floor. From there the run decides where he goes: every sight
he can reach is scored by how serious it is, how new it is and how far he must walk, and he goes
to the best one. The planner writes his route, his gaze, the camera and the cards as data
(data/layout-real/visitor.json); Godot plays it live and Blender renders it. The visitor is
drawn only: he is not in the model and no number comes from him. Standard library only:

    python3 -m unittest viz.tests.test_visitor      (from the repo root)

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
PLAN = ROOT / "viz/visitor/plan.py"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
TRACE = ROOT / "data/layout-real/trace-optimised.json"

STAGES = ["outside", "lobby", "lift", "link", "gowning", "air shower", "clean floor"]
EYE = 1.6  # the visitor's eye above his feet (drawn 1.75 m tall)
KINDS = {"breakdown", "maintenance", "queue", "hot", "hoist"}


def run_plan(out, seed=7):
    subprocess.run([sys.executable, str(PLAN), str(SCENE), str(TRACE), str(out), "--seed", str(seed)],
                   check=True, timeout=600)
    return json.loads(Path(out).read_text())


def angle(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


def ang3(u, v):
    nu = math.sqrt(sum(c * c for c in u))
    nv = math.sqrt(sum(c * c for c in v))
    c = sum(p * q for p, q in zip(u, v)) / (nu * nv)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def inside(box, x, y, pad=0.0):
    return box["x0"] - pad < x < box["x1"] + pad and box["y0"] - pad < y < box["y1"] + pad


def inside3(box, x, y, z, tol=0.05):
    return (box["x0"] - tol <= x <= box["x1"] + tol and box["y0"] - tol <= y <= box["y1"] + tol
            and box["z0"] - tol <= z <= box["z1"] + tol)


class World:
    """The run, read the way the planner must read it."""

    def __init__(self, s, tr):
        self.s, self.tr = s, tr
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
                    # moving on the rail: lots parked on shelves sit at the same height
                    if a[1:4] != b[1:4] and p[2] >= self.s["ride_z"] - 0.01 and abs(p[0] - x) <= 15.0:
                        n += 1
                    break
        return n


def clock_at(knots, s):
    for a, b in zip(knots, knots[1:]):
        if a[0] <= s <= b[0]:
            return a[1] + (b[1] - a[1]) * (s - a[0]) / (b[0] - a[0])
    raise AssertionError(f"film time {s} is off the clock")


P = W = None
if PLAN.exists() and SCENE.exists() and TRACE.exists():
    _tmp = tempfile.mkdtemp()
    P = run_plan(Path(_tmp) / "visitor.json")
    W = World(json.loads(SCENE.read_text()), json.loads(TRACE.read_text()))


class Source(unittest.TestCase):
    def test_standard_library_only(self):
        tree = ast.parse(PLAN.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                self.assertIn(n.split(".")[0], sys.stdlib_module_names, n)

    def test_it_says_what_it_is(self):
        doc = PLAN.read_text().split('"""')[1]
        for words in ("from the SMT2020 testbed", "not a real fab", "drawn only"):
            self.assertIn(words, doc, words)


@unittest.skipUnless(P is not None, "no plan, scene or trace")
class Plan(unittest.TestCase):
    def setUp(self):
        self.s = W.s
        self.path = P["path"]
        self.rooms = {r["name"]: r for r in P["rooms"]}
        self.stage = {st["name"]: st for st in P["stages"]}

    def samples(self, name):
        # stages are half-open, the last one closed
        st = self.stage[name]
        last = name == STAGES[-1]
        return [p for p in self.path if st["s0"] <= p[0] < st["s1"] or (last and p[0] == st["s1"])]

    # the way in

    def test_he_comes_in_the_way_people_do(self):
        self.assertEqual([st["name"] for st in P["stages"]], STAGES)
        for a, b in zip(P["stages"], P["stages"][1:]):
            self.assertAlmostEqual(a["s1"], b["s0"], delta=1e-6)
        self.assertAlmostEqual(P["stages"][0]["s0"], 0.0)
        self.assertGreaterEqual(self.stage["gowning"]["s1"] - self.stage["gowning"]["s0"], 3.0)
        self.assertGreaterEqual(self.stage["air shower"]["s1"] - self.stage["air shower"]["s0"], 2.0)
        park = [c for c in self.s["campus"] if c["kind"] == "parking"][0]
        first = self.path[0]
        self.assertTrue(inside(park, first[1], first[2]), "he starts at his car in the car park")
        self.assertAlmostEqual(first[3], 0.0, delta=0.01)
        for p in self.samples("clean floor"):
            self.assertAlmostEqual(p[3], W.cz, delta=0.01)

    def test_each_room_holds_him_in_its_turn(self):
        for name in STAGES[1:-1]:
            box = self.rooms[name]
            for p in self.samples(name):
                self.assertTrue(inside3(box, p[1], p[2], p[3]), f"{name}: {p}")
        # outside he walks on the ground, never through a building
        for p in self.samples("outside"):
            self.assertAlmostEqual(p[3], 0.0, delta=0.01)
            for c in self.s["campus"]:
                if c["kind"] in ("fab", "office", "cub", "upw", "gas", "pad"):
                    self.assertFalse(inside(c, p[1], p[2], pad=-0.3), (c["name"], p))
        # the link bridge reaches from the office to the fab at clean-floor height, over the road
        link = self.rooms["link"]
        office = [c for c in self.s["campus"] if c["kind"] == "office"][0]
        self.assertAlmostEqual(link["z0"], W.cz, delta=0.01)
        self.assertLessEqual(link["y0"], self.s["spine"] / 2 + self.s["depth"] + 6.01)
        self.assertGreaterEqual(link["y1"], office["y0"] - 0.01)

    def test_the_film_cuts_only_on_the_way_in(self):
        # the office hall and the bridge are long; the film cuts between rooms, never on the clean floor
        allowed = {self.stage[n]["s0"] for n in ("lobby", "link")}
        for c in P["cuts"]:
            self.assertIn(c, allowed)

    def test_the_lift_lifts_and_the_rest_is_walked(self):
        cuts = set(P["cuts"])
        for a, b in zip(self.path, self.path[1:]):
            dt = b[0] - a[0]
            self.assertGreater(dt, 0)
            if b[0] in cuts:
                continue
            v = math.hypot(b[1] - a[1], b[2] - a[2]) / dt
            self.assertLessEqual(v, 1.5 + 1e-6, f"too fast at {a[0]:.2f} s: {v:.2f} m/s")
            dz = abs(b[3] - a[3])
            if dz > 1e-6:
                lift = self.stage["lift"]
                self.assertTrue(lift["s0"] - 1e-6 <= a[0] and b[0] <= lift["s1"] + 1e-6, "only the lift changes height")

    # on the clean floor

    def test_he_never_walks_through_a_tool(self):
        sp, depth = self.s["spine"], self.s["depth"]
        walk_rooms = [r for r in P["rooms"] if r["kind"] == "walkway"] + [self.rooms["air shower"]]
        for p in self.samples("clean floor"):
            x, y = p[1], p[2]
            for t in self.s["tools"]:
                self.assertFalse(inside(t, x, y, pad=0.3), f"inside a tool at {x:.2f}, {y:.2f}")
            for st in self.s["stockers"]:
                self.assertFalse(inside(st, x, y, pad=0.3), f"inside a stocker at {x:.2f}, {y:.2f}")
            ok = False
            for ph, (ox, L) in enumerate(zip(self.s["offsets"], self.s["lengths"])):
                if ox < x < ox + L and abs(y) < sp / 2 + depth:
                    ok = True
            ok = ok or any(inside3(r, x, y, p[3]) for r in walk_rooms)
            self.assertTrue(ok, f"off the floor at {x:.2f}, {y:.2f}")

    def test_he_faces_the_way_he_walks(self):
        good = n = 0
        for a, b in zip(self.path, self.path[1:]):
            dx, dy = b[1] - a[1], b[2] - a[2]
            if math.hypot(dx, dy) / (b[0] - a[0]) < 0.5:
                continue
            n += 1
            good += angle(a[4], math.atan2(dy, dx)) < math.radians(25)
        self.assertGreater(n, 100)
        self.assertGreaterEqual(good / n, 0.95)

    # what he goes to see

    def test_the_run_decides(self):
        sights = P["sights"]
        self.assertGreaterEqual(len(sights), 5, "he sees the fab working, not one tool")
        self.assertGreaterEqual(len({x["kind"] for x in sights}), 3)
        self.assertLessEqual({x["kind"] for x in sights}, KINDS)
        self.assertEqual(len({x["key"] for x in sights}), len(sights), "never the same sight twice")
        seen_kinds, seen_groups, seen_places = [], set(), set()
        for x in sights:
            if x["tool"] is not None:
                self.assertEqual(x["place"], f"bay:{self.s['tools'][x['tool']]['bay']}")
            else:
                self.assertTrue(x["place"].startswith("spine:"), x["place"])
            k = seen_kinds.count(x["kind"])
            nov = (1.0 / (1 + k)) * (0.3 if x["group"] is not None and x["group"] in seen_groups else 1.0) \
                * (0.5 if x["place"] in seen_places else 1.0)
            self.assertAlmostEqual(x["novelty"], nov, places=6, msg=x["key"])
            self.assertAlmostEqual(x["score"], x["severity"] * x["novelty"] / (1 + x["walk_s"] / 15.0), places=6)
            c = x["candidates"]
            self.assertGreaterEqual(len(c), 2, "he had a choice")
            self.assertEqual(c[0]["key"], x["key"])
            for o in c:
                self.assertAlmostEqual(o["score"], o["severity"] * o["novelty"] / (1 + o["walk_s"] / 15.0), places=6)
                self.assertLessEqual(o["score"], x["score"] + 1e-9, (o["key"], x["key"]))
            seen_kinds.append(x["kind"])
            seen_places.add(x["place"])
            if x["group"] is not None:
                seen_groups.add(x["group"])
        self.assertGreaterEqual(len(seen_places), 4, "he moves on through the fab")

    def test_every_sight_is_in_the_run_when_he_gets_there(self):
        for x in P["sights"]:
            t = clock_at(P["clock"], x["arrive_s"])
            self.assertAlmostEqual(t, x["t_arrive"], delta=1e-3)
            n = x["numbers"]
            g = x["group"]
            if g is not None:
                self.assertEqual(n["waiting"], W.waiting(g, t), x["key"])
            if x["tool"] is not None:
                self.assertEqual(self.s["tools"][x["tool"]]["g"], g)
            k = x["kind"]
            if k == "breakdown":
                self.assertEqual(W.state(x["tool"], t), 3, x["key"])
                sev = 3 + n["waiting"] / 10
            elif k == "maintenance":
                self.assertEqual(W.state(x["tool"], t), 2, x["key"])
                sev = 1.5 + n["waiting"] / 10
            elif k == "queue":
                self.assertGreaterEqual(n["waiting"], 10)
                sev = n["waiting"] / 10
            elif k == "hot":
                self.assertIn(n["lot"], W.hot_waiting(g, t), x["key"])
                sev = 2 + n["waiting"] / 20
            else:
                self.assertEqual(n["riding"], W.riding(x["look"][0], t), x["key"])
                self.assertGreaterEqual(n["riding"], 3)
                sev = n["riding"] / 5
            self.assertAlmostEqual(x["severity"], sev, places=6, msg=x["key"])

    def test_he_walks_there_and_stays_to_watch(self):
        prev = self.stage["clean floor"]["s0"]
        for x in P["sights"]:
            self.assertGreaterEqual(x["leave_s"] - x["arrive_s"], 6.0, x["key"])
            got = 0.0
            pts = [p for p in self.path if prev <= p[0] <= x["arrive_s"]]
            for a, b in zip(pts, pts[1:]):
                got += math.hypot(b[1] - a[1], b[2] - a[2])
            self.assertAlmostEqual(got, x["walk_s"] * P["speed"], delta=0.03 * got + 1.0, msg=x["key"])
            here = [p for p in self.path if x["arrive_s"] <= p[0] <= x["leave_s"]]
            for p in here:
                self.assertLess(math.hypot(p[1] - x["view"][0], p[2] - x["view"][1]), 0.05, "he stands still to watch")
            prev = x["leave_s"]

    def test_his_head_turns_before_his_body(self):
        prev = self.stage["clean floor"]["s0"]
        for x in P["sights"]:
            v, lk = x["view"], x["look"]
            want = math.atan2(lk[1] - v[1], lk[0] - v[0])
            at = min(self.path, key=lambda p: abs(p[0] - x["arrive_s"]))
            self.assertGreaterEqual(angle(at[4], want), math.radians(30), f"{x['key']}: he turns to face it")
            win = [p for p in self.path if max(prev, x["arrive_s"] - 3) < p[0] <= x["leave_s"]]
            tb = next(p[0] for p in win if p[0] >= x["arrive_s"] and angle(p[4], want) < math.radians(10))
            # the head reaches the sight and stays on it before the body gets there
            off = [p[0] for p in win if p[0] <= tb and angle(p[5], want) >= math.radians(10)]
            th = min(p[0] for p in win if p[0] > (off[-1] if off else -1))
            self.assertLess(th, tb, x["key"])
            if x["kind"] == "hoist":
                mid = [p for p in win if p[0] >= x["arrive_s"] + 2]
                self.assertTrue(any(p[6] > math.radians(12) for p in mid), "he looks up at the hoist")
            prev = x["leave_s"]

    def test_the_clock_runs_fast_while_he_walks_and_slow_while_he_watches(self):
        k = P["clock"]
        for a, b in zip(k, k[1:]):
            self.assertGreater(b[0], a[0])
            self.assertGreater(b[1], a[1])
        self.assertGreaterEqual(k[0][1], self.s["from"])
        self.assertLessEqual(k[-1][1], self.s["to"])
        self.assertAlmostEqual(k[0][0], 0.0)
        self.assertGreaterEqual(k[-1][0], self.path[-1][0])
        rw, rv = P["clock_rate"]["walk"] / 60.0, P["clock_rate"]["watch"] / 60.0
        self.assertGreater(rw, 4 * rv)
        prev = self.stage["clean floor"]["s0"]
        for x in P["sights"]:
            d = clock_at(k, x["leave_s"]) - clock_at(k, x["arrive_s"])
            self.assertAlmostEqual(d / (x["leave_s"] - x["arrive_s"]), rv, places=6)
            if x["arrive_s"] - prev > 1:
                d = clock_at(k, x["arrive_s"]) - clock_at(k, prev)
                self.assertAlmostEqual(d / (x["arrive_s"] - prev), rw, places=6)
            prev = x["leave_s"]

    # how it is seen

    def test_the_camera_looks_over_his_shoulder(self):
        cam = P["camera"]
        self.assertEqual(cam[0][0], 0.0)
        self.assertGreaterEqual(cam[-1][0], self.path[-1][0])
        modes = {c[7] for c in cam}
        self.assertLessEqual(modes, {"shoulder", "wide", "fixed"})
        lift = self.stage["lift"]
        pos = {round(p[0], 4): p for p in self.path}
        n = 0
        for c in cam:
            p = pos.get(round(c[0], 4))
            if p is None:
                continue
            head = (p[1], p[2], p[3] + EYE)
            d = math.dist(c[1:4], head)
            if c[7] == "fixed":
                self.assertTrue(lift["s0"] - 1e-6 <= c[0] <= lift["s1"] + 1e-6, "a fixed shot only while the lift rises")
                continue
            if c[7] == "shoulder":
                n += 1
                self.assertTrue(1.5 <= d <= 4.0, f"camera {d:.2f} m from him at {c[0]:.2f} s")
            look = [c[4] - c[1], c[5] - c[2], c[6] - c[3]]
            to_him = [head[0] - c[1], head[1] - c[2], head[2] - c[3]]
            self.assertLessEqual(ang3(look, to_him), 20.0, f"he is out of frame at {c[0]:.2f} s")
        self.assertGreater(n, 0.6 * len(cam))

    def test_the_sight_is_in_frame_while_he_watches(self):
        for x in P["sights"]:
            for c in P["camera"]:
                if x["arrive_s"] + 1.5 <= c[0] <= x["leave_s"] and c[7] in ("shoulder", "wide"):
                    look = [c[4] - c[1], c[5] - c[2], c[6] - c[3]]
                    to = [x["look"][i] - c[1 + i] for i in range(3)]
                    self.assertLessEqual(ang3(look, to), 20.0, f"{x['key']} out of frame at {c[0]:.2f} s")

    def test_the_camera_never_enters_a_tool_or_leaves_the_building(self):
        sp, depth = self.s["spine"], self.s["depth"]
        cf = self.stage["clean floor"]
        rooms = list(P["rooms"])
        for c in P["camera"]:
            x, y, z = c[1], c[2], c[3]
            for t in self.s["tools"]:
                if z < W.cz + t["h"] + 0.3:
                    self.assertFalse(inside(t, x, y, pad=0.2), f"camera in a tool at {c[0]:.2f} s")
            for st in self.s["stockers"]:
                self.assertFalse(inside(st, x, y, pad=0.2), f"camera in a stocker at {c[0]:.2f} s")
            if c[0] > cf["s0"] + 0.5:
                self.assertTrue(W.cz + 0.5 <= z <= W.ceil - 0.3, f"camera at {z:.2f} m at {c[0]:.2f} s")
                ok = any(ox < x < ox + L and abs(y) < sp / 2 + depth for ox, L in zip(self.s["offsets"], self.s["lengths"]))
                ok = ok or any(inside3(r, x, y, z) for r in rooms)
                self.assertTrue(ok, f"camera outside the clean floor at {c[0]:.2f} s: {x:.1f}, {y:.1f}")

    def test_big_moments_cut_wide(self):
        cam = P["camera"]
        runs, cur = [], None
        for a, b in zip(cam, cam[1:]):
            if a[7] == "wide":
                cur = cur or [a[0], a[0]]
                cur[1] = b[0]
            elif cur:
                runs.append(cur)
                cur = None
        if cur:
            runs.append(cur)
        self.assertGreaterEqual(len(runs), 2)
        for r in runs:
            self.assertGreaterEqual(r[1] - r[0], 2.0)
        for x in P["sights"]:
            if x["kind"] == "breakdown":
                self.assertTrue(any(r[0] <= x["arrive_s"] + 3 and r[1] >= x["arrive_s"] for r in runs), x["key"])

    # what it says

    def test_cards_give_the_runs_numbers(self):
        cards = P["cards"]
        for x in P["sights"]:
            c = [cd for cd in cards if cd["sight"] == x["key"]]
            self.assertEqual(len(c), 1, x["key"])
            c = c[0]
            self.assertLessEqual(c["s0"], x["arrive_s"] + 0.5)
            self.assertGreaterEqual(c["s1"], x["leave_s"] - 0.5)
            text = c["title"] + " " + " ".join(c["lines"])
            if x["group"] is not None:
                self.assertIn(self.s["groups"][x["group"]]["name"], text)
                self.assertIn(str(x["numbers"]["waiting"]), text)
            if x["kind"] == "hoist":
                self.assertIn(str(x["numbers"]["riding"]), text)
            self.assertIn("SMT2020 testbed", text)

    def test_the_badge(self):
        for words in ("from the SMT2020 testbed", "not a real fab", "drawn only"):
            self.assertIn(words, P["badge"], words)

    def test_it_is_one_short_piece(self):
        self.assertLessEqual(self.path[-1][0], 240.0)
        self.assertGreaterEqual(self.path[-1][0], 60.0)
        self.assertEqual(P["fps"], 24)

    def test_the_same_seed_gives_the_same_plan(self):
        with tempfile.TemporaryDirectory() as d:
            a = run_plan(Path(d) / "a.json")
            b = run_plan(Path(d) / "b.json")
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(P, sort_keys=True))


# ---------------------------------------------------------------- Godot plays the plan

GPROJ = ROOT / "viz/godot-real"
GREPORT = ROOT / "data/layout-real/visitor-check.json"


def godot_report():
    import os
    g = os.environ.get("GODOT")
    if g and P is not None:
        subprocess.run(["sh", str(GPROJ / "sync.sh")], cwd=ROOT, check=True)
        subprocess.run([g, "--headless", "--path", str(GPROJ), "--", "--fab", "concept", "--visitor-check", str(GREPORT)],
                       check=True, timeout=900)
    return json.loads(GREPORT.read_text()) if GREPORT.exists() else None


class GodotSource(unittest.TestCase):
    def test_the_explore_scene_has_a_visitor_mode(self):
        main = (GPROJ / "main.gd").read_text()
        self.assertIn("res://visitor.gd", main)
        self.assertIn("KEY_V", main)
        self.assertIn("V visitor", main)
        v = (GPROJ / "visitor.gd").read_text()
        self.assertIn("res://data/visitor.json", v)
        self.assertIn("hazmat.glb", v)
        for words in ("from the SMT2020 testbed", "not a real fab", "drawn only"):
            self.assertIn(words, v, words)

    def test_sync_copies_the_plan_and_the_model(self):
        sync = (GPROJ / "sync.sh").read_text()
        self.assertIn("visitor.json", sync)
        self.assertIn("character-hazmat.glb", sync)


G = godot_report() if P is not None else None


def anim_at(path, s):
    for a, b in zip(path, path[1:]):
        if a[0] <= s < b[0]:
            return "walk" if math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0]) > 0.3 else "idle"
    return "idle"


@unittest.skipUnless(G is not None and P is not None, "no Godot and no visitor check report")
class GodotPlays(unittest.TestCase):
    def test_it_plays_this_plan(self):
        self.assertEqual(G["seed"], P["seed"])
        self.assertEqual(G["rooms"], len(P["rooms"]))
        for words in ("from the SMT2020 testbed", "not a real fab", "drawn only"):
            self.assertIn(words, G["badge"], words)

    def test_the_visitor_is_the_hazmat_suit_and_nothing_else(self):
        m = G["model"]
        self.assertEqual(sorted(m["meshes"]), ["Character_Hazmat", "Character_Hazmat_Head"])
        self.assertTrue(1.70 <= m["height"] <= 1.80, m["height"])

    def test_he_is_where_the_plan_puts_him(self):
        path = {round(p[0], 4): p for p in P["path"]}
        cam = {round(c[0], 4): c for c in P["camera"]}
        smp = G["samples"]
        self.assertGreaterEqual(len(smp), 24)
        stages = {st["name"] for st in P["stages"] for x in smp if st["s0"] <= x["s"] < st["s1"]}
        self.assertEqual(stages, set(STAGES[:-1]) | ({"clean floor"} & stages) | {"clean floor"})
        for x in smp:
            p = path[round(x["s"], 4)]
            for a, b in zip(x["pos"], p[1:4]):
                self.assertAlmostEqual(a, b, delta=0.02, msg=f"at {x['s']} s")
            self.assertLess(angle(x["body"], p[4]), math.radians(2), f"body at {x['s']} s")
            c = cam[round(x["s"], 4)]
            for a, b in zip(x["cam"], c[1:4]):
                self.assertAlmostEqual(a, b, delta=0.02, msg=f"camera at {x['s']} s")
            want = [c[4 + i] - c[1 + i] for i in range(3)]
            self.assertLess(ang3(x["look"], want), 1.0, f"camera aim at {x['s']} s")
            self.assertAlmostEqual(x["t"], clock_at(P["clock"], x["s"]), delta=1e-3)
            self.assertEqual(x["anim"], anim_at(P["path"], x["s"]), f"at {x['s']} s")

    def test_the_cards_come_up_with_the_sights(self):
        shown = 0
        for x in G["samples"]:
            want = [c["title"] for c in P["cards"] if c["s0"] <= x["s"] <= c["s1"]]
            self.assertEqual(x["card"], want[0] if want else "", f"at {x['s']} s")
            shown += bool(want)
        self.assertGreaterEqual(shown, 3)

    def test_the_fab_runs_on_the_visitors_clock(self):
        last = G["samples"][-1]
        self.assertEqual(G["lamps"], [W.state(i, last["t"]) for i in range(len(W.s["tools"]))])


if __name__ == "__main__":
    unittest.main()
