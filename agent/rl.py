"""Reinforcement learning in Fab Gym (docs/RL-DEFECTS.md): train PPO over `fabsim env`, and score contestants once on
held-out seeds against today's rule with paired 95% intervals (Bonferroni over the contestants).

    python -m agent.rl train   --shop data/smt2020/hvlm --seeds 100..200 --defects 120,240,60 --timesteps 2000000 --workers 4 --out results/rl-defects/ppo
    python -m agent.rl contest --shop data/smt2020/hvlm --seeds 0..10 --defects 120,240,60 --policy ppo=results/rl-defects/ppo/policy.zip --out results/rl-defects/contest

On the SMT2020 model, a published model of a fab; not a real fab. Agents propose, the simulator scores, a person signs."""

import argparse
import json
import math
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FABSIM = ROOT / "target" / "release" / "fabsim"
NOTE = "On the SMT2020 model, a published model of a fab. Defect holds and their rates are assumed. Real-fab effect: cannot say."

# ------------------------------------------------------------------ intervals (as crates/fabsim/src/uq.rs)


def _betacf(a, b, x):
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb) * _betacf(b, a, 1.0 - x) / b


def t_tail(t, df):
    """P(T > t) for t >= 0."""
    return 0.5 * _ibeta(df / 2.0, 0.5, df / (df + t * t))


def t_quantile(p, df):
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -t_quantile(1.0 - p, df)
    want, lo, hi = 1.0 - p, 0.0, 1.0
    while t_tail(hi, df) > want:
        lo, hi = hi, hi * 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_tail(mid, df) > want:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def paired(base, cand, alpha):
    d = [c - b for b, c in zip(base, cand)]
    n = len(d)
    mean = sum(d) / n
    if n < 2:
        return {"mean": mean, "lo": -math.inf, "hi": math.inf}
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1))
    half = t_quantile(1.0 - alpha / 2.0, n - 1) * sd / math.sqrt(n)
    return {"mean": mean, "lo": mean - half, "hi": mean + half}


def verdict(iv, higher_is_better):
    if iv["lo"] > 0:
        return "better" if higher_is_better else "worse"
    if iv["hi"] < 0:
        return "worse" if higher_is_better else "better"
    return "no clear effect"


# ------------------------------------------------------------------ contestants


class Today:
    """Today's rule: always the engine's own pick (slot 0)."""

    def act(self, obs, info):
        return 0


class Fixed:
    """Always one slot (masked to the engine's pick when empty); for checks."""

    def __init__(self, k):
        self.k = k

    def act(self, obs, info):
        return self.k


class BuiltIn:
    """One of the engine's own rules (today, fifo, spt, cr, random), played inside the engine by `fabsim env --auto
    NAME` through the same episode code (docs/LONG-RESCORE.md)."""

    def __init__(self, name, fabsim=str(FABSIM)):
        self.name, self.fabsim = name, fabsim

    def play_episode(self, seed, shop, warmup_days, window_days, defects, picks=None):
        cmd = [self.fabsim, "env", str(shop), "--seed", str(seed), "--warmup", str(warmup_days), "--window", str(window_days),
               "--auto", self.name]
        if defects:
            cmd += ["--defects", ",".join(str(x) for x in defects)]
        if picks:
            cmd += ["--picks", str(picks)]
        p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if p.returncode != 0:
            raise RuntimeError(f"fabsim env refused: {p.stdout.strip() or p.stderr.strip()}")
        d = json.loads(p.stdout.strip().splitlines()[-1])
        return {"seed": seed, "score": d["score"], "decisions": d["decisions"], "picked_other": 0,
                "picked_other_by_group": {}, "fallbacks": d["fallbacks"], "pick_ns": d.get("pick_ns", float("nan")),
                "daily_wafers": d.get("daily_wafers")}


class Learned:
    """A PPO policy saved by `train`, played deterministically."""

    def __init__(self, path):
        from stable_baselines3 import PPO
        self.model = PPO.load(str(path), device="cpu")

    def act(self, obs, info):
        a, _ = self.model.predict(obs, deterministic=True)
        return int(a)


