"""The way in, for the 3D fab's tour (docs/FAB-3D.md, F9): the parking lot, the visitors' pavilion, the passenger
lift, gowning room P1-GW1's fittings and its air shower. Placed from `entrance` in viz/fab3d/data/campus.json (written
by viz/fab3d/prep.py from the permit set's boxes), in plan coordinates (metres, x east, y north, z up), so it lands in
place. The lift, gowning room, doors, air shower, lockers, bench and garment rack are where the permit set puts them;
the lot, cars, pavilion, ground door, lift lobby walls and the looks of everything are ours, assumed. The lift car is
its own mesh, `lift_car`, which the scene moves; the cars are one mesh, `cars`. From the SMT2020 testbed; not a real
fab.

    Blender -b --factory-startup -P viz/blender/buildings/entrance.py -- --out data/fab3d/models/entrance.glb
"""

import json
import math
import os
import sys

import bpy

A = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = A[A.index("--out") + 1] if "--out" in A else "data/fab3d/models/entrance.glb"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
E = json.load(open(os.path.join(ROOT, "viz/fab3d/data/campus.json")))["entrance"]
P, S = E["permit"], E["assumed"]

COLOURS = {   # name: (base, metallic, roughness, emission, alpha)
    "asphalt": ((0.16, 0.17, 0.18), 0.0, 0.9, None, 1),
    "paint": ((0.92, 0.92, 0.88), 0.0, 0.6, None, 1),
    "kerb": ((0.62, 0.62, 0.6), 0.0, 0.8, None, 1),
    "paving": ((0.72, 0.71, 0.68), 0.0, 0.8, None, 1),
    "grass": ((0.25, 0.42, 0.2), 0.0, 0.95, None, 1),
    "trunk": ((0.3, 0.22, 0.15), 0.0, 0.9, None, 1),
    "leaves": ((0.2, 0.45, 0.22), 0.0, 0.85, None, 1),
    "pole": ((0.3, 0.32, 0.35), 0.6, 0.4, None, 1),
    "lamp": ((1.0, 0.95, 0.85), 0.0, 0.3, ((1.0, 0.92, 0.75), 3.0), 1),
    "frame": ((0.22, 0.24, 0.27), 0.5, 0.4, None, 1),
    "glass": ((0.6, 0.78, 0.9), 0.0, 0.05, None, 0.28),
    "panel": ((0.93, 0.94, 0.95), 0.0, 0.5, None, 1),
    "accent": ((0.12, 0.45, 0.85), 0.0, 0.4, None, 1),
    "floor": ((0.78, 0.8, 0.82), 0.0, 0.5, None, 1),
    "steel": ((0.78, 0.8, 0.82), 0.8, 0.3, None, 1),
    "locker": ((0.86, 0.88, 0.9), 0.4, 0.4, None, 1),
    "dark": ((0.1, 0.11, 0.12), 0.1, 0.5, None, 1),
    "suit": ((0.97, 0.97, 0.98), 0.0, 0.8, None, 1),
    "mat": ((0.35, 0.55, 0.8), 0.0, 0.9, None, 1),
    "tyre": ((0.06, 0.06, 0.06), 0.0, 0.9, None, 1),
    "car0": ((0.75, 0.1, 0.1), 0.5, 0.35, None, 1),
    "car1": ((0.9, 0.9, 0.92), 0.5, 0.35, None, 1),
    "car2": ((0.12, 0.14, 0.18), 0.5, 0.35, None, 1),
    "car3": ((0.2, 0.35, 0.65), 0.5, 0.35, None, 1),
    "car4": ((0.55, 0.57, 0.6), 0.6, 0.3, None, 1),
    "car5": ((0.85, 0.75, 0.55), 0.5, 0.35, None, 1),
    "car6": ((0.1, 0.55, 0.45), 0.5, 0.3, None, 1),
    "window": ((0.08, 0.1, 0.13), 0.2, 0.1, None, 1),
    "green": ((0.2, 1.0, 0.4), 0.0, 0.3, ((0.2, 1.0, 0.4), 4.0), 1),
}


