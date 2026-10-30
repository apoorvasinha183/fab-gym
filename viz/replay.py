"""The replay's data: the campus under today's rule and under a written rule, on one seed (docs/REPLAY.md).

From the SMT2020 testbed, on a gigafab-style layout of our own design; not a real fab.

    python3 viz/replay.py RULE.rs --name NAME [--hand-written] [--card CARD.json]
        [--seed 3000] [--day 30] [--hours 6] [--out data/layout-real/replay] [--copy]

Writes trace-today.json, trace-rule.json, scene-today.json, scene-rule.json and replay.json; --copy also puts
the scenes and replay.json in viz/godot-real/data/replay/ for the compare scene.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "viz" / "look"))

import scene as real_scene  # noqa: E402

FABRULE = ROOT / "target" / "release" / "fabrule"
LAYOUT = ROOT / "results" / "layout-real" / "layout.json"
DATA = ROOT / "data" / "layout-real"
TODAY = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { if c.is_default > 0.5 { 0.0 } else { 1.0 } }"
EVERY = 10.0
WHAT = ("Two copies of one campus from the SMT2020 testbed, a gigafab-style layout of our own design; not a real fab. "
        "Same seed, same hours: today's rule on one side, the written rule on the other.")


def run_trace(src_path, out, seed, day, hours):
    p = subprocess.run([str(FABRULE), "trace", str(src_path), "--real", "--data", str(DATA), "--plan", "optimised",
                        "--seed", str(seed), "--day", str(day), "--hours", str(hours), "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"fabrule trace failed: {p.stdout.strip()} {p.stderr.strip()}")
    return json.loads(p.stdout)


def series(tr, times, group):
    a = float(tr["from"])
    steps = [s for lot in tr["lots"] for s in lot["steps"]]
    moves = [sum(1 for s in steps if a < s[2] <= t) for t in times]
    wait = [round(sum(max(0.0, min(s[1], t) - max(s[0], a)) for s in steps) / 60.0, 4) for t in times]
    q = [sum(1 for s in steps if s[4] == group and s[0] <= t < s[1]) for t in times]
    return {"moves": moves, "wait_lot_hours": wait, "queue": q}


def queues(tr, times):
    """Every group's queue at each time: group -> list."""
    out = {}
    for lot in tr["lots"]:
        for s in lot["steps"]:
            row = out.setdefault(s[4], [0] * len(times))
            for i, t in enumerate(times):
                if s[0] <= t < s[1]:
                    row[i] += 1
    return out


def card_line(card_path, sha):
    if card_path is None:
        return None
    card = json.loads(Path(card_path).read_text())
    for f in card.get("finalists", []):
        if f["source_sha256"] == sha:
            rew = [m for m in f["held_out"]["vs_today"] if m["key"] == "reward"][0]["interval"]
            signed = f"signed by {card['signed_by']}" if card.get("signed_by") else "not signed"
            return (f"Scored on held-out seeds {card['seeds'][0]} to {card['seeds'][-1]}: reward against today "
                    f"{rew['mean']:+.2f} (95% {rew['lo']:+.2f} to {rew['hi']:+.2f}); card {signed}")
    raise ValueError("the card has no finalist with this rule's source")


def make(rule_path, name, hand_written, card, seed, day, hours, out, copy=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    src = Path(rule_path).read_text().strip()
    sha = hashlib.sha256(src.encode()).hexdigest()
    (out / "today.rs").write_text(TODAY)
    (out / "rule.rs").write_text(src)
    runs = {}
    for side in ("today", "rule"):
        runs[side] = run_trace(out / f"{side}.rs", out / f"trace-{side}.json", seed, day, hours)
    tr = {k: json.loads((out / f"trace-{k}.json").read_text()) for k in ("today", "rule")}
    scenes = {}
    for k in ("today", "rule"):
        scenes[k] = real_scene.build(LAYOUT, out / f"trace-{k}.json", "optimised")
        (out / f"scene-{k}.json").write_text(json.dumps(scenes[k], separators=(",", ":")))
    a, b = float(tr["today"]["from"]), float(tr["today"]["to"])
    times = []
    x = a
    while x <= b + 1e-9:
        times.append(round(x, 2))
        x += EVERY
    qa, qb = queues(tr["today"], times), queues(tr["rule"], times)
    zero = [0] * len(times)

    def gap(g):
        return abs(sum(r - t for r, t in zip(qb.get(g, zero), qa.get(g, zero)))) / len(times)

    watch = max(sorted(set(qa) | set(qb)), key=gap)
    sc = scenes["today"]
    mine = [t for t in sc["tools"] if t["g"] == watch]
    at = ([round(sum((t["x0"] + t["x1"]) / 2 for t in mine) / len(mine), 2),
           round(sum((t["y0"] + t["y1"]) / 2 for t in mine) / len(mine), 2)] if mine
          else [round((sc["ground"]["x0"] + sc["ground"]["x1"]) / 2, 2), 0.0])
    box = ([min(t["x0"] for t in mine), min(t["y0"] for t in mine), max(t["x1"] for t in mine),
            max(t["y1"] for t in mine)] if mine else None)
    g = sc["groups"][watch]
    rep = {
        "what": WHAT,
        "seed": seed,
        "from": a,
        "to": b,
        "every": EVERY,
        "rule": {"name": name, "source": src, "sha256": sha, "hand_written": bool(hand_written),
                 "card": card_line(card, sha),
                 "decisions": runs["rule"]["decisions"], "faults": runs["rule"]["faults"]},
        "watch": {"group": watch, "name": g["name"], "area": g["area"], "at": at, "box": box,
                  "why": "the tool group whose mean queue differs most between the two sides over the window",
                  "gap": round(gap(watch), 4)},
        "series": {"t": times, "today": series(tr["today"], times, watch), "rule": series(tr["rule"], times, watch)},
        "traces": {k: str((out / f"trace-{k}.json").resolve()) for k in ("today", "rule")},
    }
    (out / "replay.json").write_text(json.dumps(rep, indent=1))
    if copy:
        dst = ROOT / "viz" / "godot-real" / "data" / "replay"
        dst.mkdir(parents=True, exist_ok=True)
        for n in ("scene-today.json", "scene-rule.json", "replay.json"):
            shutil.copy(out / n, dst / n)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rule")
    ap.add_argument("--name", required=True)
    ap.add_argument("--hand-written", action="store_true")
    ap.add_argument("--card")
    ap.add_argument("--seed", type=int, default=3000)
    ap.add_argument("--day", type=int, default=30)
    ap.add_argument("--hours", type=int, default=6)
    ap.add_argument("--out", default=str(DATA / "replay"))
    ap.add_argument("--copy", action="store_true")
    a = ap.parse_args()
    rep = make(a.rule, a.name, a.hand_written, a.card, a.seed, a.day, a.hours, a.out, a.copy)
    s = rep["series"]
    print(f"watch {rep['watch']['name']} ({rep['watch']['area']}); by the end: moves today {s['today']['moves'][-1]}, "
          f"rule {s['rule']['moves'][-1]}; lot-hours waited today {s['today']['wait_lot_hours'][-1]:.0f}, "
          f"rule {s['rule']['wait_lot_hours'][-1]:.0f}")


if __name__ == "__main__":
    main()