class Written:
    """A rule written as a Rust function (an E2 winner, or one Muse Spark Open writes), played in the sandbox by
    `fabrule env` through the same episode code."""

    def __init__(self, path, fabrule=str(ROOT / "target" / "release" / "fabrule"), cache=str(ROOT / "target" / "fabrule-cache")):
        self.path, self.fabrule, self.cache = str(path), fabrule, cache

    def play_episode(self, seed, shop, warmup_days, window_days, defects, picks=None):
        import subprocess
        cmd = [self.fabrule, "env", self.path, str(shop), "--seed", str(seed), "--warmup", str(warmup_days),
               "--window", str(window_days), "--cache", self.cache]
        if defects:
            cmd += ["--defects", ",".join(str(x) for x in defects)]
        if picks:
            cmd += ["--picks", str(picks)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"fabrule env refused: {p.stdout.strip() or p.stderr.strip()}")
        d = json.loads(p.stdout.strip().splitlines()[-1])
        return {"seed": seed, "score": d["score"], "decisions": d["decisions"], "picked_other": d["picked_other"],
                "picked_other_by_group": {}, "fallbacks": d["fallbacks"], "faults": d["faults"],
                "pick_ns": d.get("pick_ns", float("nan")), "daily_wafers": d.get("daily_wafers")}


def play(policy, seed, shop, fabsim=str(FABSIM), warmup_days=1.0, window_days=3.0, defects=None, picks=None):
    """One episode on one seed; the window's score and what the policy did. `picks`: a file for the pick made at
    each decision asked, one a line (regret B, `fabsim regret audit --picks`)."""
    if hasattr(policy, "play_episode"):
        return policy.play_episode(seed, shop, warmup_days, window_days, defects, picks=picks)
    from agent.fabgym_env import FabGymEnv
    env = FabGymEnv(shop, fabsim=fabsim, seeds=[seed], warmup_days=warmup_days, window_days=window_days, defects=defects,
                    picks=picks)
    try:
        obs, info = env.reset(options={"episode_seed": seed})
        picked_other, by_group, done, steps = 0, {}, env.last.get("done", False), 0
        while not done:
            a = policy.act(obs, info)
            n = len(env.last["cands"])
            if 0 < a < n:
                picked_other += 1
                g = env.last["group"]
                by_group[g] = by_group.get(g, 0) + 1
            obs, _, done, _, info = env.step(a)
            steps += 1
        return {"seed": seed, "score": info["score"], "decisions": info["decisions"], "picked_other": picked_other,
                "picked_other_by_group": by_group, "fallbacks": info["fallbacks"], "daily_wafers": info.get("daily_wafers")}
    finally:
        env.close()


# ------------------------------------------------------------------ training


def train(seeds, timesteps, workers, out, shop, fabsim=str(FABSIM), warmup_days=1.0, window_days=3.0, defects=None, n_steps=2048, seed=0):
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
    from agent.fabgym_env import FabGymEnv

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    seeds = list(seeds)

    def make(i):
        def thunk():
            # each worker takes every workers-th training seed
            mine = seeds[i::workers] or seeds
            return Monitor(FabGymEnv(shop, fabsim=fabsim, seeds=mine, warmup_days=warmup_days, window_days=window_days, defects=defects),
                           filename=str(out / f"monitor-{i}"))
        return thunk

    vec = (SubprocVecEnv if workers > 1 else DummyVecEnv)([make(i) for i in range(workers)])
    model = PPO("MlpPolicy", vec, n_steps=n_steps, batch_size=min(256, n_steps * workers), seed=seed, device="cpu", verbose=0)
    t0 = time.time()
    model.learn(total_timesteps=timesteps)
    model.save(str(out / "policy.zip"))
    vec.close()
    import gymnasium, stable_baselines3
    meta = {"model": "SMT2020" if Path(shop).is_dir() else "toy", "shop": str(shop), "seeds": seeds,
            "defects": list(defects) if defects else None, "warmup_days": warmup_days, "window_days": window_days,
            "timesteps": timesteps, "workers": workers, "n_steps": n_steps, "seed": seed, "seconds": round(time.time() - t0, 1),
            "versions": {"torch": torch.__version__, "stable_baselines3": stable_baselines3.__version__, "gymnasium": gymnasium.__version__},
            "note": NOTE}
    (out / "train.json").write_text(json.dumps(meta, indent=1))
    return meta


