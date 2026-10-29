"""Regret A and C from the long-v1 runs (docs/LONG-RESCORE.md). On the SMT2020 model.

A, best in hindsight: on each seed, the best reward any policy of the library got; a policy's regret is that best
minus its own. C, capacity: the expected ceiling (results/long-rescore/ceiling.json) minus the wafers a day a policy
got. Mean over the 10 seeds with a 95% t-interval (paired by seed). Defects only add holds, so the ceiling of the
defects-off shop is also an upper bound with defects on (looser there).
"""
import json, math, statistics as st
from pathlib import Path

HERE = Path(__file__).parent
T975_9 = 2.2621571627409915  # t, 9 degrees of freedom


def ci(xs):
    m = st.mean(xs)
    h = T975_9 * st.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0
    return {"mean": m, "lo": m - h, "hi": m + h}


def runs(d):
    rows = {}
    for k in ("rules", "learned"):
        for line in (HERE / f"{k}-defects-{d}" / "progress.jsonl").read_text().splitlines():
            r = json.loads(line)
            rows.setdefault(r["contestant"], {})[r["seed"]] = r
    return rows


ceiling = json.loads((HERE / "ceiling.json").read_text())["wafers_per_day"]
out = {"protocol": "long-v1", "model": "SMT2020", "ceiling_wafers_per_day": ceiling,
       "library": None, "defects": {}}
for d in ("off", "on"):
    rows = runs(d)
    seeds = sorted(next(iter(rows.values())))
    best = {s: max(rows[p][s]["score"]["reward"] for p in rows) for s in seeds}
    best_by = {s: max(rows, key=lambda p: rows[p][s]["score"]["reward"]) for s in seeds}
    out["library"] = sorted(rows)
    res = {}
    for p in rows:
        sc = [rows[p][s]["score"] for s in seeds]
        res[p] = {
            "regret_a_reward": ci([best[s] - rows[p][s]["score"]["reward"] for s in seeds]),
            "regret_c_wafers_per_day": ci([ceiling - x["wafers_per_day"] for x in sc]),
            "wafers_per_day": ci([x["wafers_per_day"] for x in sc]),
            "cycle_days": ci([x["cycle_days"] for x in sc]),
            "reward": ci([x["reward"] for x in sc]),
            "breaches": ci([x["breaches"] for x in sc]),
            "above_ceiling_runs": sum(x["wafers_per_day"] > ceiling for x in sc),
        }
    out["defects"][d] = {"best_by_seed": best_by, "policies": res}
(HERE / "regret-ac.json").write_text(json.dumps(out, indent=1))
for d in ("off", "on"):
    print(f"defects {d}: best on each seed:", sorted(set(out['defects'][d]['best_by_seed'].values())))
    for p, r in sorted(out["defects"][d]["policies"].items(), key=lambda kv: kv[1]["regret_a_reward"]["mean"]):
        a, c = r["regret_a_reward"], r["regret_c_wafers_per_day"]
        print(f"  {p:7s} A {a['mean']:9.0f} ({a['lo']:.0f} to {a['hi']:.0f})   C {c['mean']:6.1f} wafers/day ({c['lo']:.1f} to {c['hi']:.1f})  above ceiling {r['above_ceiling_runs']}")
