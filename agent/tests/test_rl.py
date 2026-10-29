"""Training PPO and the held-out contest (docs/RL-DEFECTS.md, deliverables 5 and 6). Written before the code.
Run: .venv/bin/python -m unittest agent.tests.test_rl  (from the repo root, after `cargo build --release`).

On the SMT2020 model's rules, with a toy shop for speed; not a real fab."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FABSIM = ROOT / "target" / "release" / "fabsim"
HAVE = all(importlib.util.find_spec(m) is not None for m in ("gymnasium", "numpy", "torch", "stable_baselines3"))

SHOP = """fabgym-shop 1
transport\t5.0\t10.0
group\tA\t2\t1.0\t1.0\t-\t900.0\t45.0
group\tB\t2\t1.0\t1.0\t-\t-\t-
route\tr
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
step\tB\tlot\t15.0\t2.0\t-\t-\t-\t-\t-\t-\t0\t0.25\t-\t-
step\tA\tlot\t20.0\t2.0\t-\t-\t-\t-\t-\t-\t-\t-\t-\t-
release\tr\t25\t10.0\t12.0\t0.0\t-\tN
release\tr\t25\t20.0\t300.0\t30.0\t-\tH
"""


class Intervals(unittest.TestCase):
    def test_t_quantiles_match_the_tables(self):
        from agent import rl
        for p, df, want in [(0.975, 9, 2.262157), (0.995, 9, 3.249836), (0.95, 5, 2.015048), (0.975, 30, 2.042272)]:
            self.assertAlmostEqual(rl.t_quantile(p, df), want, places=5)

    def test_paired_difference_and_verdict(self):
        from agent import rl
        base = [10.0, 12.0, 11.0, 13.0]
        cand = [11.0, 13.5, 11.5, 14.0]  # differences 1, 1.5, 0.5, 1
        iv = rl.paired(base, cand, 0.05)
        self.assertAlmostEqual(iv["mean"], 1.0)
        half = rl.t_quantile(0.975, 3) * (0.408248290463863 / 2.0)
        self.assertAlmostEqual(iv["lo"], 1.0 - half, places=9)
        self.assertAlmostEqual(iv["hi"], 1.0 + half, places=9)
        self.assertEqual(rl.verdict(iv, True), "better")
        self.assertEqual(rl.verdict(iv, False), "worse")
        self.assertEqual(rl.verdict({"mean": 0.1, "lo": -1, "hi": 1}, True), "no clear effect")


@unittest.skipUnless(HAVE and FABSIM.exists(), "needs the RL packages and a release build of fabsim")
class TrainAndContest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.shop = self.tmp / "toy.shop.txt"
        self.shop.write_text(SHOP)
        self.common = dict(shop=str(self.shop), fabsim=str(FABSIM), warmup_days=0.5, window_days=1.0, defects=(120, 240, 60))

    def test_todays_rule_plays_as_fabsim_scores_it(self):
        from agent import rl
        got = rl.play(rl.Today(), seed=4, **self.common)
        p = subprocess.run([str(FABSIM), "env", str(self.shop), "--seed", "4", "--warmup", "0.5", "--window", "1.0", "--defects", "120,240,60", "--auto"],
                           capture_output=True, text=True, check=True)
        want = json.loads(p.stdout.strip().splitlines()[-1])["score"]
        for k in ("reward", "moves", "lots_finished", "wait_lot_hours", "breaches"):
            self.assertAlmostEqual(got["score"][k], want[k], places=9)
        self.assertEqual(got["picked_other"], 0)

    def test_a_small_training_run_saves_a_policy_that_plays(self):
        from agent import rl
        out = self.tmp / "ppo"
        rl.train(seeds=[100, 101], timesteps=512, workers=1, out=out, n_steps=256, **self.common)
        self.assertTrue((out / "policy.zip").exists())
        meta = json.loads((out / "train.json").read_text())
        self.assertEqual(meta["seeds"], [100, 101])
        self.assertEqual(meta["defects"], [120, 240, 60])
        self.assertTrue(meta["model"].startswith("SMT2020") or meta["model"] == "toy")
        pol = rl.Learned(out / "policy.zip")
        got = rl.play(pol, seed=4, **self.common)
        self.assertIn("reward", got["score"])
        self.assertGreater(got["decisions"], 0)

    def test_the_contest_writes_runs_and_a_card(self):
        from agent import rl
        out = self.tmp / "contest"
        card = rl.contest({"today": rl.Today(), "last slot": rl.Fixed(7)}, seeds=[0, 1, 2], out=out, **self.common)
        rows = (out / "runs.tsv").read_text().strip().splitlines()
        self.assertEqual(rows[0].split("\t")[:3], ["contestant", "seed", "reward"])
        self.assertEqual(len(rows), 1 + 2 * 3)
        self.assertEqual([c["name"] for c in card["against_today"]], ["last slot"])
        c = card["against_today"][0]
        for k in ("reward", "moves", "lots_finished", "wait_lot_hours"):
            self.assertIn(k, c["measures"])
            m = c["measures"][k]
            self.assertLessEqual(m["lo"], m["mean"])
            self.assertLessEqual(m["mean"], m["hi"])
            self.assertIn(m["verdict"], ("better", "worse", "no clear effect"))
        self.assertEqual(card["seeds"], [0, 1, 2])
        self.assertIn("SMT2020", card["note"])
        self.assertTrue((out / "card.json").exists())


    def test_every_kind_of_policy_is_scored_and_registered(self):
        """docs/LONG-RESCORE.md: built-in rules, written rules and learned policies through one harness, every
        measure kept per seed with the time each decision took, and a registry naming each policy and the protocol."""
        from agent import rl
        out = self.tmp / "registry"
        pols = {"today": rl.Today(), "fifo": rl.BuiltIn("fifo"), "cr": rl.BuiltIn("cr"), "last slot": rl.Fixed(7)}
        card = rl.contest(pols, seeds=[0, 1], out=out, protocol="test-v0", **self.common)
        head = (out / "runs.tsv").read_text().splitlines()[0].split("\t")
        for k in ("contestant", "seed", "reward", "moves", "lots_finished", "wait_lot_hours", "breaches", "cycle_days",
                  "wafers_per_day", "mean_wip", "hot_cycle_days", "decisions", "sec_per_decision"):
            self.assertIn(k, head)
        reg = json.loads((out / "policies.json").read_text())
        self.assertEqual(reg["protocol"]["name"], "test-v0")
        self.assertEqual(sorted(p["name"] for p in reg["policies"]), sorted(pols))
        for p in reg["policies"]:
            self.assertIn(p["kind"], ("built-in rule", "written rule", "learned", "fixed slot"))
        self.assertIn("cycle_days", card["against_today"][0]["measures"])


if __name__ == "__main__":
    unittest.main()