def material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    base, metal, rough, emit, alpha = COLOURS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*base, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    if alpha < 1:
        p.inputs["Alpha"].default_value = alpha
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
        elif hasattr(m, "blend_method"):
            m.blend_method = "BLEND"
    if emit:
        for k in ("Emission Color", "Emission"):
            if k in p.inputs:
                p.inputs[k].default_value = (*emit[0], 1)
                break
        p.inputs["Emission Strength"].default_value = emit[1]
    return m


PARTS = {}


def box(x0, y0, z0, x1, y1, z1, mat, group="entrance"):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    ob = bpy.context.active_object
    ob.scale = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    ob.data.materials.append(material(mat))
    PARTS.setdefault(group, []).append(ob)
    return ob


def cyl(x, y, z0, r, h, mat, group="entrance", verts=12, axis="z"):
    rot = {"z": (0, 0, 0), "x": (0, math.pi / 2, 0), "y": (math.pi / 2, 0, 0)}[axis]
    loc = (x, y, z0 + h / 2) if axis == "z" else (x, y, z0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.data.materials.append(material(mat))
    PARTS.setdefault(group, []).append(ob)
    return ob


def cone(x, y, z0, r, h, mat, group="entrance"):
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=r, depth=h, location=(x, y, z0 + h / 2))
    ob = bpy.context.active_object
    ob.data.materials.append(material(mat))
    PARTS.setdefault(group, []).append(ob)


def join(group, name):
    obs = PARTS[group]
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = ob.data.name = name
    return ob


bpy.ops.wm.read_factory_settings(use_empty=True)

# ------------------------------------------------------------------ the parking lot and the walk in (assumed)
lx0, ly0, lx1, ly1 = S["lot"]
pav = S["pavilion"]
walk_y = (S["ground_door"][1] + S["ground_door"][4]) / 2
box(lx0, ly0, 0.0, lx1, ly1, 0.04, "asphalt")
for x0, y0, x1, y1 in ((lx0 - 0.3, ly0 - 0.3, lx1 + 0.3, ly0), (lx0 - 0.3, ly1, lx1 + 0.3, ly1 + 0.3),
                       (lx0 - 0.3, ly0, lx0, ly1), (lx1, ly0, lx1 + 0.3, walk_y - 1.6), (lx1, walk_y + 1.6, lx1 + 0.3, ly1)):
    box(x0, y0, 0.0, x1, y1, 0.15, "kerb")
# bays: 2.6 m wide, 5.2 m deep, white lines, in rows either side of the walkway
for row_y in (8.6, 13.8, 26.0, 36.6, 48.8, 54.0):
    x = lx0 + 0.7
    while x < lx1 - 0.6:
        box(x - 0.05, row_y - 2.6, 0.04, x + 0.05, row_y + 2.6, 0.045, "paint")
        x += 2.6
# the walkway through the lot and on to the pavilion, a zebra where it crosses the aisles
box(lx0 + 2.0, walk_y - 1.6, 0.0, pav[0], walk_y + 1.6, 0.08, "paving")
for k in range(int((lx1 - lx0) / 1.2)):
    x = lx0 + 2.0 + k * 1.2
    if x < lx1 - 1:
        box(x, walk_y - 1.5, 0.08, x + 0.6, walk_y + 1.5, 0.085, "paint")
# lamp posts along the walkway, trees round the lot
for x in range(int(lx0) + 6, int(pav[0]), 12):
    for y in (walk_y - 2.2, walk_y + 2.2):
        cyl(x, y, 0.0, 0.07, 6.0, "pole")
        box(x - 0.35, y - 0.12, 5.9, x + 0.35, y + 0.12, 6.05, "pole")
        box(x - 0.3, y - 0.1, 5.85, x + 0.3, y + 0.1, 5.9, "lamp")
