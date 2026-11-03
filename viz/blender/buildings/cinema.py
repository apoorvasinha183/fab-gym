"""The campus cinema for the 3D fab (docs/FAB-3D.md, F11), built from the plan the rules generator writes
(viz/cinema/plan.py -> plan.json), so the building, its floor plan sheet and its rule check never disagree. Plan
coordinates in metres (x east, y north, z up). The screen is its own mesh named `screen` with the material
`cinema_screen`, which the scene replaces with the playing film. Looks and the sizes no rule gives are ours. From the
SMT2020 testbed's campus, our own design; not a real building.

    Blender -b --factory-startup -P viz/blender/buildings/cinema.py -- --plan data/cinema/plan.json --out data/fab3d/models/cinema.glb
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

A = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = A[A.index("--out") + 1] if "--out" in A else "data/fab3d/models/cinema.glb"
PLAN = A[A.index("--plan") + 1] if "--plan" in A else "data/cinema/plan.json"
P = json.load(open(PLAN))
C = P["choices"]
H = C["hall_height_m"]
T = 0.3

COLOURS = {   # base, metallic, roughness, emission (colour, strength), alpha
    "cinema_wall": ((0.86, 0.85, 0.82), 0.0, 0.6, None, 1),
    "cinema_hall_wall": ((0.16, 0.15, 0.2), 0.0, 0.85, None, 1),
    "cinema_trim": ((0.15, 0.17, 0.22), 0.2, 0.4, None, 1),
    "cinema_floor": ((0.28, 0.24, 0.22), 0.0, 0.7, None, 1),
    "cinema_lobby_floor": ((0.82, 0.8, 0.76), 0.0, 0.45, None, 1),
    "cinema_carpet": ((0.32, 0.08, 0.10), 0.0, 0.9, None, 1),
    "cinema_step_edge": ((0.95, 0.75, 0.25), 0.0, 0.5, ((1.0, 0.75, 0.3), 0.6), 1),
    "cinema_seat": ((0.70, 0.10, 0.12), 0.0, 0.75, None, 1),
    "cinema_seatback": ((0.55, 0.07, 0.09), 0.0, 0.75, None, 1),
    "cinema_companion": ((0.85, 0.55, 0.12), 0.0, 0.7, None, 1),
    "cinema_wheelchair": ((0.12, 0.38, 0.72), 0.0, 0.6, None, 1),
    "cinema_frame": ((0.05, 0.05, 0.06), 0.1, 0.5, None, 1),
    "cinema_screen": ((0.92, 0.92, 0.92), 0.0, 0.9, None, 1),
    "cinema_glass": ((0.55, 0.75, 0.88), 0.0, 0.05, None, 0.3),
    "cinema_marquee": ((1.0, 0.85, 0.45), 0.0, 0.3, ((1.0, 0.82, 0.4), 3.0), 1),
    "cinema_lamp": ((1.0, 0.9, 0.7), 0.0, 0.3, ((1.0, 0.85, 0.6), 4.0), 1),
    "cinema_exit": ((0.2, 0.85, 0.35), 0.0, 0.3, ((0.2, 1.0, 0.4), 4.0), 1),
    "cinema_rail": ((0.78, 0.78, 0.76), 0.8, 0.3, None, 1),
    "cinema_wood": ((0.45, 0.30, 0.18), 0.0, 0.55, None, 1),
    "cinema_paving": ((0.62, 0.62, 0.60), 0.0, 0.8, None, 1),
    "cinema_tile": ((0.88, 0.9, 0.92), 0.0, 0.4, None, 1),
    "cinema_door": ((0.35, 0.37, 0.4), 0.4, 0.4, None, 1),
    "cinema_poster_a": ((0.85, 0.45, 0.15), 0.0, 0.5, ((0.95, 0.5, 0.18), 1.2), 1),
    "cinema_poster_b": ((0.15, 0.35, 0.75), 0.0, 0.5, ((0.2, 0.42, 0.9), 1.2), 1),
    "cinema_poster_c": ((0.55, 0.12, 0.45), 0.0, 0.5, ((0.7, 0.16, 0.55), 1.2), 1),
    "cinema_poster_d": ((0.12, 0.5, 0.35), 0.0, 0.5, ((0.16, 0.62, 0.42), 1.2), 1),
}
# what the visitor stands on: the floor map is cast down onto these only (walls, seats and rails are not floor)
FLOOR_MATS = {"cinema_paving", "cinema_floor", "cinema_lobby_floor", "cinema_carpet", "cinema_step_edge",
              "cinema_wheelchair", "cinema_tile"}
BUILT = {"posters": []}


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
    if emit:
        for k in ("Emission Color", "Emission"):
            if k in p.inputs:
                p.inputs[k].default_value = (*emit[0], 1)
                break
        p.inputs["Emission Strength"].default_value = emit[1]
    return m


PARTS = {}


def box(x0, y0, z0, x1, y1, z1, mat, group="cinema"):
    if x1 - x0 <= 1e-4 or y1 - y0 <= 1e-4 or z1 - z0 <= 1e-4:
        return None
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    ob = bpy.context.active_object
    ob.scale = (x1 - x0, y1 - y0, z1 - z0)
    ob.data.materials.append(material(mat))
    PARTS.setdefault(group, []).append(ob)
    return ob


DOOR_H = 2.3


def doors_in(x0, y0, x1, y1):
    # the plan's doors whose centre lies in this wall's box (a little grown): [(lo, hi, z bottom)] along the wall
    along_x = (x1 - x0) >= (y1 - y0)
    out = []
    for d in P["doors"]:
        dx, dy = d["at"]
        if x0 - 0.25 <= dx <= x1 + 0.25 and y0 - 0.25 <= dy <= y1 + 0.25:
            c = dx if along_x else dy
            out.append((c - d["clear_m"] / 2, c + d["clear_m"] / 2, 0.04 + d["level"]))
    return along_x, sorted(out)


def wall(x0, y0, x1, y1, z0, z1, mat):
    # a wall box with the plan's doorways cut through it: solid either side, below the door's sill and above its head
    along_x, cuts = doors_in(x0, y0, x1, y1)
    a, b = (x0, x1) if along_x else (y0, y1)
    pos = a
    for lo, hi, zb in cuts:
        pieces = [(pos, lo, z0, z1), (lo, hi, z0, zb), (lo, hi, min(z1, zb + DOOR_H), z1)]
        for p0, p1, q0, q1 in pieces:
            if along_x:
                box(p0, y0, q0, p1, y1, q1, mat)
            else:
                box(x0, p0, q0, x1, p1, q1, mat)
        pos = hi
    if along_x:
        box(pos, y0, z0, b, y1, z1, mat)
    else:
        box(x0, pos, z0, x1, b, z1, mat)


def rail(pts, mat="cinema_rail", r=0.025, group="cinema"):
    # a handrail through the points, with posts every 1.2 m
    for (ax, ay, az), (bx, by, bz) in zip(pts, pts[1:]):
        L = math.dist((ax, ay, az), (bx, by, bz))
        if L < 1e-3:
            continue
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=r, depth=L, location=((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2))
        ob = bpy.context.active_object
        d = (bx - ax, by - ay, bz - az)
        ob.rotation_mode = "XYZ"
        ob.rotation_euler = (0.0, math.acos(max(-1, min(1, d[2] / L))), math.atan2(d[1], d[0]))
        ob.data.materials.append(material(mat))
        PARTS.setdefault(group, []).append(ob)
        n = max(1, int(L / 1.2))
        for k in range(n + 1):
            u = k / n
            px, py, pz = ax + d[0] * u, ay + d[1] * u, az + d[2] * u
            box(px - 0.02, py - 0.02, pz - 0.9, px + 0.02, py + 0.02, pz, mat, group)


bpy.ops.wm.read_factory_settings(use_empty=True)
x0, y0, x1, y1 = P["footprint"]
rooms = {r["name"]: r for r in P["rooms"]}
hall = rooms["hall"]["box"]
lobby = rooms["lobby"]["box"]

# ------------------------------------------------------------------ the site, floors and outer walls
box(x0 - 6, y0 - 3, -0.05, x1 + 6, y1 + 8, 0.0, "cinema_paving")
box(x0, y0, 0.0, x1, y1, 0.02, "cinema_floor")
box(lobby[0], lobby[1], 0.02, lobby[2], lobby[3], 0.04, "cinema_lobby_floor")
for b in ([x0, y0, x0 + T, y1], [x1 - T, y0, x1, y1], [x0, y0, x1, y0 + T]):
    wall(b[0], b[1], b[2], b[3], 0, H, "cinema_wall")
mid_x = (x0 + x1) / 2
box(x0, y1 - T, 0, mid_x - 6, y1, H, "cinema_wall")
box(mid_x + 6, y1 - T, 0, x1, y1, H, "cinema_wall")
box(mid_x - 6, y1 - T, 3.4, mid_x + 6, y1, H, "cinema_wall")
box(mid_x - 6, y1 - 0.12, 0.04, mid_x - 1.5, y1 - 0.06, 3.4, "cinema_glass")
box(mid_x + 1.5, y1 - 0.12, 0.04, mid_x + 6, y1 - 0.06, 3.4, "cinema_glass")
box(mid_x - 1.5, y1 - 0.14, 2.6, mid_x + 1.5, y1 - 0.04, 3.4, "cinema_glass")
box(mid_x - 1.5, y1 - 0.16, 2.5, mid_x + 1.5, y1 - 0.02, 2.6, "cinema_frame")
for xx in (mid_x - 6, mid_x - 3, mid_x - 1.5, mid_x + 1.5, mid_x + 3, mid_x + 6):
    box(xx - 0.05, y1 - 0.14, 0.04, xx + 0.05, y1 - 0.04, 3.4, "cinema_frame")
box(x0 - 0.3, y0 - 0.3, H, x1 + 0.3, y1 + 0.3, H + 0.4, "cinema_trim")
box(mid_x - 7, y1, 3.6, mid_x + 7, y1 + 4, 3.9, "cinema_trim")                   # canopy and marquee band
box(mid_x - 7, y1 + 3.9, 3.9, mid_x + 7, y1 + 4.05, 4.8, "cinema_marquee")
for k in (-6.5, 6.5):
    box(mid_x + k - 0.12, y1 + 3.7, 0, mid_x + k + 0.12, y1 + 3.94, 3.6, "cinema_trim")

# ------------------------------------------------------------------ the hall's walls (dark, so the screen reads)
hx0, hy0, hx1, hy1 = hall
wall(hx0, hy1, hx1, hy1 + T, 0.04, H, "cinema_hall_wall")
wall(hx1, hy0, hx1 + T, hy1 + T, 0.04, H, "cinema_hall_wall")
box(hx0 + 0.02, hy0 + 0.02, 0.04, hx0 + 0.05, hy1 - 0.02, H - 0.2, "cinema_hall_wall")
wall(hx0, hy0 + 0.02, hx1, hy0 + 0.05, 0.04, H - 0.2, "cinema_hall_wall")

# ------------------------------------------------------------------ the stadium: level cross aisles, rows on risers
for ca in P["cross_aisles"]:
    b = ca["box"]
    top = 0.04 + ca["level"] if ca["level"] > 0 else 0.06
    box(b[0], b[1], 0.04, b[2], b[3], top, "cinema_carpet")
    box(b[0], b[1], top, b[0] + 0.05, b[3], top + 0.005, "cinema_step_edge")
for r in P["rows"]:
    if r["block"] != "centre":
        continue
    # the row's tier across the hall, with the stepped aisles left open (they get their own half-steps below)
    cuts = sorted((a["box"][1], a["box"][3]) for a in P["aisles"] if a["box"][0] - 1e-6 <= r["x0"] and r["x1"] <= a["box"][2] + 1e-6)
    ya = hy0 + 0.05
    for c0, c1 in cuts + [(hy1, hy1)]:
        box(r["x0"], ya, 0.04, r["x1"], c0, 0.04 + r["level"], "cinema_carpet")
        box(r["x0"], ya, 0.04 + r["level"], r["x0"] + 0.05, c0, 0.045 + r["level"], "cinema_step_edge")
        ya = c1
# stepped aisles: a half-step in each row (risers of half the row's rise), and a mid-aisle handrail
for a in P["aisles"]:
    b = a["box"]
    ym = (b[1] + b[3]) / 2
    rows_in = [r for r in P["rows"] if r["block"] == "centre" and b[0] - 1e-6 <= r["x0"] and r["x1"] <= b[2] + 1e-6]
    pts = []
    for r in rows_in:
        half = (r["x0"] + r["x1"]) / 2
        box(r["x0"], b[1], 0.04, half, b[3], 0.04 + r["level"] - a["riser_m"], "cinema_carpet")
        box(half, b[1], 0.04, r["x1"], b[3], 0.04 + r["level"], "cinema_carpet")
        box(r["x0"], b[1], 0.04 + r["level"] - a["riser_m"], r["x0"] + 0.05, b[3], 0.045 + r["level"] - a["riser_m"], "cinema_step_edge")
        box(half, b[1], 0.04 + r["level"], half + 0.05, b[3], 0.045 + r["level"], "cinema_step_edge")
        pts.append((r["x0"] + 0.1, ym, 0.04 + r["level"] - a["riser_m"] + 0.9))
        pts.append((r["x1"] - 0.1, ym, 0.04 + r["level"] + 0.9))
    if len(pts) >= 2:
        rail(pts)
# seats: a seat pan and a back to the rear (east), facing the screen
sw = C["seat_width_m"]
for s in P["seats"]:
    z = 0.04 + s["level"]
    x = s["x"] - 0.15
    box(x - 0.25, s["y"] - sw / 2 + 0.04, z, x + 0.22, s["y"] + sw / 2 - 0.04, z + 0.45, "cinema_seat")
    box(x + 0.22, s["y"] - sw / 2 + 0.04, z + 0.3, x + 0.32, s["y"] + sw / 2 - 0.04, z + C["seat_back_m"], "cinema_seatback")
    box(x - 0.25, s["y"] + sw / 2 - 0.05, z, x + 0.25, s["y"] + sw / 2 - 0.02, z + 0.65, "cinema_seatback")
# wheelchair spaces: blue floor panels; companion seats in orange beside them
for w in P["wheelchair"]:
    b = w["box"]
    z = 0.06 + w["level"]
    box(b[0], b[1], z - 0.01, b[2], b[3], z + 0.002, "cinema_wheelchair")
    ax, ay = w["companion_at"]
    box(ax - 0.25, ay - 0.23, z, ax + 0.22, ay + 0.23, z + 0.45, "cinema_companion")
    box(ax + 0.22, ay - 0.23, z + 0.3, ax + 0.32, ay + 0.23, z + C["seat_back_m"], "cinema_companion")

# ------------------------------------------------------------------ the ramp up to the mid cross aisle, the front passage
rp = rooms["ramp"]
rb = rp["box"]
runs, run_m, land = rp["runs"], rp["run_m"], C["landing_m"]
rise_each = rp["rises_to"] / runs
x = rb[2] - land                         # bottom landing at the east end (from the lobby), rising westwards
box(x, rb[1], 0.04, rb[2], rb[3], 0.06, "cinema_lobby_floor")
z = 0.0
RY = rb[3] - 0.1                         # the handrail runs along the glass, clear of the hall's doorway
pts = [(rb[2] - land, RY, 0.96)]
for k in range(runs):
    n = 12
    for i in range(n):
        u0, u1 = i / n, (i + 1) / n
        box(x - run_m * u1, rb[1], 0.04, x - run_m * u0, rb[3], 0.06 + z + rise_each * (u0 + u1) / 2, "cinema_lobby_floor")
    pts.append((x, RY, 0.96 + z))
    pts.append((x - run_m, RY, 0.96 + z + rise_each))
    x -= run_m
    z += rise_each
    west = rb[0] if k == runs - 1 else x - land   # the top landing runs on to the ramp's end, so no gap is left
    box(west, rb[1], 0.04, x, rb[3], 0.06 + z, "cinema_lobby_floor")
    x = west
pts.append((x, RY, 0.96 + z))
rail(pts)
fp = rooms["front passage"]["box"]
box(fp[0], fp[1], 0.04, fp[2], fp[3], 0.06, "cinema_lobby_floor")
box(fp[2], fp[1], 0.04, fp[2] + 0.1, fp[3], 3.0, "cinema_wall")                # wall between the passage and the ramp

# ------------------------------------------------------------------ back of house: exit stair, projection room, toilets
for name in ("exit stair", "projection room", "toilets"):
    b = rooms[name]["box"]
    for wb in ([b[0], b[1], b[2], b[1] + 0.15], [b[0], b[3] - 0.15, b[2], b[3]], [b[2] - 0.15, b[1], b[2], b[3]]):
        wall(wb[0], wb[1], wb[2], wb[3], 0.04, H - 0.3, "cinema_wall")
es = rooms["exit stair"]["box"]
top = rooms["exit stair"]["rises_to"]
steps = int(round(top / 0.15))
for k in range(steps):
    yy = es[3] - 0.4 - k * 0.28
    box(es[0] + 0.15, yy - 0.28, 0.04, es[2] - 0.15, yy, 0.04 + top - k * 0.15, "cinema_tile")
pr = rooms["projection room"]
pb = pr["box"]
box(pb[0], pb[1], pr["level"], pb[2], pb[3], pr["level"] + 0.2, "cinema_tile")
box(hx1 + 0.02, (pb[1] + pb[3]) / 2 - 0.4, pr["level"] + 1.2, hx1 + T - 0.02, (pb[1] + pb[3]) / 2 + 0.4, pr["level"] + 1.6, "cinema_glass")
tb = rooms["toilets"]["box"]
box(tb[0], tb[1], 0.04, tb[2], tb[3], 0.06, "cinema_tile")

# ------------------------------------------------------------------ doors: frames, green exit signs over the exits
for d in P["doors"]:
    if d["name"] == "main entrance":
        continue
    dx, dy = d["at"]
    w = d["clear_m"]
    zb = 0.04 + d["level"]
    along_x = abs(dy - (y0 + T / 2)) < 0.4 or abs(dy - (hy1 + T / 2)) < 0.4
    if along_x:
        parts = [(dx - w / 2 - 0.08, dy - 0.2, zb, dx - w / 2, dy + 0.2, zb + 2.3), (dx + w / 2, dy - 0.2, zb, dx + w / 2 + 0.08, dy + 0.2, zb + 2.3),
                 (dx - w / 2 - 0.08, dy - 0.2, zb + 2.2, dx + w / 2 + 0.08, dy + 0.2, zb + 2.3)]
        sign = (dx - 0.3, dy - 0.25, zb + 2.4, dx + 0.3, dy + 0.25, zb + 2.62)
    else:
        parts = [(dx - 0.2, dy - w / 2 - 0.08, zb, dx + 0.2, dy - w / 2, zb + 2.3), (dx - 0.2, dy + w / 2, zb, dx + 0.2, dy + w / 2 + 0.08, zb + 2.3),
                 (dx - 0.2, dy - w / 2 - 0.08, zb + 2.2, dx + 0.2, dy + w / 2 + 0.08, zb + 2.3)]
        sign = (dx - 0.25, dy - 0.3, zb + 2.4, dx + 0.25, dy + 0.3, zb + 2.62)
    for q in parts:
        box(*q, "cinema_door")
    if d.get("exit"):
        box(*sign, "cinema_exit")
    # which way it swings: out of the hall, the way people leave (north to the lobby, south outside, east to the stair)
    out = [0.0, 1.0] if (along_x and dy > hy1 - 0.5) else ([0.0, -1.0] if along_x else [1.0, 0.0])
    BUILT.setdefault("doors", []).append({"name": d["name"], "at": [dx, dy], "clear_m": w, "z": zb, "height": DOOR_H - 0.1,
                                          "along": "x" if along_x else "y", "out": out})

# ------------------------------------------------------------------ the lobby: concession counter, benches, posters
box(lobby[0] + 2.0, lobby[1] + 4.0, 0.04, lobby[0] + 9.0, lobby[1] + 5.0, 1.1, "cinema_wood")
for k in range(3):
    xx = lobby[2] - 13 + k * 4
    box(xx, lobby[3] - 3.0, 0.04, xx + 2.2, lobby[3] - 2.4, 0.5, "cinema_wood")
gy = (rb[3] + lobby[1]) / 2                      # the line between the ramp and the lobby
gx0, gx1 = fp[2] + 0.1, rb[2] - land             # from the passage wall to the ramp's bottom landing, which stays open
box(gx0, gy - 0.03, 0.04, gx1, gy + 0.03, 3.4, "cinema_glass")
box(gx0, gy - 0.06, 3.4, gx1, gy + 0.06, 3.5, "cinema_frame")
box(gx0, gy - 0.06, 0.04, gx1, gy + 0.06, 0.12, "cinema_frame")
n_m = max(1, int((gx1 - gx0) / 3.0))
for k in range(n_m + 1):
    xx = gx0 + (gx1 - gx0) * k / n_m
    box(xx - 0.04, gy - 0.06, 0.04, xx + 0.04, gy + 0.06, 3.4, "cinema_frame")
for k, mat in enumerate(("cinema_poster_a", "cinema_poster_b", "cinema_poster_c", "cinema_poster_d")):
    xx = lobby[0] + 12.5 + k * 4
    yb = lobby[1] + 0.25                         # a lit case on a plinth, its face to the lobby (north)
    box(xx - 0.1, yb, 0.04, xx + 1.3, yb + 0.2, 0.5, "cinema_frame")
    box(xx - 0.1, yb, 0.5, xx + 1.3, yb + 0.12, 2.6, "cinema_frame")
    box(xx, yb + 0.12, 0.65, xx + 1.2, yb + 0.15, 2.45, mat)
    BUILT["posters"].append({"x0": xx, "x1": xx + 1.2, "z0": 0.65, "z1": 2.45, "y": yb + 0.15})
for xx in range(int(hx0) + 4, int(hx1), 3):
    for yy in (hy0 + 0.07, hy1 - 0.1):
        box(xx, yy, 3.0, xx + 0.6, yy + 0.03, 3.15, "cinema_lamp")

# ------------------------------------------------------------------ the screen on the west wall, facing east
sc = P["screen"]
sw_, sh_, sz = sc["width_m"], sc["height_m"], sc["bottom_m"]
box(sc["x"] - 0.05, sc["y_centre"] - sw_ / 2 - 0.3, sz - 0.3, sc["x"] + 0.03, sc["y_centre"] + sw_ / 2 + 0.3, sz + sh_ + 0.3, "cinema_frame")
bpy.ops.mesh.primitive_plane_add(size=1, location=(sc["x"] + 0.04, sc["y_centre"], sz + sh_ / 2), rotation=(math.pi / 2, 0, math.pi / 2))
scr = bpy.context.active_object
scr.scale = (sw_, sh_, 1)
scr.data.materials.append(material("cinema_screen"))
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
scr.name = scr.data.name = "screen"

# ------------------------------------------------------------------ the floor map: the top of whatever floor is under each point
verts, polys = [], []
for o in PARTS["cinema"]:
    if not o.data.materials or o.data.materials[0].name not in FLOOR_MATS:
        continue
    base = len(verts)
    verts += [o.matrix_world @ v.co for v in o.data.vertices]
    polys += [[base + i for i in p.vertices] for p in o.data.polygons]
tree = BVHTree.FromPolygons(verts, polys)
STEP = 0.1
nx, ny = int(round((x1 - x0) / STEP)) + 1, int(round((y1 - y0) / STEP)) + 1
cm = []
for j in range(ny):
    for i in range(nx):
        # two rays a little off the grid point, the higher kept, so a ray landing exactly on the seam between two
        # floor pieces cannot fall through to the ground under them
        tops = []
        for ox, oy in ((0.011, 0.013), (-0.017, -0.009)):
            hit = tree.ray_cast(Vector((x0 + i * STEP + ox, y0 + j * STEP + oy, 20.0)), Vector((0, 0, -1)))
            if hit[0] is not None:
                tops.append(hit[0].z)
        cm.append(int(round(max(tops) * 100)) if tops else -1)
BUILT["entrance"] = {"x0": mid_x - 1.5, "x1": mid_x + 1.5, "y": y1 - 0.09, "z0": 0.04, "z1": 2.5}
BUILT["floor"] = {"origin": [x0, y0], "step": STEP, "nx": nx, "ny": ny, "cm": cm,
                  "about": "Top of the cinema's floor under each point, in centimetres, row by row from the south-west "
                           "corner; -1 where nothing is built. Cast down onto the floor parts of the built model."}

bpy.ops.object.select_all(action="DESELECT")
obs = PARTS["cinema"]
for o in obs:
    o.select_set(True)
bpy.context.view_layer.objects.active = obs[0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
b = bpy.context.active_object
b.name = b.data.name = "cinema"
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_apply=True)
json.dump(BUILT, open(os.path.join(os.path.dirname(os.path.abspath(PLAN)), "built.json"), "w"), separators=(",", ":"))
print(f"cinema: {len(b.data.polygons)} faces from {PLAN} ({P['occupants']} occupants), screen {sw_} x {sh_:.2f} m -> {OUT}")
