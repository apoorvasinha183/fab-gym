"""The Gymnasium wrapper over `fabsim env` (docs/RL-DEFECTS.md, test 8). Written before the code.
Run: python3 -m unittest agent.tests.test_env  (from the repo root, after `cargo build --release`).
Skipped until Gymnasium is installed (its download is asked first).

From the SMT2020 testbed's rules, with a toy shop; not a real fab."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FABSIM = ROOT / "target" / "release" / "fabsim"
HAVE_GYM = importlib.util.find_spec("gymnasium") is not None and importlib.util.find_spec("numpy") is not None

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
defects\t120\t240\t60
"""


@unittest.skipUnless(HAVE_GYM and FABSIM.exists(), "needs Gymnasium, NumPy and a release build of fabsim")
class Env(unittest.TestCase):
    def setUp(self):
        from agent.fabgym_env import FabGymEnv, K
        self.K = K
        self.tmp = Path(tempfile.mkdtemp())
        self.shop = self.tmp / "toy.shop.txt"
        self.shop.write_text(SHOP)
        self.env = FabGymEnv(str(self.shop), fabsim=str(FABSIM), seeds=[5], warmup_days=0.5, window_days=1.0)

    def tearDown(self):
        self.env.close()

    def test_fixed_shapes_and_mask(self):
        obs, info = self.env.reset(seed=0)
        self.assertEqual(self.K, 8)
        self.assertEqual(self.env.action_space.n, 8)
        self.assertEqual(obs.shape, self.env.observation_space.shape)
        mask = info["mask"]
        self.assertEqual(len(mask), 8)
        self.assertGreaterEqual(int(sum(mask)), 2)
        # an action on an empty slot is masked to the engine's pick, never an error
        empty = [k for k in range(8) if not mask[k]]
        if empty:
            obs2, _, _, _, info2 = self.env.step(empty[0])
            self.assertEqual(obs2.shape, obs.shape)
            self.assertEqual(info2["fallbacks"], 1)

    def test_engine_picks_score_as_todays_rule(self):
        import subprocess, json
        obs, info = self.env.reset(seed=0)
        total, done = 0.0, False
        while not done:
            obs, r, term, trunc, info = self.env.step(info["default"])
            total += r
            done = term or trunc
        score = info["score"]
        self.assertAlmostEqual(total, score["reward"], places=9)
        # the same as fabsim's own run of today's rule over that window
        p = subprocess.run([str(FABSIM), "env", str(self.shop), "--seed", "5", "--warmup", "0.5", "--window", "1.0", "--auto"],
                           capture_output=True, text=True, check=True)
        want = json.loads(p.stdout.strip().splitlines()[-1])["score"]
        for k in ("reward", "moves", "lots_finished", "wait_lot_hours"):
            self.assertAlmostEqual(score[k], want[k], places=9)


if __name__ == "__main__":
    unittest.main()
