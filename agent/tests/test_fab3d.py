"""The 3D fab's helper side (docs/FAB-3D.md, F2 to F4). Written before the code. The helper runs the simulator for the
whole fab, keeps it, and answers for the cells near the viewer only; spoken questions go to Meta's speech model, here
always a recorded stand-in, so no test calls a network. From the SMT2020 testbed; not a real fab."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import fab3d, helper

ROOT = Path(__file__).resolve().parents[2]
BUILDING = ROOT / "web/data/building.json"
SHOP = ROOT / "web/data/shop-real.txt"
FABSIM = ROOT / "target/release/fabsim"


def make(d, voice=None):
    s = None
    if voice is not None:
        s = Path(d) / "stand"
        s.mkdir(exist_ok=True)
        (s / "voice.json").write_text(json.dumps({"text": voice}))
    return helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True, stand_in=s)


class Setup(unittest.TestCase):
    def test_fresh_clone_explains_missing_inputs_without_starting_a_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            web = root / "web"
            (web / "data").mkdir(parents=True)
            (web / "data/areas.tsv").write_text("A\tCMP\n")
            h = helper.Helper(web=web, jobs=root / "jobs", runs=root / "runs", no_model=True)
            with patch.object(h, "_fab3d_cmd") as run:
                answer = h.fab3d_run({})
            run.assert_not_called()
            self.assertTrue(answer["missing_data"])
            self.assertIn("sh web/build-3d.sh", answer["error"])


class Copper(unittest.TestCase):
    def test_f2_a_carrier_is_copper_only_when_its_lot_is_bound_for_the_back_end(self):
        for g in ("DE_BE_11", "Planar_BE_75", "TF_BE_23"):
            self.assertTrue(fab3d.is_copper(g), g)
        for g in ("DE_FE_1", "Litho_FE_111", "Planar_FE_77", "Delay_32", "", None):
            self.assertFalse(fab3d.is_copper(g), g)


@unittest.skipUnless(FABSIM.exists() and SHOP.exists() and BUILDING.exists(), "needs the built simulator and the building")
class Live(unittest.TestCase):
    def test_f3_a_cell_gets_its_own_tools_and_carriers_at_that_minute(self):
        with tempfile.TemporaryDirectory() as d:
            h = make(d)
            r = h.fab3d_run({"seed": 1, "days": 0.5})
            self.assertNotIn("error", r, r)
            self.assertGreater(r["frames"], 1)
            self.assertAlmostEqual(r["minutes"], 720.0)
            cells = fab3d.cells(json.loads(BUILDING.read_text()))
            cid, cell = next((k, c) for k, c in sorted(cells["cells"].items()) if c["tools"] and c["stretches"])
            t = 300.0
            s = h.fab3d_state({"run": r["run"], "t": t, "cells": [cid]})
            self.assertNotIn("error", s, s)
            # that cell's tools, and no others
            self.assertEqual(sorted(int(k) for k in s["tools"]), sorted(cell["tools"]))
            # each tool's state is the moods frame at or before t
            run = h.fab3d_runs[r["run"]]
            for k, mood in s["tools"].items():
                self.assertEqual(mood, run.mood_at(int(k), t), k)
            # carriers only on that cell's stretches, placed along them, copper or not
            for c in s["carriers"]:
                self.assertIn(c["stretch"], cell["stretches"], c)
                self.assertGreaterEqual(c["along"], 0.0)
                self.assertLessEqual(c["along"], 1.0)
                self.assertIsInstance(c["copper"], bool)
                self.assertIsInstance(c["loaded"], bool)

    def test_f3_a_vehicle_standing_over_a_port_is_still_sent(self):
        # between two stays a vehicle stands over a tool's port while its pod goes down and up; with a span the
        # helper also sends each vehicle's stays that ended in the last few minutes, so the scene can hold it there
        with tempfile.TemporaryDirectory() as d:
            h = make(d)
            r = h.fab3d_run({"seed": 1, "days": 0.5})
            cells = fab3d.cells(json.loads(BUILDING.read_text()))
            ids = sorted(cells["cells"])
            t = 400.0
            s = h.fab3d_state({"run": r["run"], "t": t, "cells": ids, "span": 2})
            by = {}
            for c in s["carriers"]:
                by.setdefault(c["vehicle"], []).append(c)
            standing = [v for v, cs in by.items() if all(c["t_out"] is not None and c["t_out"] <= t for c in cs)]
            self.assertTrue(standing, "no vehicle between two stays at t")
            for c in s["carriers"]:
                self.assertGreater(c["t_out"] if c["t_out"] is not None else 1e12, t - fab3d.PARK)
                self.assertLess(c["t_in"], t + 2)
            # a vehicle that drove out of a cell is not left standing there: an ended stay comes only when it is the
            # vehicle's latest move anywhere in the fab
            last = {}
            for c in s["carriers"]:
                if c["t_in"] <= t:
                    last[c["vehicle"]] = max(last.get(c["vehicle"], -1.0), c["t_in"])
            for cid in ids[:40]:
                one = h.fab3d_state({"run": r["run"], "t": t, "cells": [cid], "span": 2})
                for c in one["carriers"]:
                    if c["t_out"] is not None and c["t_out"] <= t:
                        self.assertEqual(c["t_in"], last[c["vehicle"]], (cid, c))

    def test_f3_an_unknown_run_or_cell_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            h = make(d)
            self.assertIn("error", h.fab3d_state({"run": "nope", "t": 0, "cells": ["0,0"]}))
            r = h.fab3d_run({"seed": 1, "days": 0.1})
            self.assertIn("error", h.fab3d_state({"run": r["run"], "t": 0, "cells": ["999,999"]}))


class Voice(unittest.TestCase):
    def test_f4_the_stand_in_answers_and_nothing_is_called(self):
        with tempfile.TemporaryDirectory() as d:
            h = make(d, voice="why is the polisher queue long")
            audio = base64.b64encode(b"\x1aE\xdf\xa3" + b"0" * 2000).decode()
            r = h.voice({"audio": audio, "mime": "audio/webm"})
            self.assertEqual(r["text"], "why is the polisher queue long")
            self.assertEqual(r.get("model"), "stand-in")

    def test_f4_too_big_is_refused_and_no_model_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            h = make(d, voice="hello")
            big = base64.b64encode(b"0" * (20 * 1024 * 1024 + 1)).decode()
            r = h.voice({"audio": big, "mime": "audio/webm"})
            self.assertIn("error", r)
            self.assertIn("20 MB", r["error"])
            h2 = make(d)
            r2 = h2.voice({"audio": base64.b64encode(b"abc").decode(), "mime": "audio/webm"})
            self.assertIn("error", r2)


if __name__ == "__main__":
    unittest.main()
