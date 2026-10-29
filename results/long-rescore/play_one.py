"""One long-v1 run of one policy on one seed, defects off: its picks and its done line with wafers out day by day
(regret B and the day-by-day graphs, docs/LONG-RESCORE.md). On the SMT2020 model.
    python results/long-rescore/play_one.py POLICY SEED OUTDIR"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the repo, for `agent`
from agent import rl  # noqa: E402

name, seed, out = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
# today's rule is played inside the engine, as the other built-in rules are
pol = rl.Learned("results/rl-defects/ppo/policy.zip") if name == "ppo" else rl.BuiltIn(name)
r = rl.play(pol, seed, "data/smt2020/hvlm", warmup_days=130, window_days=60, picks=str(out / "picks" / f"{name}-{seed}.picks"))
(out / "runs" / f"{name}-{seed}.json").write_text(json.dumps({"policy": name, "seed": seed, **{k: v for k, v in r.items() if k != "picked_other_by_group"}}))
