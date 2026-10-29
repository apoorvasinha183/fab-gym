"""The drawn rails are the simulator's track (decided by quiz 29 Oct: the two-rail bay loop; the drawings keep their
look). Written before the code. On the SMT2020 model, a gigafab-style layout of our own design; not a real fab.

    .venv/bin/python -m unittest viz.tests.test_rails      (from the repo root)

Compares the scene's rails (viz/look/scene.py, read by the plans, the BIM, Blender and the game) with the track the
simulator moves vehicles on (`fabsim track`), both as straight runs on the plan.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FABSIM = ROOT / "target/release/fabsim"
DATA = ROOT / "data/layout-real-dd"


def runs(segs):
    """Axis-aligned segments merged into maximal straight runs, as rounded tuples (direction dropped)."""
    lines = {}
    for (ax, ay), (bx, by) in segs:
        if abs(ay - by) < 1e-6:
            k, lo, hi = ("h", round(ay, 2)), min(ax, bx), max(ax, bx)
        elif abs(ax - bx) < 1e-6:
            k, lo, hi = ("v", round(ax, 2)), min(ay, by), max(ay, by)
        else:
            raise AssertionError(f"a rail that is not straight along the plan: {(ax, ay, bx, by)}")
        if hi - lo > 1e-6:
            lines.setdefault(k, []).append((lo, hi))
    out = set()
    for k, v in lines.items():
        v.sort()
        cur = list(v[0])
        for lo, hi in v[1:]:
            if lo <= cur[1] + 0.02:
                cur[1] = max(cur[1], hi)
            else:
                out.add((k, round(cur[0], 1), round(cur[1], 1)))
                cur = [lo, hi]
        out.add((k, round(cur[0], 1), round(cur[1], 1)))
    return out


@unittest.skipUnless(FABSIM.exists() and (DATA / "scene-optimised.json").exists() and (DATA / "optimised.shop.txt").exists(),
                     "build fabsim and the US building first")
class Rails(unittest.TestCase):
    def test_the_drawn_rails_are_the_simulators_track(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "track.json"
            subprocess.run([str(FABSIM), "track", "--data", str(DATA), "--out", str(out)], check=True, capture_output=True)
            track = json.loads(out.read_text())
        scene = json.loads((DATA / "scene-optimised.json").read_text())
        drawn = runs([((a[0], a[1]), (c[0], c[1])) for a, c in scene["rails"]])
        sim = runs([((s[0], s[1]), (s[2], s[3])) for s in track["runs"]])
        self.assertEqual(sorted(drawn - sim), [], "every drawn rail is track the simulator uses")
        self.assertEqual(sorted(sim - drawn), [], "the simulator uses no rail the drawings leave out")


if __name__ == "__main__":
    unittest.main()
