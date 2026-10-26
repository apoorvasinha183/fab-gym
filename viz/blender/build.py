"""Build the gigafab-style campus (our own design on the SMT2020 model; not a real fab) in
Blender from viz/prep.py's scene file, animate the lots, and render a film.

    Blender -b -P viz/blender/build.py -- SCENE.json OUT_DIR [--frames N] [--still F]

Writes OUT_DIR/campus.blend and OUT_DIR/frames/f0001.jpg ... (or a still PNG with --still).
Tools keep their area colours here; their states are shown in the Godot view.
"""

import json
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :]
SCENE, OUT = Path(argv[0]), Path(argv[1])
OUT.mkdir(parents=True, exist_ok=True)
FRAMES = int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 1440
STILL = int(argv[argv.index("--still") + 1]) if "--still" in argv else None
FPS = 24
S = json.loads(SCENE.read_text())
T0, T1 = S["from"], S["to"]


def frame_of(t):
    return 1 + (t - T0) / (T1 - T0) * (FRAMES - 1)


def hexcol(h, a=1.0):
    h = h.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x**2.2 for x in c] + [a]


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, FRAMES
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
try:
    scene.eevee.taa_render_samples = 8
    scene.eevee.use_shadows = True
except AttributeError:
    pass
scene.view_settings.view_transform = "AgX"
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = hexcol("0b1220")
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6

MATS = {}


def mat(name, colour, emit=0.0, alpha=1.0, rough=0.6):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = hexcol(colour)
    b.inputs["Roughness"].default_value = rough
    if emit > 0:
        b.inputs["Emission Color"].default_value = hexcol(colour)
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "BLENDED"
        except AttributeError:
            m.blend_method = "BLEND"
    MATS[name] = m
    return m


