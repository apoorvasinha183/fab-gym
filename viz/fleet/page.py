#!/usr/bin/env python3
"""The fleet on the rails, as a page (docs/FLEET.md): today's US building's bays and tools from its scene, the one-way
track and what the fleet did on it in an hour, for two fleet sizes, replayed on a canvas.

    python3 viz/fleet/page.py [--scene data/layout-real-dd/scene-optimised.json]
        [--trace data/layout-real-dd/fleet-90.json --trace data/layout-real-dd/fleet-160.json]
        [--out data/layout-real-dd/fleet-page/index.html]

Write the traces first with `fabsim fleet-trace --vehicles N`. Standard library only. On the SMT2020 model, a
gigafab-style layout of our own design; not a real fab.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def r(x, d=2):
    return round(x, d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default=str(ROOT / "data/layout-real-dd/scene-optimised.json"))
    ap.add_argument("--trace", action="append")
    ap.add_argument("--out", default=str(ROOT / "data/layout-real-dd/fleet-page/index.html"))
    a = ap.parse_args()
    traces = a.trace or [str(ROOT / "data/layout-real-dd/fleet-90.json"), str(ROOT / "data/layout-real-dd/fleet-160.json")]
    s = json.loads(Path(a.scene).read_text())
    plan = {
        "fabs": [[r(c["x0"]), r(c["x1"]), r(c["y0"]), r(c["y1"]), c["label"]] for c in s["campus"] if c["kind"] in ("fab", "bridge")],
        "bays": [[r(b["x0"]), r(b["x1"]), r(b["y0"]), r(b["y1"]), b["area"]] for b in s["bays"]],
        "tools": [[r(t["x0"]), r(t["x1"]), r(t["y0"]), r(t["y1"])] for t in s["tools"]],
        "stockers": [[r(t["x0"]), r(t["x1"]), r(t["y0"]), r(t["y1"])] for t in s["stockers"]],
    }
    fleets = []
    track = None
    for p in traces:
        j = json.loads(Path(p).read_text())
        if track is None:
            track = {"nodes": j["nodes"], "edges": j["edges"], "spine": j["spine"]}
        assert j["nodes"] == track["nodes"] and j["edges"] == track["edges"], "the traces must share one track"
        fleets.append({"vehicles": j["vehicles"], "from": j["from"], "to": j["to"], "entries": j["entries"], "hoists": j["hoists"]})
    data = {"what": json.loads(Path(traces[0]).read_text())["what"], "plan": plan, "track": track, "fleets": fleets}
    html = (Path(__file__).parent / "template.html").read_text().replace("{{DATA}}", json.dumps(data, separators=(",", ":")))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"wrote {out}: {len(track['nodes'])} nodes, {len(track['edges'])} stretches, fleets {[f['vehicles'] for f in fleets]}, {len(html) // 1024} KB")


if __name__ == "__main__":
    main()
