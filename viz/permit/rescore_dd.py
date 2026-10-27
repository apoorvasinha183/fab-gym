"""Design development back into Fab Gym (docs/DESIGN-DEV.md, DD2): what the cross aisles cost the fab, on the SMT2020
model.

Taken as service corridors (the stricter reading), the chases need a door into the fab area within 75 ft of every
point (IBC 415.11.3.3). Where the tools line a 60 m chase end to end there is no place for one, so the layout leaves a
cross aisle at mid-depth on every wall of tools (`fabsim layout --real --chase 1.6 --cross 1.6`). This scores the 1.6 m
chase layout D10 rescored against the same layout with the cross aisles, on the same seeds (`fabsim layout-score`,
paired t intervals, Bonferroni over its five measures), and writes results/layout-real-dd/rescore.json and rescore.md.

    .venv/bin/python viz/permit/rescore_dd.py [--cross 1.6] [--seeds 10] [--threads 4]

One heavy job: the runs are niced and use at most 4 threads. A gigafab-style layout of our own design on the SMT2020
model; not a real fab.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FABSIM = ROOT / "target/release/fabsim"
TRUTH = "On the SMT2020 model. A layout of our own design. Not a real fab."


def sh(args):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(["nice", "-n", "10", *map(str, args)], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chase", type=float, default=1.6)
    ap.add_argument("--cross", type=float, default=1.6)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    out = ROOT / "results/layout-real-dd"
    data = ROOT / "data/layout-real-dd"
    sh([FABSIM, "layout", "--real", "--chase", a.chase, "--cross", a.cross, "--out", out, "--data", data])
    pair = data / "pair"
    pair.mkdir(parents=True, exist_ok=True)
    # the score command compares "plain" with "optimised": here they are the optimised plan without and with the aisles
    shutil.copyfile(ROOT / "data/layout-real-permit/optimised.shop.txt", pair / "plain.shop.txt")
    shutil.copyfile(data / "optimised.shop.txt", pair / "optimised.shop.txt")
    sh([FABSIM, "layout-score", "--real", "--data", pair, "--out", out / "score", "--seeds", a.seeds,
        "--threads", min(a.threads, 4)])
    before = json.loads((ROOT / "results/layout-real-permit/layout.json").read_text())
    after = json.loads((out / "layout.json").read_text())
    score = json.loads((out / "score/score.json").read_text())
    mean = lambda v: sum(v) / len(v)
    measures = [{"name": m["name"], "before": mean(m["plain"]), "after": mean(m["optimised"]), "diff": m["mean"],
                 "lo": m["lo"], "hi": m["hi"], "verdict": m["verdict"]} for m in score["measures"]]
    lb, la = before["plans"]["optimised"]["lengths"], after["plans"]["optimised"]["lengths"]
    R = {
        "truth": TRUTH + " Effect in a real fab: cannot say.",
        "question": "Taken as service corridors, the chases need a door into the fab area within 75 ft of every point "
                    "(IBC 415.11.3.3); where tools line a chase end to end, a cross aisle at mid-depth makes room for it. "
                    "What do the cross aisles cost the fab?",
        "cites": ["IBC 415.11.3.3"],
        "chase_m": after["assumed"]["chase"],
        "cross_before_m": before["assumed"].get("cross", 0.0),
        "cross_after_m": after["assumed"]["cross"],
        "bays": {"before": len(before["plans"]["optimised"]["bays"]), "after": len(after["plans"]["optimised"]["bays"])},
        "lengths_m": {"before": lb, "after": la},
        "hoist_m_per_day": {"before": before["plans"]["optimised"]["metres_per_day"],
                            "after": after["plans"]["optimised"]["metres_per_day"]},
        "seeds": len(score["seeds"]),
        "seed_list": score["seeds"],
        "days": score["days"], "warmup": score["warmup"], "alpha_each": score["alpha_each"],
        "preregistered_design": score["preregistered"],
        "how": "fabsim layout-score on the same seeds: the optimised plan with 1.6 m chases against the same with a "
               "cross aisle on every wall; paired t intervals, each at the stated level, Bonferroni over five measures.",
        "measures": measures,
    }
    (out / "rescore.json").write_text(json.dumps(R, indent=1) + "\n")
    hb, ha = R["hoist_m_per_day"]["before"], R["hoist_m_per_day"]["after"]
    md = ["# What the cross aisles cost the fab\n", TRUTH + "\n",
          f"The question: {R['question']}\n",
          f"Cross aisle {R['cross_before_m']} m before, {R['cross_after_m']} m after; chases {R['chase_m']} m. "
          f"Bays {R['bays']['before']} before, {R['bays']['after']} after; buildings {lb} m before, {la} m after. "
          f"Hoist travel a day at the release rates: {hb / 1000:.0f} km before, {ha / 1000:.0f} km after "
          f"({100 * (ha - hb) / hb:+.1f}%).\n",
          f"{R['seeds']} paired seeds, {R['days']:.0f} days, measured over days {R['warmup']:.0f} to {R['days']:.0f}; "
          f"each interval at level {R['alpha_each']:.3f} (Bonferroni over five, so all cover at once with probability "
          "at least 95%).\n",
          "| measure | before | after | after minus before (95%) | verdict |", "|---|---|---|---|---|"]
    for m in measures:
        md.append(f"| {m['name']} | {m['before']:.3f} | {m['after']:.3f} | {m['diff']:+.3f} ({m['lo']:+.3f} to "
                  f"{m['hi']:+.3f}) | {m['verdict']} |")
    (out / "rescore.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
