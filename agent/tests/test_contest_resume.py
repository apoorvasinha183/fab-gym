"""Contest resumes must keep the experiment and its saved scores together."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import rl


class ContestResume(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.shop = self.root / "shop.txt"
        self.shop.write_text("shop version one")
        self.binary = self.root / "fabsim"
        self.binary.write_bytes(b"sim version one")
        self.kw = dict(shop=self.shop, fabsim=self.binary, out=self.root / "runs", seeds=[0, 1])

    @staticmethod
    def result(policy, seed, *args):
        return dict(seed=seed, score={k: 1.0 for k, _ in rl.MEASURES}, decisions=2,
                    picked_other=1, picked_other_by_group={"CMP": 1}, fallbacks=0,
                    sec_per_decision=0.1, act_ms=0.01)

    def test_identical_resume_reuses_scores_and_keeps_group_counts(self):
        with patch.object(rl, "timed_play", side_effect=self.result) as play:
            pols = {"today": rl.Today(), "candidate": rl.Fixed(1)}
            first = rl.contest(pols, **self.kw)
            again = rl.contest(pols, **self.kw)
            self.assertEqual(play.call_count, 4)
            self.assertEqual(again, first)

    def test_changed_protocol_policy_or_shop_cannot_relabel_old_scores(self):
        for change in ("window", "protocol", "defects", "policy", "shop", "binary"):
            with self.subTest(change=change), patch.object(rl, "timed_play", side_effect=self.result):
                kw = {**self.kw, "out": self.root / change}
                pols = {"today": rl.Today(), "candidate": rl.Fixed(1)}
                rl.contest(pols, **kw)
                if change == "window":
                    kw["window_days"] = 60
                elif change == "protocol":
                    kw["protocol"] = "new-protocol"
                elif change == "defects":
                    kw["defects"] = (120, 240, 60)
                elif change == "policy":
                    pols["candidate"] = rl.Fixed(7)
                elif change == "shop":
                    self.shop.write_text("shop version two")
                else:
                    self.binary.write_bytes(b"sim version two")
                with self.assertRaisesRegex(ValueError, "(?i)(resume|different|changed|match)"):
                    rl.contest(pols, **kw)



if __name__ == "__main__":
    unittest.main()
