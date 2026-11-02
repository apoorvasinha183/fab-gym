"""Copy what the 3D fab reads into viz/fab3d/data/ (docs/FAB-3D.md): the campus with its cells, the models, the
building, the teaching stages and the silicon film as Ogg Theora. The data folder is never committed. From the
SMT2020 testbed; a gigafab-style layout of our own design; not a real fab.

    python3 viz/fab3d/prep.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import fab3d  # noqa: E402

PROJ = ROOT / "viz/fab3d"
DATA = PROJ / "data"
BUILDING = ROOT / "web/data/building.json"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
MODELS = ROOT / "data/fab3d/models"
BIM = ROOT / "data/layout-real-dd/bim/fab-building.glb"
FILM = ROOT / "data/film/out/from-sand-to-chip-720p.mp4"


def stages():
    """The ten stages of 'How a chip is made' (web/stages.js), read through Node so the words are the page's own."""
    js = "const s=require(process.argv[1]);console.log(JSON.stringify(s.STAGES.map(x=>({key:x.key,name:x.name,areas:x.areas,color:x.color,what:x.what,why:x.why,note:x.note}))))"
    p = subprocess.run(["node", "-e", js, str(ROOT / "web/stages.js")], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    b = json.loads(BUILDING.read_text())
    s = json.loads(SCENE.read_text())
    area_of = {g["name"]: g["area"] for g in s["groups"]}
    cells = fab3d.cells(b)
    campus = {
        "about": "Today's US building on the SMT2020 testbed: a gigafab-style layout of our own design, not a real fab.",
        "heights": {k: s[k] for k in ("clean_z", "port_z", "rail_z", "ride_z")},
        "kinds": s["kinds"],
        "areas": s["areas"],
        "tools": [[t[0], area_of.get(t[0], ""), t[5], t[6], t[1], t[2], t[3], t[4], t[7]] for t in b["tools"]],
        "tool_fields": ["group", "area", "kind", "phase", "x0", "x1", "y0", "y1", "h"],
        "stockers": b["stockers"],
        "fabs": b["fabs"],
        "bays": b["bays"],
        "labels": b["labels"],
        "track": b["track"],
        "cell_size": cells["size"],
        "cells": cells["cells"],
        "stages": stages(),
    }
    (DATA / "campus.json").write_text(json.dumps(campus, separators=(",", ":")))
    (DATA / "models").mkdir(exist_ok=True)
    for f in sorted(MODELS.glob("*.glb")):
        dst = DATA / "models" / f.name
        if not dst.exists() or dst.read_bytes() != f.read_bytes():
            shutil.copyfile(f, dst)
    if BIM.exists():
        shutil.copyfile(BIM, DATA / "fab-building.glb")
    film = DATA / "film" / "from-sand-to-chip.ogv"
    if FILM.exists() and not film.exists():
        film.parent.mkdir(exist_ok=True)
        blender = Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"
        subprocess.run(["nice", "-n", "10", str(blender), "-b", "--factory-startup", "-P", str(PROJ / "film_ogv.py"), "--",
                        str(FILM), str(film)], check=True, capture_output=True)
    print(f"campus: {len(campus['tools'])} tools in {len(campus['cells'])} cells; "
          f"{len(list((DATA / 'models').glob('*.glb')))} models; film {'yes' if film.exists() else 'no'}")


if __name__ == "__main__":
    main()
