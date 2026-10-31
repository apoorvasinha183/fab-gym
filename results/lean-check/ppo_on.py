"""PPO with defects on (long-v1, docs/LEAN-CHECK.md): play each held-out seed again, writing its picks this time, and
check the replayed score equals the scored run's in results/long-rescore/learned-defects-on. On the SMT2020 model.
    python results/lean-check/ppo_on.py SEED"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import rl  # noqa: E402

seed = int(sys.argv[1])
picks = ROOT / "results" / "lean-check" / "picks" / f"ppo-on-{seed}.picks"
picks.parent.mkdir(parents=True, exist_ok=True)
r = rl.play(rl.Learned(str(ROOT / "results/rl-defects/ppo/policy.zip")), seed, str(ROOT / "data/smt2020/hvlm"),
            warmup_days=130, window_days=60, defects=(120, 240, 60), picks=str(picks))
old = None
for line in (ROOT / "results/long-rescore/learned-defects-on/progress.jsonl").read_text().splitlines():
    d = json.loads(line)
    if d.get("contestant") == "ppo" and d.get("seed") == seed:
        old = d["score"]
same = old is not None and all(abs(r["score"][k] - old[k]) < 1e-6 for k in ("wafers_per_day", "breaches", "moves"))
print(json.dumps({"seed": seed, "same_as_scored": same, "wafers_per_day": r["score"]["wafers_per_day"],
                  "scored_wafers_per_day": old and old["wafers_per_day"]}))
sys.exit(0 if same else 3)
