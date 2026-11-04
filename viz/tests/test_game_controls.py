"""Input-data regressions for the public game builds; standard library only."""

import unittest

from viz.fab3d.prep import tool_phase


class ToolPhase(unittest.TestCase):
    def test_phase_follows_building_not_tool_wall_orientation(self):
        fabs = [[0, 100, -20, 20, "First", "fab"],
                [100, 120, -5, 5, "Bridge", "bridge"],
                [120, 200, -20, 20, "Second", "fab"]]
        for wall in (0, 1):
            self.assertEqual(tool_phase(["first", 10, 12, 2, 4, "furnace", wall, 3], fabs), 0)
            self.assertEqual(tool_phase(["second", 130, 132, 2, 4, "furnace", wall, 3], fabs), 1)

    def test_a_tool_in_a_bridge_or_outside_the_fab_is_rejected(self):
        fabs = [[0, 100, -20, 20, "First", "fab"], [100, 120, -5, 5, "Bridge", "bridge"]]
        with self.assertRaisesRegex(ValueError, "outside"):
            tool_phase(["stray", 105, 107, 2, 4, "furnace", 0, 3], fabs)


if __name__ == "__main__":
    unittest.main()
