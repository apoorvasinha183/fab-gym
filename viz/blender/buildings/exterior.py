"""The campus outside the buildings, for the 3D fab's drone opening (docs/FAB-3D.md, F10): the permit set's rooftop
make-up air units on their curbs, its chillers and transformers in the utility yard; and ours, assumed: the yard's
concrete pad, the roads with their centre lines, trees and the roofs' exhaust stacks. Placed from `exterior` in
viz/fab3d/data/campus.json, in plan coordinates (metres, x east, y north, z up). The looks are ours. One mesh. From
the SMT2020 testbed; not a real fab.

    Blender -b --factory-startup -P viz/blender/buildings/exterior.py -- --out data/fab3d/models/exterior.glb
"""

import json
import math
import os
import sys

import bpy

A = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = A[A.index("--out") + 1] if "--out" in A else "data/fab3d/models/exterior.glb"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
X = json.load(open(os.path.join(ROOT, "viz/fab3d/data/campus.json")))["exterior"]
P, S = X["permit"], X["assumed"]

COLOURS = {   # name: (base, metallic, roughness)
    "unit": ((0.82, 0.84, 0.85), 0.3, 0.45),
    "louvre": ((0.32, 0.35, 0.38), 0.4, 0.5),
    "curb": ((0.25, 0.26, 0.28), 0.0, 0.8),
    "fan": ((0.12, 0.13, 0.14), 0.3, 0.5),
    "chiller": ((0.72, 0.78, 0.76), 0.3, 0.45),
    "coil": ((0.42, 0.46, 0.45), 0.5, 0.4),
    "transformer": ((0.42, 0.5, 0.45), 0.2, 0.55),
    "bushing": ((0.75, 0.55, 0.35), 0.0, 0.4),
    "pad": ((0.66, 0.66, 0.63), 0.0, 0.85),
    "asphalt": ((0.17, 0.18, 0.19), 0.0, 0.9),
    "paint": ((0.93, 0.93, 0.88), 0.0, 0.6),
    "stack": ((0.7, 0.72, 0.75), 0.8, 0.3),
    "stack_band": ((0.85, 0.2, 0.15), 0.0, 0.5),
    "trunk": ((0.3, 0.22, 0.15), 0.0, 0.9),
    "leaves": ((0.22, 0.46, 0.24), 0.0, 0.85),
    "leaves2": ((0.3, 0.52, 0.22), 0.0, 0.85),
    "bridge": ((0.86, 0.87, 0.88), 0.2, 0.45),
    "bridge_trim": ((0.12, 0.42, 0.85), 0.0, 0.4),
    "bridge_glass": ((0.35, 0.55, 0.7), 0.6, 0.08),
    "deck": ((0.78, 0.8, 0.82), 0.0, 0.5),
    "rail": ((0.86, 0.86, 0.84), 0.1, 0.35),
}


def material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    base, metal, rough = COLOURS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*base, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    return m


PARTS = []


def box(x0, y0, z0, x1, y1, z1, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    ob = bpy.context.active_object
    ob.scale = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    ob.data.materials.append(material(mat))
    PARTS.append(ob)


def cyl(x, y, z0, r, h, mat, verts=12):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(x, y, z0 + h / 2))
    ob = bpy.context.active_object
    ob.data.materials.append(material(mat))
    PARTS.append(ob)


def cone(x, y, z0, r, h, mat):
    bpy.ops.mesh.primitive_cone_add(vertices=9, radius1=r, depth=h, location=(x, y, z0 + h / 2))
    ob = bpy.context.active_object
    ob.data.materials.append(material(mat))
    PARTS.append(ob)


bpy.ops.wm.read_factory_settings(use_empty=True)

# ------------------------------------------------------------------ the permit set's rooftop air units, on their curbs
for c in P["curbs"]:
    box(*c["box"], "curb")
for u in P["air_units"]:
    x0, y0, z0, x1, y1, z1 = u["box"]
    z0 = max(z0, 18.85)
    box(x0 + 0.05, y0 + 0.05, z0, x1 - 0.05, y1 - 0.05, z1, "unit")
    for k in range(5):                                   # louvres down the long sides
        xx = x0 + 0.5 + k * (x1 - x0 - 1.0) / 4
        for y in (y0 + 0.02, y1 - 0.06):
            box(xx - 0.3, y, z0 + 0.4, xx + 0.3, y + 0.04, z1 - 0.5, "louvre")
    for k in range(2):                                   # two fans on top
        cyl(x0 + (x1 - x0) * (k + 0.5) / 2, (y0 + y1) / 2, z1, 0.9, 0.25, "fan", verts=16)

# ------------------------------------------------------------------ the utility yard (permit set), on our pad
items = P["chillers"] + P["transformers"]
xs = [i["box"][0] for i in items] + [i["box"][3] for i in items]
ys = [i["box"][1] for i in items] + [i["box"][4] for i in items]
box(min(xs) - 4, min(ys) - 4, -0.02, max(xs) + 4, max(ys) + 4, 0.12, "pad")
for c in P["chillers"]:
    x0, y0, z0, x1, y1, z1 = c["box"]
    box(x0, y0, z0 + 0.12, x1, y1, z1, "chiller")
    for k in range(int((x1 - x0) / 2.5)):                # condenser coils and fans along the top
        xx = x0 + 1.25 + k * 2.5
        cyl(xx, (y0 + y1) / 2, z1, 0.95, 0.3, "fan", verts=16)
        for y in (y0 - 0.01, y1 - 0.04):
            box(xx - 1.0, y, z0 + 1.0, xx + 1.0, y + 0.05, z1 - 0.4, "coil")
