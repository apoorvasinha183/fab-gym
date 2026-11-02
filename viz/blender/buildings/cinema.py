"""The campus cinema for the 3D fab (docs/FAB-3D.md): a small building south of phase 1 where the silicon film plays.
Our own design, modelled in plan coordinates (metres, x east, y north, z up), so it lands in place in the scene. The
screen is its own mesh with its own material, `cinema_screen`, which the scene replaces with the playing film. From the
SMT2020 testbed; not a real fab.

    Blender -b --factory-startup -P viz/blender/buildings/cinema.py -- --out data/fab3d/models/cinema.glb
"""

import math
import os
import sys

import bpy

A = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = A[A.index("--out") + 1] if "--out" in A else "data/fab3d/models/cinema.glb"
X0, X1, Y0, Y1 = 40.0, 76.0, -122.0, -98.0      # the footprint: 36 m by 24 m (assumed)
H = 9.0
LOBBY = 7.0                                      # the lobby's depth, at the north (entrance) side
COLOURS = {
    "cinema_wall": ((0.86, 0.85, 0.82), 0.0, 0.6, None),
    "cinema_trim": ((0.15, 0.17, 0.22), 0.2, 0.4, None),
    "cinema_floor": ((0.28, 0.24, 0.22), 0.0, 0.7, None),
    "cinema_carpet": ((0.32, 0.08, 0.10), 0.0, 0.9, None),
    "cinema_seat": ((0.70, 0.10, 0.12), 0.0, 0.75, None),
    "cinema_seatback": ((0.55, 0.07, 0.09), 0.0, 0.75, None),
    "cinema_frame": ((0.05, 0.05, 0.06), 0.1, 0.5, None),
    "cinema_screen": ((0.92, 0.92, 0.92), 0.0, 0.9, None),
    "cinema_glass": ((0.55, 0.75, 0.88), 0.0, 0.05, None),
    "cinema_marquee": ((1.0, 0.85, 0.45), 0.0, 0.3, ((1.0, 0.82, 0.4), 3.0)),
    "cinema_lamp": ((1.0, 0.9, 0.7), 0.0, 0.3, ((1.0, 0.85, 0.6), 4.0)),
    "cinema_poster0": ((0.20, 0.45, 0.95), 0.0, 0.4, ((0.20, 0.45, 0.95), 0.6)),
    "cinema_poster1": ((0.95, 0.70, 0.20), 0.0, 0.4, ((0.95, 0.70, 0.20), 0.6)),
    "cinema_poster2": ((0.45, 0.85, 0.55), 0.0, 0.4, ((0.45, 0.85, 0.55), 0.6)),
    "cinema_wood": ((0.45, 0.30, 0.18), 0.0, 0.55, None),
    "cinema_paving": ((0.62, 0.62, 0.60), 0.0, 0.8, None),
}


def material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    base, metal, rough, emit = COLOURS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*base, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    if emit:
        for k in ("Emission Color", "Emission"):
            if k in p.inputs:
                p.inputs[k].default_value = (*emit[0], 1)
                break
        p.inputs["Emission Strength"].default_value = emit[1]
    return m


PARTS = {}