for k, (x, y) in enumerate([(lx0 - 2, ly0 + 6 + i * 9) for i in range(6)] + [(lx0 + 6 + i * 10, ly1 + 2) for i in range(5)]
                           + [(lx0 + 6 + i * 10, ly0 - 2) for i in range(5)]):
    cyl(x, y, 0.0, 0.18, 2.2, "trunk", verts=8)
    cone(x, y, 1.6, 1.6 + (k % 3) * 0.3, 4.0 + (k % 2), "leaves")

# ------------------------------------------------------------------ the cars (assumed): one simple body each
for cx, cy, yaw, c in S["cars"]:
    g = "cars"
    s = 1 if yaw < 1 else -1           # which way it faces (along y)
    L, W = 4.4, 1.8
    box(cx - W / 2, cy - L / 2, 0.3, cx + W / 2, cy + L / 2, 0.95, f"car{c}", g)
    box(cx - W / 2 + 0.12, cy - L / 2 + 1.0 + (0.3 if s < 0 else 0), 0.95, cx + W / 2 - 0.12, cy + L / 2 - 1.0 - (0.3 if s > 0 else 0), 1.45, "window", g)
    box(cx - W / 2 + 0.1, cy - L / 2 + 1.05 + (0.3 if s < 0 else 0), 1.45, cx + W / 2 - 0.1, cy + L / 2 - 1.05 - (0.3 if s > 0 else 0), 1.5, f"car{c}", g)
    for dy in (-1.4, 1.4):
        for dx in (-W / 2, W / 2):
            cyl(cx + dx, cy + dy, 0.33, 0.33, 0.24, "tyre", g, verts=10, axis="x")

# ------------------------------------------------------------------ the visitors' pavilion (assumed)
px0, py0, _, px1, py1, ph = pav
box(px0, py0, 0.0, px1, py1, 0.12, "floor")
box(px0 - 1.5, py0 - 0.5, ph, px1, py1 + 0.5, ph + 0.3, "frame")           # roof, with a canopy over the door
box(px0 - 1.5, py0 - 0.5, ph - 0.12, px1, py0 - 0.4, ph, "accent")
for x, y in ((px0, py0), (px0, py1), (px0 - 1.5, py0 - 0.4), (px0 - 1.5, py1 + 0.4)):
    box(x - 0.1, y - 0.1, 0.0, x + 0.1, y + 0.1, ph, "frame")
door0, door1 = walk_y - 1.0, walk_y + 1.0
for y0, y1 in ((py0, door0), (door1, py1)):                                 # glass west face, a 2 m doorway
    box(px0 - 0.03, y0, 0.12, px0 + 0.03, y1, ph, "glass")
box(px0 - 0.06, door0, 2.4, px0 + 0.06, door1, ph, "frame")
for y in (py0, py1):                                                        # glass sides
    box(px0, y - 0.03, 0.12, px1, y + 0.03, ph, "glass")
box(px1 - 3.0, py0 + 0.6, 0.12, px1 - 2.2, py0 + 3.4, 1.05, "panel")         # a reception desk and a bench
box(px1 - 3.05, py0 + 0.55, 1.05, px1 - 2.15, py0 + 3.45, 1.1, "accent")
box(px0 + 1.0, py1 - 1.0, 0.12, px0 + 4.0, py1 - 0.5, 0.55, "panel")
gd = S["ground_door"]                                                       # the ground door into the lift: a frame
box(gd[0] - 0.08, gd[1] - 0.1, 0.0, gd[0], gd[1], gd[5] + 0.1, "frame")
box(gd[0] - 0.08, gd[4], 0.0, gd[0], gd[4] + 0.1, gd[5] + 0.1, "frame")
box(gd[0] - 0.08, gd[1] - 0.1, gd[5], gd[0], gd[4] + 0.1, gd[5] + 0.1, "frame")

# ------------------------------------------------------------------ the lift (permit set: P1 passenger lift)
lb = P["lift"]["box"]
x0, y0, z0, x1, y1, z1 = lb
t = 0.12
cz = 7.5
mid_y = (y0 + y1) / 2
for (a0, a1, b0, b1, c0, c1) in ((x0, x1, y0, y0 + t, 0.0, z1), (x0, x1, y1 - t, y1, 0.0, z1)):   # side walls of the shaft
    box(a0, b0, c0, a1, b1, c1, "panel")