for t in P["transformers"]:
    x0, y0, z0, x1, y1, z1 = t["box"]
    box(x0 + 0.3, y0 + 0.3, z0 + 0.12, x1 - 0.3, y1 - 0.3, z1, "transformer")
    for k in range(6):                                   # cooling fins on the long sides
        xx = x0 + 0.5 + k * (x1 - x0 - 1.0) / 5
        for y in (y0 + 0.05, y1 - 0.3):
            box(xx - 0.05, y, z0 + 0.4, xx + 0.05, y + 0.25, z1 - 0.4, "transformer")
    for k in range(3):                                   # bushings on top
        cyl(x0 + (x1 - x0) * (k + 1) / 4, (y0 + y1) / 2, z1, 0.15, 0.7, "bushing", verts=10)

# ------------------------------------------------------------------ ours: roads, stacks, trees
for r in S["roads"]:
    x0, y0, x1, y1 = r
    box(x0, y0, -0.01, x1, y1, 0.03, "asphalt")
    along_x = (x1 - x0) > (y1 - y0)
    n = int(((x1 - x0) if along_x else (y1 - y0)) / 6)
    for k in range(n):                                   # dashed centre line
        if along_x:
            x = x0 + 1.5 + k * 6
            box(x, (y0 + y1) / 2 - 0.08, 0.03, x + 3, (y0 + y1) / 2 + 0.08, 0.035, "paint")
        else:
            y = y0 + 1.5 + k * 6
            box((x0 + x1) / 2 - 0.08, y, 0.03, (x0 + x1) / 2 + 0.08, y + 3, 0.035, "paint")
for x, y, r, h in S["stacks"]:
    cyl(x, y, 18.5, r, h, "stack", verts=16)
    cyl(x, y, 18.5 + h - 1.4, r + 0.04, 0.5, "stack_band", verts=16)
    cyl(x, y, 18.5, r + 0.35, 0.4, "curb", verts=16)
for k, (x, y, r, h) in enumerate(S["trees"]):
    cyl(x, y, 0.0, 0.2, h * 0.35, "trunk", verts=8)
    cone(x, y, h * 0.25, r, h * 0.55, "leaves" if k % 2 else "leaves2")
    cone(x, y, h * 0.55, r * 0.7, h * 0.45, "leaves2" if k % 2 else "leaves")

# ------------------------------------------------------------------ the bridge between the phases (outline: permit set)
B = X["bridge"]
x0, y0, _, x1, y1, deck_top = B["deck"]
roof = B["roof_z"]
box(x0, y0, B["deck"][2] - 0.6, x1, y1, deck_top, "bridge")                 # the deck's underside and its floor
box(x0, y0 + 0.4, deck_top, x1, y1 - 0.4, deck_top + 0.01, "deck")
box(x0, y0 - 0.2, roof, x1, y1 + 0.2, roof + 0.5, "bridge")                 # roof
box(x0, y0 - 0.25, roof - 0.15, x1, y1 + 0.25, roof, "bridge_trim")
for y_a, y_b in ((y0 - 0.2, y0), (y1, y1 + 0.2)):                           # sides: a solid sill, a window band, a head
    box(x0, y_a, deck_top, x1, y_b, deck_top + 1.0, "bridge")
    box(x0, y_a + 0.05, deck_top + 1.0, x1, y_b - 0.05, roof - 0.6, "bridge_glass")
    box(x0, y_a, roof - 0.6, x1, y_b, roof, "bridge")
    n = int((x1 - x0) / 4.0)
    for k in range(n + 1):                                                  # mullions every 4 m
        xx = x0 + k * (x1 - x0) / n
        box(xx - 0.08, y_a - 0.02, deck_top + 1.0, xx + 0.08, y_b + 0.02, roof - 0.6, "bridge")
for cx, cy in B["columns"]:                                                 # columns down to the ground
    box(cx - 0.4, cy - 0.4, 0.0, cx + 0.4, cy + 0.4, B["deck"][2] - 0.6, "bridge")
box(x0, -0.12, 11.62, x1, 0.12, 11.8, "rail")                               # the overhead rail running through
for k in range(int((x1 - x0) / 3.0) + 1):
    xx = x0 + k * 3.0
    box(xx - 0.02, -0.02, 11.8, xx + 0.02, 0.02, roof, "rail")

bpy.ops.object.select_all(action="DESELECT")
for o in PARTS:
    o.select_set(True)
bpy.context.view_layer.objects.active = PARTS[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
ob = bpy.context.active_object
ob.name = ob.data.name = "exterior"
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_apply=True)
print(f"exterior: {len(ob.data.polygons)} faces -> {OUT}")