def box(x0, y0, z0, x1, y1, z1, mat, group="cinema"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    ob = bpy.context.active_object
    ob.scale = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    ob.data.materials.append(material(mat))
    PARTS.setdefault(group, []).append(ob)
    return ob


bpy.ops.wm.read_factory_settings(use_empty=True)
T = 0.3                                                               # wall thickness
# paving round the building and the floor
box(X0 - 6, Y0 - 3, -0.05, X1 + 6, Y1 + 8, 0.0, "cinema_paving")
box(X0, Y0, 0.0, X1, Y1, 0.1, "cinema_floor")
# walls: south (behind the screen), east, west, the north front with a door opening and glass, the lobby wall
box(X0, Y0, 0, X1, Y0 + T, H, "cinema_wall")
box(X0, Y0, 0, X0 + T, Y1, H, "cinema_wall")
box(X1 - T, Y0, 0, X1, Y1, H, "cinema_wall")
mid = (X0 + X1) / 2
box(X0, Y1 - T, 0, mid - 3, Y1, H, "cinema_wall")
box(mid + 3, Y1 - T, 0, X1, Y1, H, "cinema_wall")
box(mid - 3, Y1 - T, 3.2, mid + 3, Y1, H, "cinema_wall")
box(mid - 3, Y1 - 0.12, 0.1, mid + 3, Y1 - 0.06, 3.2, "cinema_glass")
box(X0, Y1 - LOBBY, 0, mid - 1.5, Y1 - LOBBY + T, 4.0, "cinema_wall")    # lobby to hall, with an opening in the middle
box(mid + 1.5, Y1 - LOBBY, 0, X1, Y1 - LOBBY + T, 4.0, "cinema_wall")
box(X0, Y1 - LOBBY, 4.0, X1, Y1 - LOBBY + T, H, "cinema_wall")
# the roof, with a trim band
box(X0 - 0.3, Y0 - 0.3, H, X1 + 0.3, Y1 + 0.3, H + 0.4, "cinema_trim")
# the entrance canopy and the marquee band above it (no text: the scene writes the title)
box(mid - 6, Y1, 3.4, mid + 6, Y1 + 4, 3.7, "cinema_trim")
box(mid - 6, Y1 + 3.9, 3.7, mid + 6, Y1 + 4.05, 4.6, "cinema_marquee")
for k in (-5.5, 5.5):
    box(mid + k - 0.12, Y1 + 3.7, 0, mid + k + 0.12, Y1 + 3.94, 3.4, "cinema_trim")
# lobby: a counter, benches, poster frames
box(X0 + 3, Y1 - 5.5, 0.1, X0 + 9, Y1 - 4.6, 1.1, "cinema_wood")
for k in range(3):
    box(X1 - 12 + k * 3.5, Y1 - 3.2, 0.1, X1 - 10 + k * 3.5, Y1 - 2.6, 0.55, "cinema_wood")
for k in range(3):
    x = X0 + 12 + k * 4
    box(x, Y1 - LOBBY + T, 1.2, x + 2.2, Y1 - LOBBY + T + 0.06, 4.0, "cinema_frame")
    box(x + 0.15, Y1 - LOBBY + T + 0.061, 1.35, x + 2.05, Y1 - LOBBY + T + 0.07, 3.85, f"cinema_poster{k}")
# the hall: carpet, raked rows of seats facing the screen at the south wall
hall_y0, hall_y1 = Y0 + T, Y1 - LOBBY
box(X0 + T, hall_y0, 0.1, X1 - T, hall_y1, 0.12, "cinema_carpet")
rows, per_row = 8, 14
row0 = Y0 + 7.0                                                      # the first row, 6.7 m from the screen
for r in range(rows):
    y = row0 + r * 1.1
    z = 0.12 + r * 0.32
    box(X0 + T, y - 0.55, 0.12, X1 - T, y + 0.55, z, "cinema_carpet")                 # the step
    for k in range(per_row):
        x = mid - (per_row - 1) * 0.6 / 2 + k * 0.6
        if per_row // 2 - 1 <= k <= per_row // 2:                                   # a central aisle
            continue
        box(x - 0.25, y - 0.25, z, x + 0.25, y + 0.2, z + 0.45, "cinema_seat")
        box(x - 0.25, y + 0.2, z + 0.3, x + 0.25, y + 0.3, z + 1.0, "cinema_seatback")
# wall lights along the hall
for y in range(int(hall_y0) + 3, int(hall_y1) - 1, 3):
    for x in (X0 + T + 0.05, X1 - T - 0.08):
        box(x, y, 3.0, x + 0.03, y + 0.6, 3.15, "cinema_lamp")
# the screen: a frame and the screen surface (16:9, 12 m wide), its own object and material
sw, sh, sz = 12.0, 6.75, 1.6
box(mid - sw / 2 - 0.3, Y0 + T, sz - 0.3, mid + sw / 2 + 0.3, Y0 + T + 0.08, sz + sh + 0.3, "cinema_frame")
bpy.ops.mesh.primitive_plane_add(size=1, location=(mid, Y0 + T + 0.09, sz + sh / 2), rotation=(math.pi / 2, 0, 0))
scr = bpy.context.active_object
scr.scale = (sw, sh, 1)
scr.data.materials.append(material("cinema_screen"))
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
scr.name = scr.data.name = "screen"

# one mesh for the building (joined), the screen apart
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
print(f"cinema: {len(b.data.polygons)} faces, screen {sw} x {sh} m at plan ({mid}, {Y0 + T}) -> {OUT}")
