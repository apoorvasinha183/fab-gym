"""Choosing a look (docs/FILM-PLAYBOOK.md, step 3): one shot painted in each candidate look of film/drawn/looks.json,
its first background and Grain's first drawing from the same model sheet, set side by side with the shot as it is now,
so the looks are judged on the same moment. A look with no style picture yet is painted from its words alone, and the
first background and drawing it gets become its style pictures.

    python3 -m viz.drawn.artdir SHOT LOOK [LOOK ...]     data/drawn/artdir/<shot>/compare.jpg
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import pilot, poses, produce, scene

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/drawn/artdir"
W, H = 1920, 1080


def compare(shot_id, looks):
    n = scene.scene_of(shot_id)
    sc = scene.load(n)
    shot = next(s for s in sc["shots"] if s["id"] == shot_id)
    plate_name = next(x for lv in shot["levels"] if lv.get("plate") for x in (lv.get("cels") and [lv["cels"][0][0]] or lv["cycle"]))
    grain = next(lv for lv in shot["levels"] if not lv.get("plate"))
    key = next(x[0] for x in grain["cels"] if x[0] != "none")
    dd = sc["drawings"][key]
    while dd.get("kind") in ("next", "between"):           # a drawing made from others: use the key it starts from
        key = dd["after"] if dd.get("kind") == "next" else dd["between"][0]
        dd = sc["drawings"][key]
    out = OUT / shot_id
    out.mkdir(parents=True, exist_ok=True)
    c = pilot.client()
    data = json.loads(scene.LOOKS.read_text())["looks"]

    def paint(look):
        scene.use(look)
        L = data[look]
        refs = [(ROOT / L["style_ref"]).read_bytes()] if (ROOT / L.get("style_ref", "-")).is_file() else []
        p = out / f"{look}-plate.png"
        if not p.exists():
            img = produce._try(c, [scene.plate_text(n, sc["plates"][plate_name])], refs)
            if img:
                p.write_bytes(img)
        g = out / f"{look}-grain.png"
        if not g.exists():
            img = produce._try(c, [scene.char(n) + dd["pose"]], [(ROOT / "data/drawn/sheets" / f"{dd['sheet']}.png").read_bytes()])
            if img:
                g.write_bytes(img)
    for look in looks:                                     # one look at a time: use() sets the look for the module
        paint(look)
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 44)
    tiles = []
    for look, plate, cel in [("now", scene.ROOT / "data/drawn/scenes" / n / f"{plate_name}.png",
                              scene.ROOT / "data/drawn/scenes" / n / f"{key}.png")] + \
                            [(look, out / f"{look}-plate.png", out / f"{look}-grain.png") for look in looks]:
        if not (plate.exists() and cel.exists()):
            continue
        fr = Image.open(plate).convert("RGBA").resize((W, H), Image.LANCZOS)
        cut = poses.fit(pilot.key(Image.open(cel)), float(grain.get("height", 330)))
        cx, cy = poses.measure(cut)["contact"]
        at = grain.get("at") or grain["path"][-1][1:]
        fr.alpha_composite(cut, (int(at[0] - cx), int(at[1] - cy)))
        t = fr.convert("RGB").resize((960, 540))
        d = ImageDraw.Draw(t)
        name = "Now" if look == "now" else data[look]["name"]
        d.rounded_rectangle([16, 16, 32 + d.textlength(name, font=font), 76], 10, fill=(0, 0, 0))
        d.text((24, 20), name, font=font, fill=(255, 220, 120))
        tiles.append(t)
    board = Image.new("RGB", (1920, 540 * ((len(tiles) + 1) // 2)))
    for i, t in enumerate(tiles):
        board.paste(t, ((i % 2) * 960, (i // 2) * 540))
    board.save(out / "compare.jpg", quality=86)
    print(out / "compare.jpg", f"spent ${c.spent():.2f}")
    return out / "compare.jpg"


if __name__ == "__main__":
    compare(sys.argv[1], sys.argv[2:])
