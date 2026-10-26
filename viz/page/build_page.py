"""Build the campus page (a private artifact) from results/layout/: the 2D floor plans,
the numbers and the films' asset URLs.

    python3 viz/page/build_page.py OUT.html [--blender URL] [--godot URL]
"""

import json
import sys
from pathlib import Path

here = Path(__file__).parent
root = here.parent.parent
args = sys.argv[1:]
out = Path(args[0])


def opt(flag):
    return args[args.index(flag) + 1] if flag in args else ""


lay = json.loads((root / "results/layout/layout.json").read_text())
score = json.loads((root / "results/layout/score.json").read_text())


def r(x, k=2):
    return round(x, k)


plans = {}
for name, p in lay["plans"].items():
    plans[name] = {
        "metres": round(p["metres_per_day"]),
        "lengths": p["lengths"],
        "sides": p["sides"],
        "bays": [[b["phase"], b["side"], b["area"], r(b["x0"]), r(b["x1"])] for b in p["bays"]],
        "tools": [[t[0], t[1], t[2], r(t[4]), r(t[5]), r(t[6]), r(t[7])] for t in p["tools"]],
        "places": [None if q is None else [q[0], q[1], r(q[3]), r(q[4])] for q in p["places"]],
    }
data = {
    "assumed": lay["assumed"],
    "groups": [[g["name"], g["area"], g["tools"]] for g in lay["groups"]],
    "flows": [[f[0], f[1], r(f[2], 3)] for f in lay["flows"]],
    "crossings": r(lay["crossings_per_day"], 1),
    "plans": plans,
    "score": [
        {"name": m["name"], "plain": r(sum(m["plain"]) / len(m["plain"]), 3), "optimised": r(sum(m["optimised"]) / len(m["optimised"]), 3),
         "flat": r(sum(m["flat"]) / len(m["flat"]), 3), "mean": r(m["mean"], 3), "lo": r(m["lo"], 3), "hi": r(m["hi"], 3), "verdict": m["verdict"]}
        for m in score["measures"]
    ],
}
html = (here / "campus.html").read_text()
html = html.replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
html = html.replace("{{BLENDER}}", opt("--blender")).replace("{{GODOT}}", opt("--godot"))
out.write_text(html)
print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
