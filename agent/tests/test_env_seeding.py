"""Reset seeding is reproducible while training stays within its configured seed pool."""
import importlib.util
import unittest

HAVE = all(importlib.util.find_spec(m) is not None for m in ("numpy", "gymnasium"))


@unittest.skipUnless(HAVE, "requires Gymnasium and NumPy")
class SeedContract(unittest.TestCase):
    def test_repeated_reset_seed_replays_the_same_episode(self):
        from agent.fabgym_env import FabGymEnv
        env = FabGymEnv("unused", seeds=[100, 101, 102])
        self.addCleanup(env.close)
        env._start = lambda seed: None
        env._read = lambda: {"done": True, "score": {}, "decisions": 0}
        first = env.reset(seed=7)[1]["seed"]
        env.reset()
        again = env.reset(seed=7)[1]["seed"]
        self.assertEqual(first, again)
        self.assertIn(first, env.seeds)

    def test_explicit_episode_seed_and_seedless_rotation(self):
        from agent.fabgym_env import FabGymEnv
        env = FabGymEnv("unused", seeds=[100, 101])
        self.addCleanup(env.close)
        env._start = lambda seed: None
        env._read = lambda: {"done": True, "score": {}, "decisions": 0}
        self.assertEqual([env.reset()[1]["seed"] for _ in range(3)], [100, 101, 100])
        self.assertEqual(env.reset(options={"episode_seed": 0})[1]["seed"], 0)

    def test_empty_seed_pool_is_rejected_at_construction(self):
        from agent.fabgym_env import FabGymEnv
        with self.assertRaises(ValueError):
            FabGymEnv("unused", seeds=[])