# ------------------------------------------------------------------ the contest

MEASURES = [("reward", True), ("moves", True), ("lots_finished", True), ("wait_lot_hours", False), ("breaches", False),
            ("cycle_days", False), ("wafers_per_day", True), ("mean_wip", False), ("hot_cycle_days", False)]


def kind_of(p):
    return {"BuiltIn": "built-in rule", "Today": "built-in rule", "Written": "written rule", "Learned": "learned",
            "Fixed": "fixed slot"}.get(type(p).__name__, "learned")


def timed_play(policy, seed, shop, fabsim, warmup_days, window_days, defects):
    """`play`, with the wall time per decision (the simulation included) and the time inside the policy's own code
    when it runs in Python."""
    import time
    inner = [0.0]
    if hasattr(policy, "act"):
        act = policy.act

        def counted(obs, info):
            t0 = time.perf_counter()
            try:
                return act(obs, info)
            finally:
                inner[0] += time.perf_counter() - t0
        policy.act = counted
    t0 = time.perf_counter()
    try:
        r = play(policy, seed, shop, fabsim, warmup_days, window_days, defects)
    finally:
        if hasattr(policy, "act"):
            policy.act = act
    wall = time.perf_counter() - t0
    n = max(1, r["decisions"])
    r["sec_per_decision"] = wall / n
    # inside the policy's own code: timed here for Python players, inside the engine for built-in and written rules
    r["act_ms"] = 1000.0 * inner[0] / n if hasattr(policy, "act") else r.get("pick_ns", float("nan")) / 1e6
    return r


def contest(policies, seeds, out, shop, fabsim=str(FABSIM), warmup_days=1.0, window_days=3.0, defects=None, protocol=None, sources=None):
    """Every contestant on every held-out seed; each against today's rule. `policies` must hold "today". Writes
    runs.tsv (every measure per seed), card.json (each against today) and policies.json (the registry: each policy, its
    kind and source, and the protocol), so any later policy, Meta's agent included, is scored the same way."""
    assert "today" in policies, "the contest needs today's rule"
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    seeds = list(seeds)
    # each run is kept as it lands; a contest started again picks up the runs already done
    done = {}
    prog = out / "progress.jsonl"
    if prog.exists():
        for line in prog.read_text().splitlines():
            r = json.loads(line)
            done[(r["contestant"], r["seed"])] = {**r, "picked_other_by_group": {}}
    runs, failed = {}, {}
    for name, p in policies.items():
        runs[name] = []
        for s in seeds:
            if (name, s) in done:
                runs[name].append(done[(name, s)])
                continue
            try:
                r = timed_play(p, s, shop, fabsim, warmup_days, window_days, defects)
            except Exception as err:  # a policy that cannot play is recorded, and the contest goes on
                failed[name] = str(err)[:2000]
                break
            runs[name].append(r)
            with open(prog, "a") as fh:
                fh.write(json.dumps({"contestant": name, **{k: v for k, v in r.items() if k != "picked_other_by_group"}}) + "\n")
    if "today" in failed:
        raise RuntimeError("today's rule failed: " + failed["today"])
    for name in failed:
        runs.pop(name, None)
    policies = {n: p for n, p in policies.items() if n in runs}
    num = lambda x: "nan" if x is None else repr(float(x))
    head = ["contestant", "seed"] + [m for m, _ in MEASURES] + ["decisions", "picked_other", "fallbacks", "sec_per_decision", "act_ms"]
    lines = ["\t".join(head)]
    for name, rs in runs.items():
        for r in rs:
            lines.append("\t".join([name, str(r["seed"])] + [num(r["score"].get(m)) for m, _ in MEASURES] +
                                   [str(r["decisions"]), str(r["picked_other"]), str(r["fallbacks"]), num(r["sec_per_decision"]), num(r["act_ms"])]))
    (out / "runs.tsv").write_text("\n".join(lines) + "\n")
    reg = {"protocol": {"name": protocol or f"warmup-{warmup_days:g}d-window-{window_days:g}d", "warmup_days": warmup_days,
                        "window_days": window_days, "seeds": seeds, "defects": list(defects) if defects else None,
                        "shop": str(shop), "warm_up_rule": "today", "note": NOTE},
           "policies": [{"name": n, "kind": kind_of(p), "source": (sources or {}).get(n, getattr(p, "path", getattr(p, "name", None)))}
                        for n, p in policies.items()],
           "failed": [{"name": n, "error": e} for n, e in failed.items()]}
    (out / "policies.json").write_text(json.dumps(reg, indent=1))
    others = [n for n in policies if n != "today"]
    alpha = 0.05 / max(1, len(others))
    card = {"seeds": seeds, "alpha_each": alpha, "defects": list(defects) if defects else None,
            "warmup_days": warmup_days, "window_days": window_days, "against_today": [], "note": NOTE,
            "today": {m: sum(r["score"][m] for r in runs["today"]) / len(seeds) for m, _ in MEASURES}}
    for name in others:
        ms = {}
        for m, higher in MEASURES:
            a = [r["score"].get(m) for r in runs["today"]]
            b = [r["score"].get(m) for r in runs[name]]
            if any(x is None for x in a + b):
                ms[m] = {"mean": None, "lo": None, "hi": None, "verdict": "not measured", "higher_is_better": higher}
                continue
            iv = paired(a, b, alpha)
            ms[m] = {**iv, "verdict": verdict(iv, higher), "higher_is_better": higher}
        picked = sum(r["picked_other"] for r in runs[name])
        decided = sum(r["decisions"] for r in runs[name])
        groups = {}
        for r in runs[name]:
            for g, n in r["picked_other_by_group"].items():
                groups[g] = groups.get(g, 0) + n
        card["against_today"].append({"name": name, "measures": ms, "picked_other_share": picked / decided if decided else 0.0,
                                      "picked_other_top_groups": sorted(groups.items(), key=lambda x: -x[1])[:8]})
    (out / "card.json").write_text(json.dumps(card, indent=1))
    return card


