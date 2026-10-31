"""The supervisor, a toy experiment (docs/SUPERVISOR-TOY.md). Written before the code; no model is called.
Run: python3 -m unittest agent.tests.test_supervise  (from the repo root)."""

import json
import unittest

try:  # arrives with the code
    from agent import supervise
except ImportError:
    supervise = None

RULES = ["today", "fifo", "spt", "cr"]
CAPS = [None, 10, 15, 20, 25, 30]
GRID = [[r, c] for r in RULES for c in CAPS]
STATE = {"t": 4320.0, "current": ["today", None], "lots_inside": 31, "lots_finished": 22, "lot_hours_waiting": 140.5,
         "groups": [["Litho_T", 2, 1, 9, 0.4], ["Planar_T", 1, 0, 3, 0.0]],
         "future_breakdowns": [[0, 5000.0]], "tried": [[["fifo", 20], 3.1]]}


class View(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(supervise, "agent/supervise.py is missing")

    def test_SP1_only_the_past_and_the_present_and_every_setting(self):
        text = supervise.view(STATE, GRID)
        self.assertIn("31 lots inside", text)
        self.assertIn("Litho_T", text)
        self.assertIn("1 of 2 down", text)
        self.assertNotIn("5000", text, "no future breakdowns")
        self.assertNotIn("3.1", text, "no copy's score")
        for r, c in GRID:
            self.assertIn(supervise.setting_name([r, c]), text)


class Reply(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(supervise, "agent/supervise.py is missing")

    def test_SP2_at_most_three_valid_settings_with_reasons(self):
        reply = json.dumps({"settings": [
            {"rule": "fifo", "cap": 20, "why": "Litho has a line."},
            {"rule": "warp", "cap": 20, "why": "no such rule"},
            {"rule": "today", "cap": 12, "why": "no such cap"},
            {"rule": "spt", "cap": None, "why": "short jobs"},
            {"rule": "cr", "cap": 30, "why": "due dates"},
            {"rule": "today", "cap": 10, "why": "a fourth valid one"}]})
        got = supervise.parse_reply("Here you go:\n" + reply, GRID)
        self.assertEqual([s for s, _ in got], [["fifo", 20], ["spt", None], ["cr", 30]])
        self.assertEqual(got[0][1], "Litho has a line.")

    def test_SP2_nothing_valid_keeps_the_current_setting(self):
        self.assertEqual(supervise.parse_reply("I am not sure.", GRID), [])
        self.assertEqual(supervise.parse_reply('{"settings": [{"rule": "warp"}]}', GRID), [])


class Interval(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(supervise, "agent/supervise.py is missing")

    def test_SP3_the_paired_95_interval(self):
        m, lo, hi = supervise.paired([1, 2, 3, 4, 5], [0, 0, 0, 0, 0])
        self.assertAlmostEqual(m, 3.0)
        self.assertAlmostEqual(lo, 3.0 - 2.776445 * 0.707107, places=4)
        self.assertAlmostEqual(hi, 3.0 + 2.776445 * 0.707107, places=4)


if __name__ == "__main__":
    unittest.main()