for xw, opens_at in ((x0, 0.0), (x1 - t, cz)):                              # end walls, each with its doorway
    box(xw, y0, 0.0, xw + t, mid_y - 0.6, z1, "panel")
    box(xw, mid_y + 0.6, 0.0, xw + t, y1, z1, "panel")
    for za, zb in ((0.0, opens_at), (opens_at + 2.4, z1)):
        if zb > za:
            box(xw, mid_y - 0.6, za, xw + t, mid_y + 0.6, zb, "panel")
    box(xw - 0.02, mid_y - 0.7, opens_at + 2.4, xw + t + 0.02, mid_y + 0.7, opens_at + 2.55, "steel")
    box(xw + (t if xw > x0 else -0.03), mid_y + 0.75, opens_at + 1.1, xw + (t + 0.03 if xw > x0 else 0.0), mid_y + 0.9, opens_at + 1.35, "steel")
box(x0, y0, z1 - 0.15, x1, y1, z1, "panel")
# the car: floor, side walls, roof, a rail; it rides from the ground (0) to the clean floor (7.5)
c = "lift_car"
ix0, iy0, ix1, iy1 = x0 + t + 0.05, y0 + t + 0.05, x1 - t - 0.05, y1 - t - 0.05
box(ix0, iy0, 0.0, ix1, iy1, 0.1, "dark", c)
for ya, yb in ((iy0, iy0 + 0.05), (iy1 - 0.05, iy1)):
    box(ix0, ya, 0.1, ix1, yb, 2.4, "steel", c)
    box(ix0 + 0.2, ya + (0.05 if ya == iy0 else -0.05), 0.9, ix1 - 0.2, yb + (0.05 if ya == iy0 else -0.05), 0.95, "dark", c)
box(ix0, iy0, 2.4, ix1, iy1, 2.5, "panel", c)
box(ix0 + 0.4, iy0 + 0.4, 2.38, ix1 - 0.4, iy1 - 0.4, 2.4, "lamp", c)

# ------------------------------------------------------------------ the lift lobby on the clean floor (assumed walls)
for w in S["lobby_walls"]:
    box(*w, "panel")
box(x1, y0, cz, -0.6, y1 + 0.2, cz + 0.02, "floor")

# ------------------------------------------------------------------ the gowning room (permit set: P1-GW1)
for k in ("entry_door", "clean_door"):
    d = P[k]["box"]
    along_x = (d[3] - d[0]) > (d[4] - d[1])
    if along_x:
        box(d[0] - 0.08, d[1] - 0.05, d[2], d[0], d[4] + 0.05, d[5], "frame")
        box(d[3], d[1] - 0.05, d[2], d[3] + 0.08, d[4] + 0.05, d[5], "frame")
        box(d[0] - 0.08, d[1] - 0.05, d[5] - 0.08, d[3] + 0.08, d[4] + 0.05, d[5], "frame")
    else:
        box(d[0] - 0.05, d[1] - 0.08, d[2], d[3] + 0.05, d[1], d[5], "frame")
        box(d[0] - 0.05, d[4], d[2], d[3] + 0.05, d[4] + 0.08, d[5], "frame")
        box(d[0] - 0.05, d[1] - 0.08, d[5] - 0.08, d[3] + 0.05, d[4] + 0.08, d[5], "frame")
ed = P["entry_door"]["box"]
box(ed[0], ed[1] - 1.2, cz, ed[3], ed[1] - 0.1, cz + 0.01, "mat")          # a tacky mat inside the entry door (assumed)
for lk in P["lockers"]:
    a = lk["box"]
    box(a[0], a[1] + 0.01, a[2], a[3], a[4] - 0.01, a[5], "locker")
    box(a[3], a[1] + 0.03, a[2] + 0.1, a[3] + 0.01, a[4] - 0.03, a[5] - 0.1, "steel")
    box(a[3] + 0.01, (a[1] + a[4]) / 2 - 0.02, a[2] + 1.0, a[3] + 0.03, (a[1] + a[4]) / 2 + 0.02, a[2] + 1.2, "dark")
    for zz in (a[2] + 0.5, a[5] - 0.25):
        box(a[3] + 0.005, a[1] + 0.12, zz, a[3] + 0.015, a[4] - 0.12, zz + 0.04, "dark")
