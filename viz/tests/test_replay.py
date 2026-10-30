"""Tests for the replay: a rule against today's rule, side by side (docs/REPLAY.md). Written before the code.

From the SMT2020 testbed, on a gigafab-style layout of our own design; not a real fab. Standard library only:

    python3 -m unittest viz.tests.test_replay      (from the repo root)

The trace and builder tests need the campus's shop (data/layout-real/optimised.shop.txt, from
`fabsim layout --real`) and skip without it. The Godot check runs when GODOT names Godot; otherwise it
reads the report a machine with Godot wrote (data/layout-real/replay-check.json), and skips if neither.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJ = ROOT / "viz/godot-real"
SHOP = ROOT / "data/layout-real/optimised.shop.txt"
FABSIM = ROOT / "target/release/fabsim"
FABRULE = ROOT / "target/release/fabrule"
REPORT = ROOT / "data/layout-real/replay-check.json"

TODAY = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { if c.is_default > 0.5 { 0.0 } else { 1.0 } }"
FIFO = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { -c.waited_minutes }"
BROKEN = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { c.nope }"
WINDOW = ["--seed", "3001", "--day", "30", "--hours", "2"]

BRANDS = ["ASML", "TSMC", "Tokyo Electron", "Applied Materials", "Lam Research", "KLA", "Daifuku", "Murata",
          "Samsung", "Intel", "TWINSCAN"]

sys.path.insert(0, str(ROOT / "viz"))


def need_shop(t):
    if not SHOP.exists():
        t.skipTest("no campus shop: run `fabsim layout --real` first")


def build():
    if not (FABSIM.exists() and FABRULE.exists()):
        subprocess.run(["cargo", "build", "--release", "-p", "fabsim", "-p", "fabrule"], cwd=ROOT, check=True)


_traces = {}


def trace(src, d):
    """fabrule's trace of the campus under a rule, written in d."""
    f = Path(d) / "rule.rs"
    f.write_text(src)
    out = Path(d) / "trace.json"
    p = subprocess.run([str(FABRULE), "trace", str(f), "--real", "--data", str(ROOT / "data/layout-real"),
                        "--plan", "optimised", *WINDOW, "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
    return p, out


def cached(name, src):
    if name not in _traces:
        d = tempfile.mkdtemp(prefix=f"replay-{name}-")
        p, out = trace(src, d)
        assert p.returncode == 0, p.stdout + p.stderr
        _traces[name] = out
    return _traces[name]


# ------------------------------------------------------------------ fabrule trace


class Trace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()

    def setUp(self):
        need_shop(self)

    def test_todays_rule_gives_fabsims_own_trace(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(SHOP, Path(d) / "optimised.shop.txt")
            subprocess.run([str(FABSIM), "layout-trace", "--real", "--data", d, "--plan", "optimised", *WINDOW],
                           cwd=ROOT, check=True, capture_output=True)
            own = (Path(d) / "trace-optimised.json").read_bytes()
        self.assertEqual(cached("today", TODAY).read_bytes(), own)

    def test_another_rule_gives_another_run_on_the_same_campus(self):
        a = json.loads(cached("today", TODAY).read_text())
        b = json.loads(cached("fifo", FIFO).read_text())
        for k in ("model", "from", "to", "spine", "bridge", "offsets", "lengths"):
            self.assertEqual(a[k], b[k], k)
        self.assertNotEqual(a["lots"], b["lots"])

    def test_a_rule_that_does_not_compile_is_refused_with_the_compilers_words(self):
        with tempfile.TemporaryDirectory() as d:
            p, out = trace(BROKEN, d)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse(out.exists())
            self.assertIn("nope", p.stdout + p.stderr)


# ------------------------------------------------------------------ the pair


def recount(tr, every=10.0):
    """moves, lot-hours waited and the queue of each group, counted from a trace alone."""
    a, b = float(tr["from"]), float(tr["to"])
    steps = [s for l in tr["lots"] for s in l["steps"]]
    times = []
    x = a
    while x <= b + 1e-9:
        times.append(round(x, 2))
        x += every
    moves = [sum(1 for s in steps if a < s[2] <= t) for t in times]
    wait = [sum(max(0.0, min(s[1], t) - max(s[0], a)) for s in steps) / 60.0 for t in times]
    return times, moves, wait


def queue(tr, g, t):
    return sum(1 for l in tr["lots"] for s in l["steps"] if s[4] == g and s[0] <= t < s[1])


class Pair(unittest.TestCase):
    out = None

    @classmethod
    def setUpClass(cls):
        if not SHOP.exists():
            return
        build()
        import replay  # viz/replay.py

        cls.d = Path(tempfile.mkdtemp(prefix="replay-pair-"))
        src = cls.d / "fifo.rs"
        src.write_text(FIFO)
        cls.rep = replay.make(src, name="First in, first out", hand_written=True, card=None,
                              seed=3001, day=30, hours=2, out=cls.d)
        cls.out = cls.d

    def setUp(self):
        need_shop(self)

    def load(self, n):
        return json.loads((self.out / n).read_text())

    def test_three_files(self):
        for n in ("scene-today.json", "scene-rule.json", "replay.json"):
            self.assertTrue((self.out / n).exists(), n)

    def test_both_scenes_are_the_same_campus(self):
        a, b = self.load("scene-today.json"), self.load("scene-rule.json")
        for k in ("tools", "bays", "campus", "rails", "groups", "from", "to", "floors"):
            self.assertEqual(a[k], b[k], k)
        self.assertEqual(len(a["tools"]), 1043)
        self.assertNotEqual(a["lots"], b["lots"])

    def test_the_rule_is_named_and_hashed(self):
        r = self.load("replay.json")["rule"]
        self.assertEqual(r["name"], "First in, first out")
        self.assertEqual(r["source"], FIFO)
        self.assertEqual(r["sha256"], hashlib.sha256(FIFO.encode()).hexdigest())
        self.assertTrue(r["hand_written"])
        self.assertIsNone(r["card"])

    def test_it_says_what_it_is(self):
        r = self.load("replay.json")
        self.assertIn("SMT2020 testbed", r["what"])
        self.assertIn("not a real fab", r["what"])
        self.assertEqual(r["seed"], 3001)

    def test_the_series_are_counted_from_the_traces(self):
        r = self.load("replay.json")
        for side in ("today", "rule"):
            tr = json.loads(Path(r["traces"][side]).read_text())
            times, moves, wait = recount(tr)
            s = r["series"]
            self.assertEqual(s["t"], times)
            self.assertEqual(s[side]["moves"], moves, side)
            for x, y in zip(s[side]["wait_lot_hours"], wait):
                self.assertAlmostEqual(x, y, places=2)
            g = r["watch"]["group"]
            self.assertEqual(s[side]["queue"], [queue(tr, g, t) for t in times], side)

    def test_the_watched_group_is_where_the_two_differ_most(self):
        r = self.load("replay.json")
        tr = {k: json.loads(Path(r["traces"][k]).read_text()) for k in ("today", "rule")}
        times = r["series"]["t"]
        groups = {s[4] for k in tr for l in tr[k]["lots"] for s in l["steps"]}

        def gap(g):
            return abs(sum(queue(tr["rule"], g, t) - queue(tr["today"], g, t) for t in times)) / len(times)

        best = max(gap(g) for g in groups)
        self.assertAlmostEqual(gap(r["watch"]["group"]), best, places=6)
        scene = self.load("scene-today.json")
        self.assertEqual(r["watch"]["name"], scene["groups"][r["watch"]["group"]]["name"])
        self.assertEqual(len(r["watch"]["at"]), 2)


# ------------------------------------------------------------------ Godot


class Scene(unittest.TestCase):
    def test_compare_is_a_scene_with_two_worlds(self):
        t = (PROJ / "compare.tscn").read_text()
        self.assertEqual(t.count("type=\"SubViewportContainer\""), 2)
        self.assertEqual(t.count("type=\"SubViewport\""), 2)
        self.assertEqual(t.count("own_world_3d = true"), 2)
        self.assertEqual(t.count("instance=ExtResource("), 2)
        self.assertIn("res://main.tscn", t)
        self.assertIn("res://data/replay/scene-today.json", t)
        self.assertIn("res://data/replay/scene-rule.json", t)
        self.assertIn("res://compare.gd", t)

    def test_main_can_be_embedded(self):
        s = (PROJ / "main.gd").read_text()
        self.assertIn("@export var scene_path", s)
        self.assertIn("@export var embedded", s)

    def test_compare_says_what_it_is(self):
        s = (PROJ / "compare.gd").read_text()
        for words in ("from the SMT2020 testbed", "not a real fab", "Today's rule", "hand-written", "not scored",
                      "one seed"):
            self.assertIn(words, s, words)
        for b in BRANDS:
            self.assertNotIn(b, s, b)


def check_report():
    godot = os.environ.get("GODOT")
    if godot and (PROJ / "data/replay/replay.json").exists():
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "check.json"
            subprocess.run([godot, "--headless", "--path", str(PROJ), "res://compare.tscn", "--", "--compare-check",
                            str(out)], check=True, capture_output=True, timeout=600)
            r = json.loads(out.read_text())
        REPORT.write_text(json.dumps(r, indent=1))
        return r
    if REPORT.exists():
        return json.loads(REPORT.read_text())
    return None


class Check(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = check_report()

    def setUp(self):
        if self.r is None:
            self.skipTest("no Godot and no saved report")

    def test_both_sides_draw_the_whole_campus(self):
        self.assertEqual(self.r["tools"], [1043, 1043])

    def test_one_clock_and_one_camera(self):
        for step in self.r["steps"]:
            self.assertEqual(step["t"][0], step["t"][1])
            for a, b in zip(step["cam"][0], step["cam"][1]):
                self.assertAlmostEqual(a, b, places=4)
        self.assertGreater(self.r["steps"][-1]["t"][0], self.r["steps"][0]["t"][0], "the clock moved")

    def test_the_panels_show_the_series(self):
        rep = json.loads((PROJ / "data/replay/replay.json").read_text()) if (PROJ / "data/replay/replay.json").exists() else None
        if rep is None:
            self.skipTest("no synced replay")
        times = rep["series"]["t"]
        for step in self.r["steps"]:
            t = step["t"][0]
            k = max(i for i, x in enumerate(times) if x <= t + 1e-6)
            for side, i in (("today", 0), ("rule", 1)):
                self.assertEqual(step["panel"][i]["moves"], rep["series"][side]["moves"][k])
                self.assertEqual(step["panel"][i]["queue"], rep["series"][side]["queue"][k])

    def test_the_screen_names_both_rules(self):
        text = " ".join(self.r["text"])
        for words in ("Today's rule", "from the SMT2020 testbed", "not a real fab"):
            self.assertIn(words, text)
        self.assertIn(json.loads((PROJ / "data/replay/replay.json").read_text())["rule"]["name"], text)


if __name__ == "__main__":
    unittest.main()
