"""Bundle a 30-minute simulator recording so desktop and web visitors can explore offline.

Run after web/build-3d.sh and prep.py. No network or model calls are made.
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import helper  # noqa: E402


def main():
    campus = json.loads((ROOT / "viz/fab3d/data/campus.json").read_text())
    building = json.loads((ROOT / "web/data/building.json").read_text())
    if [(t[0], t[4:8]) for t in campus["tools"]] != [(t[0], t[1:5]) for t in building["tools"]]:
        raise SystemExit("Rebuild campus.json with prep.py: its tool positions differ from the simulation inputs.")
    with tempfile.TemporaryDirectory() as d:
        h = helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True)
        info = h.fab3d_run({"seed": 1, "days": 0.5})
        if "error" in info:
            raise SystemExit(info["error"])
        run = h.fab3d_runs[info["run"]]
        frames = [run.state(t, list(run.cells), span=2.0) for t in range(360, 390, 2)]
        data = {"about": "Recorded simulator demo, seed 1, 06:00–06:30; loops. SMT2020 testbed, not a real fab.",
                "seed": 1, "start": 360, "end": 390, "every": 2, "frames": frames}
        path = ROOT / "viz/fab3d/data/demo.json"
        path.write_text(json.dumps(data, separators=(",", ":")) + "\n")
        print(f"Recorded {len(frames)} frames for all {len(campus['tools'])} tools: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