# ------------------------------------------------------------------ command line


def _seeds(s):
    a, b = s.split("..")
    return list(range(int(a), int(b)))


def main():
    ap = argparse.ArgumentParser(description="PPO over fabsim env, and the held-out contest (docs/RL-DEFECTS.md).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("train", "contest"):
        p = sub.add_parser(name)
        p.add_argument("--shop", default=str(ROOT / "data" / "smt2020" / "hvlm"))
        p.add_argument("--fabsim", default=str(FABSIM))
        p.add_argument("--seeds", required=True, help="A..B, B excluded")
        p.add_argument("--defects", default=None, help="H,L,R minutes, or omit for none")
        p.add_argument("--warmup", type=float, default=1.0)
        p.add_argument("--window", type=float, default=3.0)
        p.add_argument("--out", required=True)
        if name == "train":
            p.add_argument("--timesteps", type=int, required=True)
            p.add_argument("--workers", type=int, default=4)
            p.add_argument("--n-steps", type=int, default=2048)
        else:
            p.add_argument("--policy", action="append", default=[], help="NAME=policy.zip (PPO), NAME=rule.rs (a written rule) or NAME=builtin:fifo; today's rule is always in")
            p.add_argument("--protocol", default=None, help="a name for the protocol, kept in policies.json")
    a = ap.parse_args()
    defects = tuple(float(x) for x in a.defects.split(",")) if a.defects else None
    common = dict(shop=a.shop, fabsim=a.fabsim, warmup_days=a.warmup, window_days=a.window, defects=defects)
    if a.cmd == "train":
        assert a.workers <= 4, "at most 4 workers"
        print(json.dumps(train(_seeds(a.seeds), a.timesteps, a.workers, a.out, n_steps=a.n_steps, **common), indent=1))
    else:
        pols = {"today": Today()}
        for spec in a.policy:
            n, path = spec.split("=", 1)
            pols[n] = BuiltIn(path.split(":", 1)[1]) if path.startswith("builtin:") else Written(path) if path.endswith(".rs") else Learned(path)
        print(json.dumps(contest(pols, _seeds(a.seeds), a.out, protocol=a.protocol, **common), indent=1))


if __name__ == "__main__":
    main()
