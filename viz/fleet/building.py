#!/usr/bin/env python3
"""The real building for the floor page's Live view (docs/LIVE-REAL.md): the halls, bays, every tool at its place
with its kind and height, the area labels, the stockers and the simulator's track, from today's US building, and the
shop the browser simulator runs (the layout with 160 vehicles).

    python3 viz/fleet/building.py [--data data/layout-real-dd] [--out web/data]

Needs `fabsim fleet-trace --vehicles 160` first (for the track). Standard library only. From the SMT2020 testbed, a
gigafab-style layout of our own design; not a real fab.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = "fleet\t160\t3.0\t1.0\t2\t60.0\tnearest\n"  # docs/FLEET.md: gap 3 m, hoists 1 min (Yang 2023), 2 ports


def r(x):
    return round(x, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/layout-real-dd"))
    ap.add_argument("--out", default=str(ROOT / "web/data"))
    a = ap.parse_args()
    data, out = Path(a.data), Path(a.out)
    s = json.loads((data / "scene-optimised.json").read_text())
    tr = json.loads((data / "fleet-160.json").read_text())
    shop = (data / "optimised.shop.txt").read_text()
    names = [g["name"] for g in s["groups"]]
    drawn = {names[t["g"]] for t in s["tools"]}
    groups = [line.split("\t")[1] for line in shop.splitlines() if line.startswith("group\t")]
    b = {
        "what": "Today's US building from the SMT2020 testbed: a gigafab-style layout of our own design, not a real fab.",
        # Lou needs the same area names as the scene, without a Godot asset build.
        "areas": s["areas"],
        "group_areas": {g["name"]: g["area"] for g in s["groups"]},
        "fabs": [[r(c["x0"]), r(c["x1"]), r(c["y0"]), r(c["y1"]), c["label"], c["kind"]] for c in s["campus"] if c["kind"] in ("fab", "bridge")],
        "bays": [[r(x["x0"]), r(x["x1"]), r(x["y0"]), r(x["y1"]), x["area"], x["phase"], x["side"]] for x in s["bays"]],
        "tools": [[names[t["g"]], r(t["x0"]), r(t["x1"]), r(t["y0"]), r(t["y1"]), t["kind"], t["wall"], t["h"]] for t in s["tools"]],
        "stockers": [[r(x["x0"]), r(x["x1"]), r(x["y0"]), r(x["y1"])] for x in s["stockers"]],
        "labels": [[x["text"], r(x["x"]), r(x["y"]), x["area"]] for x in s["labels"]],
        "holding": [g for g in groups if g not in drawn],
        "track": {"nodes": tr["nodes"], "edges": tr["edges"]},
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "building.json").write_text(json.dumps(b, separators=(",", ":")))
    (out / "shop-real.txt").write_text(shop + ("" if shop.endswith("\n") else "\n") + FLEET)
    print(f"wrote {out}/building.json ({len(b['tools'])} tools, {len(b['track']['edges'])} stretches, holding {b['holding']}) and shop-real.txt")


if __name__ == "__main__":
    main()
