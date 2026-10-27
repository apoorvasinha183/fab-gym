"""Build the props of the visitor's way in, once each, as assets: props.blend.

    Blender -b -P viz/blender/props.py -- PLAN OUT.blend [--stills DIR]

PLAN is data/layout-real/visitor-film.json; each kind of furniture in its rooms (turnstile, reader,
glass barrier, desk, lift panel, planter, sofa, bench, lockers, shoe rack, gown rack, mirror, glove
dispenser) is modelled once at the plan's size, its front toward the room, and each kind of door
once per size (glass sliding, lift, single, interlock). visitor.py places copies where the plan puts
them. All drawn only, at assumed sizes, in our own simple shapes and plain materials chosen to look
like what such things are made of: brushed steel, glass, laminate, fabric.

Collection "props": "prop <kind>" with its origin at its low corner and its size the plan's
(custom properties "kind", "size", "front"), "prop turnstile wing", and for doors
"prop door <kind> <w>x<h>" (one leaf, origin at the hinge or the closed edge, along +x).
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bkit import Batch, collection, principled  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1 :]
PLAN, OUT = Path(argv[0]), Path(argv[1])
STILLS = Path(argv[argv.index("--stills") + 1]) if "--stills" in argv else None
P = json.loads(PLAN.read_text())

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
col = collection("props")

STEEL = principled("brushed steel", "#b8bdc3", metal=0.9, rough=0.32)
STEEL_DARK = principled("dark steel", "#5f656c", metal=0.8, rough=0.4)
GLASS = principled("clear glass", "#dbe9ee", rough=0.03, alpha=0.18, trans=0.9)
BLACK = principled("black plastic", "#16191c", rough=0.45)
LED_G = principled("led green", "#3ad16f", emit=4.0)
LED_B = principled("led blue", "#4aa8ff", emit=3.0)
OAK = principled("oak veneer", "#a3825e", rough=0.55)
QUARTZ = principled("white quartz", "#eeece8", rough=0.18, coat=0.4)
PLINTH = principled("plinth", "#2a2c2f", rough=0.6)
FABRIC = principled("grey fabric", "#666c72", rough=0.95, sheen=0.6)
POT = principled("planter grey", "#3e4247", rough=0.55)
SOIL = principled("bark mulch", "#3b2c22", rough=1.0)
LEAF = [principled("leaf " + c, c, rough=0.7, sheen=0.2) for c in ("#3f6b35", "#4c7d3c", "#2f5a2c")]
LOCKER = principled("locker grey", "#c8cdd2", metal=0.5, rough=0.4)
SEAM = principled("seam", "#7d848c", metal=0.5, rough=0.5)
GOWN = principled("gown bag", "#eef2f6", rough=0.8, sheen=0.4)
MIRROR = principled("mirror", "#f4f4f4", metal=1.0, rough=0.015)
WHITE_BOX = principled("white plastic", "#f1f2f3", rough=0.4)
NITRILE = principled("glove box window", "#6b7fd6", rough=0.4)
LAMINATE = principled("white laminate", "#e9eaea", rough=0.35)


def front_of(r, f):
    """The side of the piece that faces into the room: a long side, away from the nearer wall."""
    gaps = {"w": f["x0"] - r["x0"], "e": r["x1"] - f["x1"], "s": f["y0"] - r["y0"], "n": r["y1"] - f["y1"]}
    long_x = (f["x1"] - f["x0"]) >= (f["y1"] - f["y0"])
    near = min(("s", "n") if long_x else ("w", "e"), key=gaps.get)
    return {"w": "e", "e": "w", "s": "n", "n": "s"}[near]


FRONT = {}  # any piece whose front the rule above gets wrong


def kinds():
    out = {}
    for r in P["rooms"]:
        for f in r.get("furniture", []):
            if f["kind"] == "mark" or f["kind"] in out:
                continue
            size = (f["x1"] - f["x0"], f["y1"] - f["y0"], f["z1"] - f["z0"])
            out[f["kind"]] = (size, FRONT.get(f["kind"], front_of(r, f)))
    return out


def faced(b, w, d, front, depth_box):
    """Boxes given as (u0, v0, z0, u1, v1, z1) with v measured back from the front: put them in the
    piece's own frame (0..w along x, 0..d along y) for the front it has."""
    u0, v0, z0, u1, v1, z1 = depth_box
    if front == "s":
        return (u0, v0, z0, u1, v1, z1)
    if front == "n":
        return (u0, d - v1, z0, u1, d - v0, z1)
    if front == "w":
        return (v0, u0, z0, v1, u1, z1)
    return (w - v1, u0, z0, w - v0, u1, z1)  # e


def span(w, d, front):
    """Length across the front and depth back from it."""
    return (w, d) if front in ("n", "s") else (d, w)


