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
from viz.fab3d.prepare_film import prepare as prepare_film  # noqa: E402

PROJ = ROOT / "viz/fab3d"
DATA = PROJ / "data"
BUILDING = ROOT / "web/data/building.json"
SCENE = ROOT / "data/layout-real/scene-optimised.json"
MODELS = ROOT / "data/fab3d/models"
BIM = ROOT / "data/layout-real-dd/bim/fab-building.glb"
PERMIT = ROOT / "data/layout-real-dd/permit-cd/us/boxes.json"
SHOP = ROOT / "web/data/shop-real.txt"
POLYHAVEN = Path.home() / "fab-gym-downloads/polyhaven"     # CC0 textures and sky, downloaded 2 Nov (SOURCES.md there)
# the hall's two films (cinema.gd FILMS), converted to Ogg Theora; data/film/out/ holds the cuts, never committed
FILMS = [(ROOT / "data/film/out/sand-to-chip-v10.mp4", "sand-to-chip-v10.ogv"),
         (ROOT / "data/film/out/crime-and-punishment-acted.mp4", "crime-and-punishment-acted.ogv")]


def tool_phase(tool, fabs):
    """The building's column 6 is wall orientation; phase comes from the containing fab."""
    x, y = (tool[1] + tool[2]) / 2, (tool[3] + tool[4]) / 2
    halls = sorted((f for f in fabs if f[5] == "fab"), key=lambda f: f[0])
    for phase, f in enumerate(halls):
        if f[0] <= x <= f[1] and f[2] <= y <= f[3]:
            return phase
    raise ValueError(f"Tool {tool[0]} lies outside both fab buildings")


def stages():
    """The ten stages of 'How a chip is made' (web/stages.js), read through Node so the words are the page's own."""
    js = "const s=require(process.argv[1]);console.log(JSON.stringify(s.STAGES.map(x=>({key:x.key,name:x.name,areas:x.areas,color:x.color,what:x.what,why:x.why,note:x.note}))))"
    p = subprocess.run(["node", "-e", js, str(ROOT / "web/stages.js")], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def _texture_import(tex, normal):
    """Godot's import settings for a texture: compressed on the GPU, mipmapped (no shimmer at a distance), and marked
    as a normal map when it is one. Kept beside the copy so a fresh checkout imports it the same way."""
    imp = tex.with_name(tex.name + ".import")
    want = {"compress/mode": "2", "compress/normal_map": "1" if normal else "2", "mipmaps/generate": "true",
            "detect_3d/compress_to": "0"}
    if not imp.exists():
        imp.write_text('[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\n\n[params]\n\n'
                       + "".join(f"{k}={v}\n" for k, v in want.items()))
        return
    lines, seen = [], set()
    for line in imp.read_text().splitlines():
        k = line.split("=", 1)[0]
        if k in want:
            line, _ = f"{k}={want[k]}", seen.add(k)
        lines.append(line)
    lines += [f"{k}={v}" for k, v in want.items() if k not in seen]
    new = "\n".join(lines) + "\n"
    if new != imp.read_text():
        imp.write_text(new)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    b = json.loads(BUILDING.read_text())
    s = json.loads(SCENE.read_text())
    area_of = {g["name"]: g["area"] for g in s["groups"]}
    cells = fab3d.cells(b)
    campus = {
        "schema_version": 2,
        "about": "Today's US building on the SMT2020 testbed: a gigafab-style layout of our own design, not a real fab.",
        "heights": {k: s[k] for k in ("clean_z", "port_z", "rail_z", "ride_z")},
        "kinds": s["kinds"],
        "areas": s["areas"],
        "tools": [[t[0], area_of.get(t[0], ""), t[5], tool_phase(t, b["fabs"]), t[1], t[2], t[3], t[4], t[7]] for t in b["tools"]],
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
    permit = json.loads(PERMIT.read_text())
    campus["entrance"] = fab3d.entrance(permit)
    campus["exterior"] = fab3d.exterior(permit)
    campus["drone"] = fab3d.drone(b, campus["exterior"], campus["entrance"], SHOP.read_text())
    # the cinema's floors (docs/FAB-3D.md, F11), so the visitor stands on its steps, aisles and ramp
    cp = ROOT / "data/cinema/plan.json"
    if cp.exists():
        pl = json.loads(cp.read_text())
        rooms = {r["name"]: r for r in pl["rooms"]}
        campus["cinema"] = {"hall": rooms["hall"]["box"],
                            "floors": [[r["x0"], r["x1"], r["level"]] for r in pl["rows"] if r["block"] == "centre"]
                                      + [[a["box"][0], a["box"][2], a["level"]] for a in pl["cross_aisles"]],
                            "ramp": {"box": rooms["ramp"]["box"], "rise": rooms["ramp"]["rises_to"], "runs": rooms["ramp"]["runs"],
                                     "run_m": rooms["ramp"]["run_m"], "landing_m": pl["choices"]["landing_m"]},
                            "seats": [[q["id"], q["x"], q["y"], q["level"]] for q in pl["seats"]],
                            "screen": pl["screen"]}
        # what Blender built from the plan (viz/blender/buildings/cinema.py): the floor map and the poster cases
        bj = ROOT / "data/cinema/built.json"
        if bj.exists():
            shutil.copyfile(bj, DATA / "cinema-built.json")
    (DATA / "campus.json").write_text(json.dumps(campus, separators=(",", ":")))
    (DATA / "models").mkdir(exist_ok=True)
    for f in sorted(MODELS.glob("*.glb")):
        dst = DATA / "models" / f.name
        if not dst.exists() or dst.read_bytes() != f.read_bytes():
            shutil.copyfile(f, dst)
    if BIM.exists():
        shutil.copyfile(BIM, DATA / "fab-building.glb")
    if POLYHAVEN.exists():
        # the CC0 texture sets and the sky: copied, never committed (data/ is ignored)
        for f in sorted(POLYHAVEN.glob("*/*")):
            if f.suffix in (".jpg", ".png", ".hdr") and f.parent.name != "_catalogue":
                dst = DATA / "textures" / f.parent.name / f.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists() or dst.stat().st_size != f.stat().st_size:
                    shutil.copyfile(f, dst)
                if f.suffix == ".jpg":
                    _texture_import(dst, normal="_nor_" in f.name)
    # greyed copies of three CC0 colour maps, which the scene tints: the grass scan is mostly brown leaves, the
    # cladding is red, the roof gravel sandy
    for asset, eq in (("leafy_grass", "contrast=1.15"), ("box_profile_metal_sheet", "brightness=0.32:contrast=0.6"),
                      ("gravel_concrete", "contrast=1.05")):
        src = DATA / f"textures/{asset}/{asset}_diff_1k.jpg"
        grey = src.with_name(f"{asset}_grey_1k.jpg")
        mark = grey.with_suffix(".eq")
        if src.exists() and (not grey.exists() or not mark.exists() or mark.read_text() != eq):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vf", f"hue=s=0,eq={eq}",
                            "-q:v", "2", str(grey)], check=True)
            mark.write_text(eq)
        if grey.exists():
            _texture_import(grey, normal=False)
    blender = Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"
    films = []
    for src, name in FILMS:
        film = DATA / "film" / name
        if src.exists():
            prepare_film(src, film, blender)
        if film.exists():
            films.append(name)
    print(f"campus: {len(campus['tools'])} tools in {len(campus['cells'])} cells; "
          f"{len(list((DATA / 'models').glob('*.glb')))} models; films {', '.join(films) or 'none'}")


if __name__ == "__main__":
    main()