def boxes(name, rects, material):
    """One mesh holding many boxes: rects of (x0, y0, z0, x1, y1, z1)."""
    verts, faces = [], []
    for x0, y0, z0, x1, y1, z1 in rects:
        k = len(verts)
        verts += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces += [(k, k + 3, k + 2, k + 1), (k + 4, k + 5, k + 6, k + 7), (k, k + 1, k + 5, k + 4), (k + 1, k + 2, k + 6, k + 5), (k + 2, k + 3, k + 7, k + 6), (k + 3, k, k + 4, k + 7)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(material)
    scene.collection.objects.link(ob)
    return ob


LABELS = []


def label(text, x, y, z, size, colour):
    cu = bpy.data.curves.new(text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new("label " + text, cu)
    ob.location = (x, y, z)
    LABELS.append(ob)
    ob.data.materials.append(mat("label " + colour, colour, emit=2.0))
    scene.collection.objects.link(ob)
    return ob


# ground and site
boxes("ground", [(-1500, -1500, -0.6, 2500, 1500, -0.2)], mat("ground", "0f1622", rough=0.9))
boxes("site", [(-60, -280, -0.2, 920, 260, -0.05)], mat("site", "161f2e", rough=0.9))

# buildings
for b in S["buildings"]:
    k = b["kind"]
    if k == "fab":
        boxes(b["name"] + " floor", [(b["x0"], b["y0"], -0.05, b["x1"], b["y1"], 0.0)], mat("floor", "1b2433"))
        t = 0.6
        boxes(b["name"] + " wall", [
            (b["x0"], b["y0"], 0, b["x1"], b["y0"] + t, 4), (b["x0"], b["y1"] - t, 0, b["x1"], b["y1"], 4),
            (b["x0"], b["y0"], 0, b["x0"] + t, b["y1"], 4), (b["x1"] - t, b["y0"], 0, b["x1"], b["y1"], 4)], mat("wall", "3a4a63"))
        boxes(b["name"] + " glass", [(b["x0"], b["y0"], 0, b["x1"], b["y1"], b["h"])], mat("glass", "6c8db8", alpha=0.05))
    elif k == "pad":
        boxes(b["name"], [(b["x0"], b["y0"], -0.05, b["x1"], b["y1"], b["h"])], mat("pad", "2a3344"))
    elif k == "gas":
        boxes(b["name"] + " slab", [(b["x0"], b["y0"], -0.05, b["x1"], b["y1"], 0.2)], mat("gasslab", "232d3d"))
        for i in range(7):
            cx = b["x0"] + (i + 0.5) * (b["x1"] - b["x0"]) / 7
            bpy.ops.mesh.primitive_cylinder_add(radius=5, depth=b["h"], location=(cx, (b["y0"] + b["y1"]) / 2, b["h"] / 2))
            bpy.context.object.data.materials.append(mat("tank", "c9d3e0", rough=0.3))
    else:
        boxes(b["name"], [(b["x0"], b["y0"], 0, b["x1"], b["y1"], b["h"])], mat("support", "222c3c"))
    lz = max(b["h"], 10) + 14
    ly = (b["y0"] + b["y1"]) / 2 if k != "fab" else b["y1"] + 14
    label(b["label"], (b["x0"] + b["x1"]) / 2, ly, lz, 9 if k == "fab" else 7, "e8eef7")
for br in S["bridges"]:
    boxes("bridge", [(br["x0"], br["y"] - 3, br["z"] - 2.5, br["x1"], br["y"] + 3, br["z"] + 2.5)], mat("bridge", "7fb4ff", emit=0.3, alpha=0.35))
    label("OHT bridge", (br["x0"] + br["x1"]) / 2, 0, br["z"] + 10, 6, "9fd0ff")

# bays, aisles, spine
by_area = {}
aisles = []
for b in S["bays"]:
    by_area.setdefault(b["area"], []).append((b["x0"] + 0.3, b["y0"], 0, b["x1"] - 0.3, b["y1"], 0.03))
    cx = (b["x0"] + b["x1"]) / 2
    aisles.append((cx - 1.75, b["y0"], 0.03, cx + 1.75, b["y1"], 0.05))
for a, rects in by_area.items():
    c = S["areas"][a]["colour"]
    r, g, bl = (int(c[i : i + 2], 16) for i in (1, 3, 5))
    dark = "%02x%02x%02x" % (int(r * 0.28), int(g * 0.28), int(bl * 0.28))
    boxes("bays " + a, rects, mat("bay " + a, dark))
boxes("aisles", aisles, mat("aisle", "2b384d"))
spine = S["spine"]
for b in S["buildings"]:
    if b["kind"] == "fab":
        boxes("spine " + b["name"], [(b["x0"] + 4, -spine / 2, 0, b["x1"] - 4, spine / 2, 0.06)], mat("spine", "2f3d55"))

# tools, one mesh per area
tool_rects = {}
for t in S["tools"]:
    a = S["groups"][t["g"]]["area"]
    dx = (t["x1"] - t["x0"]) * 0.06
    dy = (t["y1"] - t["y0"]) * 0.09
    tool_rects.setdefault(a, []).append((t["x0"] + dx, t["y0"] + dy, 0, t["x1"] - dx, t["y1"] - dy, t["h"]))
for a, rects in tool_rects.items():
    boxes("tools " + a, rects, mat("tool " + a, S["areas"][a]["colour"].lstrip("#"), emit=0.25, rough=0.45))

# area names
for k, lb in enumerate(S["labels"]):
    back = lb["y"] + (22 if lb["y"] > 0 else -22)
    label(lb["text"], lb["x"], back, 10 + 9 * (k % 3), 4.5, S["areas"][lb["area"]]["colour"].lstrip("#"))

# hoist rails
rails = []
for r in S["rails"]:
    (ax, ay, az), (bx, by, bz) = r
    rails.append((min(ax, bx) - 0.15, min(ay, by) - 0.15, az + 0.4, max(ax, bx) + 0.15, max(ay, by) + 0.15, az + 0.7))
boxes("rails", rails, mat("rail", "49d3ff", emit=3.0))

def curves(ob):
    act = ob.animation_data.action
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    from bpy_extras.anim_utils import action_ensure_channelbag_for_slot

    return list(action_ensure_channelbag_for_slot(act, ob.animation_data.action_slot).fcurves)


# lots: one small box each, moved by keyframes, shown only while in the window
f = S["foup"]
lot_mesh = bpy.data.meshes.new("lot")
h = f / 2
lot_mesh.from_pydata(
    [(-h, -h, -h * 0.9), (h, -h, -h * 0.9), (h, h, -h * 0.9), (-h, h, -h * 0.9), (-h, -h, h * 0.9), (h, -h, h * 0.9), (h, h, h * 0.9), (-h, h, h * 0.9)],
    [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
hot_mesh = lot_mesh.copy()
lot_mesh.materials.append(mat("lot", "e8eef7", emit=0.6, rough=0.3))
hot_mesh.materials.append(mat("hot lot", "ff5a36", emit=2.0, rough=0.3))
lots_col = bpy.data.collections.new("lots")
scene.collection.children.link(lots_col)
for L in S["lots"]:
    keys = [k for k in L["k"]]
    ob = bpy.data.objects.new("lot " + L["id"], hot_mesh if L["hot"] else lot_mesh)
    lots_col.objects.link(ob)
    frames = [frame_of(k[0]) for k in keys]
    # make the action through the public call, then fill its curves in bulk
    ob.location = keys[0][1:4]
    ob.keyframe_insert("location", frame=frames[0])
    ob.keyframe_insert("scale", frame=frames[0])
    fcs = curves(ob)
    vis = [(frames[0] - 0.01, 0.0), (frames[0], 1.0), (frames[-1], 1.0), (frames[-1] + 0.01, 0.0)]
    for fc in fcs:
        fc.keyframe_points.clear()
        if fc.data_path == "location":
            pts = [(fr, k[1 + fc.array_index]) for fr, k in zip(frames, keys)]
            kind = 1  # linear
        else:
            pts = vis
            kind = 0  # constant
        fc.keyframe_points.add(len(pts))
        fc.keyframe_points.foreach_set("co", [x for p in pts for x in p])
        fc.keyframe_points.foreach_set("interpolation", [kind] * len(pts))
        fc.update()

# light
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.data.color = hexcol("fff1dc")[:3]
sun.rotation_euler = (math.radians(52), 0, math.radians(35))
scene.collection.objects.link(sun)

# the camera: the Godot tour, (seconds, pivot east, yaw, pitch, distance), eased
TOUR = [(0, 376, 2.45, 0.78, 760), (8, 300, 2.75, 0.62, 560), (18, 120, 3.05, 0.55, 250), (28, 250, 2.85, 0.34, 190),
        (36, 345, 2.2, 0.36, 170), (44, 450, 3.5, 0.45, 210), (52, 400, 3.9, 0.85, 640), (60, 376, 4.05, 1.05, 700)]
cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
cam.data.lens = 32
cam.data.clip_end = 6000
scene.collection.objects.link(cam)
scene.camera = cam
target = bpy.data.objects.new("look at", None)
scene.collection.objects.link(target)
tc = cam.constraints.new("TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"
for ob in LABELS:
    # face the camera
    c = ob.constraints.new("COPY_ROTATION")
    c.target = cam
total = TOUR[-1][0]
for fr in range(1, FRAMES + 1, 6):
    s = (fr - 1) / (FRAMES - 1) * total
    for a, b in zip(TOUR, TOUR[1:]):
        if a[0] <= s <= b[0]:
            u = (s - a[0]) / (b[0] - a[0])
            u = u * u * (3 - 2 * u)
            px, yaw, pitch, dist = (a[i] + (b[i] - a[i]) * u for i in (1, 2, 3, 4))
            break
    # Godot direction (x, up, south) to Blender (x, north, up)
    dx, dup, dsouth = math.cos(pitch) * math.sin(yaw), math.sin(pitch), math.cos(pitch) * math.cos(yaw)
    cam.location = (px + dx * dist, -dsouth * dist, dup * dist)
    cam.keyframe_insert("location", frame=fr)
    target.location = (px, 0, 0)
    target.keyframe_insert("location", frame=fr)
    # shrink a label away while the camera is close to it, so no text fills the frame
    for ob in LABELS:
        near = ob.data.size * 12
        d = (ob.location - cam.location).length
        u = min(max((d - near) / (near * 0.5), 0.0), 1.0)
        ob.scale = (u, u, u)
        ob.keyframe_insert("scale", frame=fr)

bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "campus.blend"), compress=True)

if STILL is not None:
    scene.frame_set(STILL)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(OUT / f"still-{STILL}.png")
    bpy.ops.render.render(write_still=True)
else:
    # frames as JPEG; encode them into a film elsewhere (ffmpeg), so this runs on any Blender
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 90
    scene.render.filepath = str(OUT / "frames" / "f")
    bpy.ops.render.render(animation=True)
print("done", OUT)