def build(kind, size, front):
    w, d, h = size
    L, D = span(w, d, front)
    b = Batch()

    def box(m, *bx):
        b.box(m, *faced(b, w, d, front, bx))

    if kind == "turnstile":
        b.box(STEEL, 0, 0, 0, w, d, h - 0.05)
        b.box(BLACK, 0, 0, h - 0.05, w, d, h)
        for x in (-0.004, w - 0.002):
            b.box(LED_G, x, 0.15, h - 0.16, x + 0.006, d - 0.15, h - 0.13)
    elif kind == "reader":
        b.box(BLACK, 0, 0, 0, w, d, h * 0.7)
        b.cyl(LED_B, (w * 0.2, d * 0.3, h * 0.7), (w * 0.8, d * 0.7, h * 0.76), "z", 20)
        b.box(BLACK, w * 0.3, d * 0.35, h * 0.76, w * 0.7, d * 0.65, h)
    elif kind == "glass barrier":
        box(GLASS, 0, D * 0.4, 0.05, L, D * 0.6, h - 0.06)
        n = max(1, int(L // 1.2))
        for i in range(n + 1):
            u = min(L - 0.04, i * L / n)
            box(STEEL, max(0, u - 0.02), D * 0.3, 0, u + 0.02, D * 0.7, h - 0.04)
        box(STEEL, 0, D * 0.3, h - 0.06, L, D * 0.7, h)
    elif kind == "desk":
        box(PLINTH, 0.04, 0.06, 0, L - 0.04, D - 0.04, 0.1)
        box(OAK, 0, 0, 0.1, L, 0.04, h - 0.04)  # the front the visitor sees
        box(OAK, 0, 0.04, 0.1, 0.04, D, 0.74)
        box(OAK, L - 0.04, 0.04, 0.1, L, D, 0.74)
        box(QUARTZ, -0.03, -0.04, h - 0.04, L + 0.03, 0.32, h)  # the high ledge
        box(QUARTZ, 0, 0.32, 0.72, L, D, 0.76)  # the work top behind it
        box(BLACK, L * 0.55, D * 0.55, 0.76, L * 0.55 + 0.5, D * 0.55 + 0.03, 1.08)  # a monitor
    elif kind == "panel":
        box(STEEL, 0, 0, 0, L, D, h)
        for z, m in ((h * 0.62, LED_B), (h * 0.36, STEEL_DARK)):
            box(m, L * 0.35, -0.006, z - 0.025, L * 0.65, 0.0, z + 0.025)
    elif kind == "planter":
        b.box(POT, 0, 0, 0, w, d, 0.55)
        b.box(SOIL, 0.05, 0.05, 0.55, w - 0.05, d - 0.05, 0.56)
        import random

        rnd = random.Random(3)
        for i in range(26):
            cx, cy = rnd.uniform(0.2, w - 0.2), rnd.uniform(0.2, d - 0.2)
            r = rnd.uniform(0.12, 0.2)
            b.cyl(LEAF[i % 3], (cx - r, cy - r, 0.55), (cx + r, cy + r, min(h, 0.6 + rnd.uniform(0.15, 0.32))), "z", 7)
    elif kind == "sofa":
        box(PLINTH, 0.05, 0.05, 0, L - 0.05, D - 0.05, 0.1)
        box(FABRIC, 0, 0, 0.1, L, D, 0.42)  # seat base
        box(FABRIC, 0.02, 0.02, 0.42, L - 0.02, D - 0.2, 0.47)  # cushions
        box(FABRIC, 0, D - 0.2, 0.42, L, D, h)  # back
        box(FABRIC, 0, 0, 0.42, 0.16, D - 0.2, 0.62)
        box(FABRIC, L - 0.16, 0, 0.42, L, D - 0.2, 0.62)
    elif kind == "bench":
        b.box(STEEL, 0, 0, h - 0.04, w, d, h)
        n = max(2, int(w // 1.3) + 1)
        for i in range(n):
            x = 0.1 + i * (w - 0.24) / (n - 1)
            b.box(STEEL, x, d * 0.3, 0, x + 0.04, d * 0.7, h - 0.04)
    elif kind == "lockers":
        box(LOCKER, 0, 0.01, 0, L, D, h)
        n = max(1, int(L // 0.4))
        for i in range(n + 1):
            u = i * L / n
            box(SEAM, max(0, u - 0.004), 0, 0.02, min(L, u + 0.004), 0.012, h - 0.02)
        for i in range(n):
            u = (i + 0.85) * L / n
            box(STEEL_DARK, u - 0.012, -0.012, h * 0.55, u, 0.01, h * 0.62)
            box(SEAM, (i + 0.2) * L / n, 0.0, h * 0.82, (i + 0.6) * L / n, 0.012, h * 0.84)  # vents
    elif kind == "rack":
        for u in (0.0, L - 0.03):
            box(STEEL, u, 0, 0, u + 0.03, D, h)
        for k in range(4):
            z = 0.15 + k * (h - 0.25) / 3
            box(STEEL, 0, 0.0, z, L, D, z + 0.02)
            box(BLACK, 0.1, 0.05, z + 0.02, L * 0.45, D - 0.08, z + 0.1)  # a pair of shoes
    elif kind == "gown rack":
        for u in (0.0, L - 0.04):
            box(STEEL, u, D * 0.45, 0, u + 0.04, D * 0.55, h)
        box(STEEL, 0, D * 0.45, h - 0.04, L, D * 0.55, h)
        n = 7
        for i in range(n):
            u = 0.12 + i * (L - 0.3) / (n - 1)
            box(GOWN, u, D * 0.1, h * 0.28, u + 0.07, D * 0.9, h - 0.08)
    elif kind == "mirror":
        box(STEEL, 0, 0, 0, L, D, h)
        box(MIRROR, 0.02, -0.002, 0.02, L - 0.02, 0.0, h - 0.02)
    elif kind == "dispenser":
        box(WHITE_BOX, 0, 0, 0, L, D, h)
        for k in range(3):
            z = 0.04 + k * (h - 0.08) / 3
            box(NITRILE, 0.05, -0.004, z + 0.02, L - 0.05, 0.0, z + (h - 0.08) / 3 - 0.02)
    else:
        raise SystemExit(f"no model for {kind}")
    ob = b.make("prop " + kind, col)
    ob["kind"], ob["size"], ob["front"] = kind, list(size), front
    return ob


PROPS = {k: build(k, *v) for k, v in kinds().items()}

# the turnstile's glass wing: a panel that closes half a lane, retracting into its cabinet
wb = Batch()
wb.box(GLASS, 0, -0.01, 0.2, 0.42, 0.01, 0.95)
wb.box(STEEL, 0, -0.012, 0.2, 0.03, 0.012, 0.95)
wing = wb.make("prop turnstile wing", col)
wing["kind"] = "turnstile wing"


def door(kind, w, h):
    """One leaf, closed, along +x from its origin; a sliding pair uses two (one mirrored)."""
    b = Batch()
    if kind == "glass sliding":
        lw = w / 2
        b.box(GLASS, 0, -0.012, 0.02, lw, 0.012, h - 0.02)
        b.box(STEEL, 0, -0.02, h - 0.1, lw, 0.02, h)
        b.box(STEEL, 0, -0.02, 0, lw, 0.02, 0.06)
        b.box(STEEL, lw - 0.03, -0.02, 0.9, lw, 0.02, 1.3)  # the meeting edge's pull
    elif kind == "lift":
        lw = w / 2
        b.box(STEEL, 0, -0.02, 0, lw, 0.02, h)
    elif kind == "single":
        b.box(LAMINATE, 0, -0.022, 0, w, 0.022, h)
        b.box(GLASS, w * 0.3, -0.024, h * 0.55, w * 0.7, 0.024, h * 0.85)
        b.box(STEEL, w - 0.14, -0.06, 1.0, w - 0.04, 0.06, 1.04)
    elif kind == "interlock":
        b.box(STEEL, 0, -0.025, 0, w, 0.025, h)
        b.box(GLASS, w * 0.25, -0.027, h * 0.5, w * 0.75, 0.027, h * 0.85)
        b.box(STEEL_DARK, w - 0.12, -0.07, 0.95, w - 0.05, 0.07, 1.0)
        b.box(LED_G, w * 0.45, -0.03, h - 0.12, w * 0.55, -0.025, h - 0.08)
    else:
        raise SystemExit(f"no door for {kind}")
    ob = b.make(f"prop door {kind} {w:g}x{h:g}", col)
    ob["kind"], ob["w"], ob["h"] = kind, w, h
    return ob


DOORS = {}
for r in P["rooms"]:
    for d in r.get("doors", []):
        key = (d["kind"], d["w"], d["h"])
        if key not in DOORS:
            DOORS[key] = door(*key)

for o in col.objects:
    o.data.name = o.name
bpy.ops.wm.save_as_mainfile(filepath=str(OUT), compress=True)
print("props", sorted(PROPS), "doors", sorted(DOORS))

if STILLS:
    STILLS.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    w = bpy.data.worlds.new("w")
    scene.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.62, 0.65, 1)
    x = 0.0
    for o in list(PROPS.values()) + [wing] + list(DOORS.values()):
        o.location = (x, 0, 0)
        x += max(o.dimensions.x, 0.4) + 0.6
    key = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
    key.data.energy = 3.0
    key.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(key)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 24
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (x / 2, -9.5, 3.2)
    cam.rotation_euler = (Vector((x / 2, 0, 0.8)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(STILLS / "props.png")
    bpy.ops.render.render(write_still=True)