b = P["bench"]["box"]
box(b[0], b[1], b[5] - 0.05, b[3], b[4], b[5], "steel")
for y in (b[1] + 0.2, b[4] - 0.2):
    box(b[0] + 0.05, y - 0.03, b[2], b[3] - 0.05, y + 0.03, b[5] - 0.05, "steel")
r = P["rack"]["box"]
for y in (r[1] + 0.05, r[4] - 0.05):
    box(r[0] + 0.25, y - 0.025, r[2], r[0] + 0.3, y + 0.025, r[5], "steel")
box(r[0] + 0.2, r[1], r[5] - 0.05, r[0] + 0.35, r[4], r[5], "steel")
n = 6
for k in range(n):                                                          # clean suits on hangers, hoods above
    y = r[1] + 0.15 + k * (r[4] - r[1] - 0.3) / (n - 1)
    box(r[0] + 0.1, y - 0.03, r[5] - 1.45, r[0] + 0.5, y + 0.03, r[5] - 0.12, "suit")
    box(r[0] + 0.15, y - 0.11, r[5] - 0.75, r[0] + 0.45, y + 0.11, r[5] - 0.25, "suit")
# boots on a low shelf by the rack (assumed)
box(r[0], r[1] - 1.2, cz, r[0] + 0.45, r[1] - 0.2, cz + 0.3, "steel")
for k in range(4):
    y = r[1] - 1.1 + k * 0.22
    box(r[0] + 0.05, y, cz + 0.3, r[0] + 0.35, y + 0.15, cz + 0.62, "suit")

# ------------------------------------------------------------------ the air shower (permit set: P1-GW1's)
s = P["air_shower"]["box"]
sx0, sy0, sz0, sx1, sy1, sz1 = s
smid = (sy0 + sy1) / 2
w = 0.08
for y_a, y_b in ((sy0, sy0 + w), (sy1 - w, sy1)):                           # stainless side walls with nozzle rows
    box(sx0, y_a, sz0, sx1, y_b, sz1, "steel")
    inner = y_b if y_a == sy0 else y_a
    for zi in range(5):
        for xi in range(3):
            cyl(sx0 + 0.25 + xi * 0.35, inner + (0.02 if y_a == sy0 else -0.02), sz0 + 0.6 + zi * 0.3, 0.025, 0.04, "dark", verts=8, axis="y")
box(sx0, sy0, sz1 - 0.12, sx1, sy1, sz1, "steel")
box(sx0, sy0, sz0, sx1, sy1, sz0 + 0.03, "dark")
for xe in (sx0, sx1 - 0.05):                                                # end frames with open glass doors
    box(xe, sy0, sz0, xe + 0.05, smid - 0.45, sz1, "steel")
    box(xe, smid + 0.45, sz0, xe + 0.05, sy1, sz1, "steel")
    box(xe, smid - 0.45, sz1 - 0.35, xe + 0.05, smid + 0.45, sz1, "steel")
box(sx0 - 0.85, smid - 0.47, sz0, sx0 - 0.03, smid - 0.45, sz1 - 0.4, "glass")   # the near door, swung open
box(sx0 + 0.3, sy1 + 0.0, sz1 - 0.3, sx0 + 0.5, sy1 + 0.02, sz1 - 0.18, "green")  # its ready light

entrance = join("entrance", "entrance")
car = join("lift_car", "lift_car")
cars = join("cars", "cars")
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_apply=True)
print(f"entrance: {len(entrance.data.polygons)} faces, lift car {len(car.data.polygons)}, "
      f"{len(S['cars'])} cars {len(cars.data.polygons)} faces -> {OUT}")
