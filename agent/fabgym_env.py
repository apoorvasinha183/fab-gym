"""Fab Gym as a Gymnasium environment (docs/RL-DEFECTS.md): one dispatch decision at a time over `fabsim env`.

    env = FabGymEnv("data/smt2020/hvlm", seeds=range(100, 200), defects=(120, 240, 60))
    obs, info = env.reset()
    obs, reward, terminated, truncated, info = env.step(action)

The observation is a fixed vector: K candidates by their fields (scaled), a mask of real candidates, and the
deciding group's tools and the fab's totals. The action picks one of the K slots; a slot with no candidate is
masked to the engine's own pick (slot 0) and counted. Rewards are the scorer's reward (lots finished minus 0.01
per lot-hour waiting) as it changes between decisions, so an episode's rewards sum to the window's reward.
From the SMT2020 testbed, a published set of a fab's tool groups, routes and times; not a real fab."""

import json
import math
import subprocess
from pathlib import Path

import gymnasium as gym
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FABSIM = ROOT / "target" / "release" / "fabsim"
K = 8
FIELDS = ["is_batch", "lots", "priority", "size_wafers", "step", "steps_left", "waited_minutes", "setup_change",
          "proc_minutes", "work_left_minutes", "age_minutes", "cqt_slack_minutes", "is_default", "family"]
MINUTES = {"waited_minutes", "proc_minutes", "work_left_minutes", "age_minutes", "cqt_slack_minutes"}
CTX = 7  # working, idle, down, held (as shares of the group), waiting, finished (thousands), time in the window


def scale(field, v):
    v = 0.0 if v is None else float(v)
    if field in MINUTES:
        return math.copysign(math.log1p(abs(min(v, 1e5))) / 10.0, v)
    if field in ("step", "steps_left"):
        return v / 600.0
    if field == "priority":
        return v / 20.0
    if field == "size_wafers":
        return v / 25.0
    if field == "lots":
        return v / 10.0
    return v


class FabGymEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, shop, fabsim=str(FABSIM), seeds=(100,), warmup_days=1.0, window_days=3.0, defects=None, picks=None):
        self.shop, self.fabsim = str(shop), str(fabsim)
        self.picks = picks  # a file for the episode's picks, one a line (regret B)
        self.seeds = list(seeds)
        self.warmup_days, self.window_days = warmup_days, window_days
        self.defects = defects
        self.action_space = gym.spaces.Discrete(K)
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, shape=(K * len(FIELDS) + K + CTX,), dtype=np.float32)
        self.proc = None
        self.episode = 0
        self.last = None

    # ------------------------------------------------------------------ the process

    def _start(self, seed):
        self.close()
        cmd = [self.fabsim, "env", self.shop, "--seed", str(seed), "--warmup", str(self.warmup_days), "--window", str(self.window_days)]
        if self.defects:
            cmd += ["--defects", ",".join(str(x) for x in self.defects)]
        if self.picks:
            cmd += ["--picks", str(self.picks)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def _read(self):
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("fabsim env stopped without a done line")
        return json.loads(line)

    def close(self):
        if self.proc is not None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            if self.proc.stdout:
                self.proc.stdout.close()
            self.proc.kill()
            self.proc.wait()
            self.proc = None

    # ------------------------------------------------------------------ observations

    def _vector(self, o):
        x = np.zeros(self.observation_space.shape, dtype=np.float32)
        if o is None or o.get("done"):
            return x
        for k, c in enumerate(o["cands"][:K]):
            for j, f in enumerate(FIELDS):
                x[k * len(FIELDS) + j] = scale(f, c.get(f))
        base = K * len(FIELDS)
        x[base:base + K] = self._mask(o)
        tools = o["tools"]
        n = max(1, tools["working"] + tools["idle"] + tools["down"])
        start = self.warmup_days * 1440.0
        x[base + K:] = [tools["working"] / n, tools["idle"] / n, tools["down"] / n, o["held_tools"] / n,
                        o["totals"]["waiting"] / 1000.0, o["totals"]["finished"] / 1000.0,
                        (o["t"] - start) / (self.window_days * 1440.0)]
        return x

    @staticmethod
    def _mask(o):
        m = np.zeros(K, dtype=np.float32)
        if o is not None and not o.get("done"):
            m[:min(K, len(o["cands"]))] = 1.0
        return m

    def _info(self, o):
        info = {"mask": self._mask(o), "default": 0, "fallbacks": self.fallbacks, "seed": self.seed_now}
        if o is not None and o.get("done"):
            info.update(score=o["score"], decisions=o["decisions"], daily_wafers=o.get("daily_wafers"))
        return info

    # ------------------------------------------------------------------ Gymnasium

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if options and "episode_seed" in options:
            self.seed_now = int(options["episode_seed"])
        elif seed is not None and seed in self.seeds:
            self.seed_now = seed
        else:
            self.seed_now = self.seeds[self.episode % len(self.seeds)]
        self.episode += 1
        self.fallbacks = 0
        self._start(self.seed_now)
        self.last = self._read()
        return self._vector(self.last), self._info(self.last)

    def step(self, action):
        if self.last is None or self.last.get("done"):
            return self._vector(None), 0.0, True, False, self._info(self.last)
        a = int(action)
        if not (0 <= a < len(self.last["cands"])):
            a = 0
            self.fallbacks += 1
        self.proc.stdin.write(json.dumps({"action": a}) + "\n")
        self.proc.stdin.flush()
        self.last = self._read()
        done = bool(self.last.get("done"))
        info = self._info(self.last)
        if done:
            self.close()
        return self._vector(self.last), float(self.last["reward"]), done, False, info

    def action_masks(self):
        """For maskable learners: which slots hold a candidate."""
        return self._mask(self.last).astype(bool)
