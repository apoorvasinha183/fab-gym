"""The robot CEO for the 3D fab (docs/FAB-3D.md, step 3), modelled from the turnaround Meta's Muse Image drew from the
founder's coat-CEO picture (Character Sheet, design A). Our own model. It stands on the CC0 skeleton of Quaternius's
Universal Animation Library, so the library's CC0 clips drive it: the CC0 base body is kept as the skinned suit and
arms (recoloured and filled out), and the robot parts are fixed to their bones. From the SMT2020 testbed; not a real
fab.

    Blender -b --factory-startup -P viz/blender/characters/ceo.py -- --out data/fab3d/models/ceo.glb
"""

import glob
import math
import os
import sys

import bpy
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGV[ARGV.index("--out") + 1] if "--out" in ARGV else "data/fab3d/models/ceo.glb"
UAL = glob.glob(os.path.expanduser(
    "~/evalzero_work/fab-gym/data/assets/quaternius/universal-animation-library-standard/*/Unreal-Godot/UAL1_Standard.glb"))[0]
KEEP = ["Walk_Formal_Loop", "Walk_Loop", "Idle_Loop", "Idle_Talking_Loop", "Interact", "Sitting_Enter",
        "Sitting_Idle_Loop", "Sitting_Exit"]

COLOURS = {  # base, metallic, roughness, emission (colour, strength)
    "ceo_shell": ((0.90, 0.89, 0.85), 0.0, 0.35, None),
    "ceo_seam": ((0.62, 0.61, 0.57), 0.0, 0.5, None),
    "ceo_screen": ((0.035, 0.06, 0.08), 0.1, 0.15, None),
    "ceo_eye": ((0.45, 1.0, 0.82), 0.0, 0.3, ((0.45, 1.0, 0.82), 4.0)),
    "ceo_mint": ((0.48, 0.84, 0.72), 0.0, 0.35, None),
    "ceo_suit": ((0.06, 0.10, 0.26), 0.0, 0.62, None),
    "ceo_shirt": ((0.95, 0.95, 0.93), 0.0, 0.5, None),
    "ceo_red": ((0.80, 0.14, 0.14), 0.0, 0.5, None),
    "ceo_shoe": ((0.04, 0.04, 0.045), 0.2, 0.3, None),
    "ceo_metal": ((0.70, 0.72, 0.75), 1.0, 0.25, None),
    "ceo_lanyard": ((0.20, 0.45, 0.85), 0.0, 0.5, None),
    "ceo_white": ((0.97, 0.97, 0.97), 0.0, 0.4, None),
    "ceo_lamp_r": ((0.95, 0.15, 0.1), 0.0, 0.3, ((1.0, 0.15, 0.1), 2.0)),
    "ceo_lamp_a": ((1.0, 0.7, 0.1), 0.0, 0.3, ((1.0, 0.65, 0.1), 2.0)),
    "ceo_lamp_g": ((0.15, 0.9, 0.35), 0.0, 0.3, ((0.15, 1.0, 0.35), 2.0)),
}
RAINBOW = [(1.0, 0.42, 0.42), (1.0, 0.85, 0.24), (0.42, 0.80, 0.47), (0.30, 0.59, 1.0), (0.78, 0.49, 1.0)]
for i, c in enumerate(RAINBOW):
    COLOURS[f"ceo_wafer{i}"] = (c, 0.6, 0.15, (c, 0.6))


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
    m.diffuse_color = (*base, 1)
    return m


# ------------------------------------------------------------------ the skeleton and the body

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=UAL)
for o in list(bpy.data.objects):
    if o.type == "MESH" and (o.parent is None or o.name.startswith("Icosphere")):   # the library's preview sphere
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = next(o for o in bpy.data.objects if o.type == "MESH")
arm.name = "CEO"
for a in list(bpy.data.actions):
    if a.name not in KEEP and not any(a.name.startswith(k) for k in KEEP):
        bpy.data.actions.remove(a)


def bone_world(name, tail=False):
    b = arm.data.bones[name]
    return arm.matrix_world @ (b.tail_local if tail else b.head_local)


# The CC0 body is kept only for its hands (white robot gloves, the fingers animated); a copy of it lends its bone
# weights to the boxy jacket and trousers we model, so they bend with the clips like cloth (Blender's data transfer).
groups = {vg.index: vg.name for vg in body.vertex_groups}


def dominant(v):
    best = max(v.groups, key=lambda g: g.weight, default=None)
    return groups.get(best.group) if best else None


donor = body.copy()
donor.data = body.data.copy()
bpy.context.collection.objects.link(donor)
donor.modifiers.clear()
HAND = ("hand", "thumb", "index", "middle", "ring", "pinky")
keep = {v.index for v in body.data.vertices if (dominant(v) or "").startswith(HAND)}
bpy.context.view_layer.objects.active = body
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="DESELECT")
bpy.ops.object.mode_set(mode="OBJECT")
for v in body.data.vertices:
    v.select = v.index not in keep
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.delete(type="VERT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=0.0005)
bpy.ops.object.mode_set(mode="OBJECT")
body.data.materials.clear()
body.data.materials.append(material("ceo_white"))
for poly in body.data.polygons:
    poly.material_index = 0
disp = body.modifiers.new("chunky", "DISPLACE")      # chunkier robot hands
disp.strength = 0.02
disp.mid_level = 0.0
bpy.ops.object.modifier_move_to_index(modifier="chunky", index=0)
bpy.ops.object.modifier_apply(modifier="chunky")

CLOTH = []


def cloth(ob, mat, bevel=0.0, subdiv=1):
    """A garment we model, skinned with the CC0 body's weights at its nearest surface."""
    ob.data.materials.clear()
    ob.data.materials.append(material(mat))
    if bevel:
        md = ob.modifiers.new("bevel", "BEVEL")
        md.width = bevel
        md.segments = 3
    if subdiv:
        md = ob.modifiers.new("sub", "SUBSURF")
        md.levels = subdiv
    CLOTH.append(ob)
    return ob


def bw(name, tail=False):
    return bone_world(name, tail)


pel, sp3, nk = bw("pelvis"), bw("spine_03"), bw("neck_01")
sh = {s: bw(f"upperarm_{s}") for s in "lr"}
el = {s: bw(f"lowerarm_{s}") for s in "lr"}
th = {s: bw(f"thigh_{s}") for s in "lr"}
ca = {s: bw(f"calf_{s}") for s in "lr"}
an = {s: bw(f"foot_{s}") for s in "lr"}
# the jacket: a boxy block from below the waist to the shoulders, broad at the top, cut square at the hem
z0, z1 = pel.z - 0.09, nk.z + 0.02
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, sp3.y + 0.01, (z0 + z1) / 2))
jk = bpy.context.active_object
jk.scale = (0.56, 0.34, z1 - z0)
bpy.ops.object.transform_apply(scale=True)
for v in jk.data.vertices:                 # taper: shoulders broad, waist narrower, a slight drop at the shoulder line
    t = (v.co.z - z0) / (z1 - z0)
    v.co.x *= 0.86 + 0.18 * t
    if t > 0.95:
        v.co.x *= 0.8
cloth(jk, "ceo_suit", bevel=0.05)
# short sleeves over the shoulders
for s in "lr":
    a, b = sh[s], sh[s] + (el[s] - sh[s]) * 0.38
    mid = (a + b) / 2
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.085, depth=(b - a).length + 0.06, location=mid,
                                        rotation=(0, math.pi / 2, 0))
    cloth(bpy.context.active_object, "ceo_suit", bevel=0.01, subdiv=0)
# trousers: a tapered tube per leg from the hip to the ankle, and a seat joining them
for s in "lr":
    top, bot = th[s] + Vector((0, 0, 0.06)), an[s] + Vector((0, 0, 0.02))
    mid = (top + bot) / 2
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.068, radius2=0.08, depth=(top - bot).length, location=mid)
    cloth(bpy.context.active_object, "ceo_suit", bevel=0.0, subdiv=0)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, pel.y, pel.z - 0.06))
seat = bpy.context.active_object
seat.scale = (0.33, 0.24, 0.16)
cloth(seat, "ceo_suit", bevel=0.05, subdiv=0)

# apply the shapes, then take the body's weights at the nearest surface, then bind to the skeleton
for ob in CLOTH:
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    for md in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for g in donor.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    dt = ob.modifiers.new("weights", "DATA_TRANSFER")
    dt.object = donor
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.datalayer_transfer(modifier="weights") if False else None
    bpy.ops.object.modifier_apply(modifier="weights")
bpy.data.objects.remove(donor, do_unlink=True)

# ------------------------------------------------------------------ the robot parts, each fixed to one bone

PARTS = []


def part(ob, mat, bone, bevel=0.0):
    ob.data.materials.clear()
    ob.data.materials.append(material(mat))
    if bevel > 0:
        md = ob.modifiers.new("bevel", "BEVEL")
        md.width = bevel
        md.segments = 3
        md.limit_method = "ANGLE"
    PARTS.append((ob, bone))
    return ob


def box(c, size, mat, bone, bevel=0.0, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rot)
    ob = bpy.context.active_object
    ob.scale = size
    return part(ob, mat, bone, bevel)


def cyl(c, r, depth, mat, bone, rot=(0, 0, 0), verts=24, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=c, rotation=rot)
    return part(bpy.context.active_object, mat, bone, bevel)


def torus(c, R, r, mat, bone, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, location=c, rotation=rot, major_segments=28, minor_segments=8)
    return part(bpy.context.active_object, mat, bone)


def tube(points, r, mat, bone):
    cu = bpy.data.curves.new("tube", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 3
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for i, p in enumerate(points):
        bp = sp.bezier_points[i]
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("tube", cu)
    bpy.context.collection.objects.link(ob)
    return part(ob, mat, bone)


neck = bone_world("neck_01")
headb = bone_world("Head")
H = 0.55                           # head height (design A)
W, D = 0.58, 0.50                  # head width and depth
hz = headb.z + 0.02                # the head's underside
cx, cy = headb.x, headb.y
F = cy - D / 2                     # the front face (front is -y)

# head shell, back plates, seams
box((cx, cy, hz + H / 2), (W, D, H), "ceo_shell", "Head", bevel=0.06)
for z in (hz + 0.12, hz + H - 0.16):
    box((cx, cy + D / 2 + 0.002, z), (W * 0.7, 0.006, 0.012), "ceo_seam", "Head")
box((cx + 0.16, cy + D / 2 + 0.004, hz + H * 0.3), (0.12, 0.008, 0.08), "ceo_mint", "Head", bevel=0.01)   # a service plate, off centre
for k in range(3):
    box((cx - 0.15, cy + D / 2 + 0.003, hz + H * 0.62 - k * 0.03), (0.12, 0.006, 0.012), "ceo_seam", "Head")    # vent slots
# the screen face, eyes and brow
box((cx, F - 0.004, hz + H * 0.62), (W * 0.78, 0.02, H * 0.36), "ceo_screen", "Head", bevel=0.03)
for side in (-1, 1):
    ex = cx + side * 0.105
    for k in range(5):                                    # each eye a shallow arc of five dashes
        a = math.radians(-50 + k * 25)
        box((ex + 0.055 * math.sin(a), F - 0.018, hz + H * 0.6 + 0.022 * math.cos(a)),
            (0.03, 0.006, 0.011), "ceo_eye", "Head", rot=(0, a, 0))
box((cx + 0.13, F - 0.018, hz + H * 0.73), (0.11, 0.006, 0.012), "ceo_eye", "Head", rot=(0, math.radians(-14), 0))  # the raised brow
box((cx - 0.12, F - 0.018, hz + H * 0.71), (0.09, 0.006, 0.011), "ceo_eye", "Head", rot=(0, math.radians(6), 0))
# the grin: a wide smile across the lower face, two rows of upright wafer teeth along a gentle curve, the corners up
def smile_y(x):
    return hz + H * 0.255 + 0.045 * (x / 0.24) ** 2


for k in range(12):                                             # the dark mouth behind the teeth
    x = -0.235 + k * 0.0427
    box((cx + x, F - 0.008, smile_y(x)), (0.05, 0.016, 0.105), "ceo_screen", "Head", bevel=0.008)
for row, dz in ((0, 0.024), (1, -0.024)):
    for k in range(9):
        x = -0.192 + k * 0.048
        box((cx + x, F - 0.02, smile_y(x) + dz), (0.043, 0.012, 0.04), f"ceo_wafer{(k + row * 2) % 5}", "Head", bevel=0.005)
for side in (-1, 1):                                            # the corners turning up
    box((cx + side * 0.25, F - 0.012, smile_y(0.25) + 0.035), (0.018, 0.01, 0.05), "ceo_screen", "Head", bevel=0.004)
# chin plate with the cable-bundle grill
box((cx, F + 0.04, hz + 0.02), (0.26, 0.14, 0.1), "ceo_shell", "Head", bevel=0.02)
for k in range(7):
    cyl((cx - 0.09 + k * 0.03, F - 0.01, hz - 0.01), 0.012, 0.11, "ceo_seam", "Head", verts=10)
# cheek panels
for side in (-1, 1):
    box((cx + side * 0.21, F - 0.004, hz + H * 0.2), (0.1, 0.012, 0.045), "ceo_mint", "Head", bevel=0.008)
# ear discs with mint rings
for side in (-1, 1):
    ex = cx + side * (W / 2 + 0.015)
    cyl((ex, cy, hz + H * 0.5), 0.085, 0.05, "ceo_shell", "Head", rot=(0, math.pi / 2, 0), bevel=0.01)
    torus((ex + side * 0.026, cy, hz + H * 0.5), 0.06, 0.012, "ceo_mint", "Head", rot=(0, math.pi / 2, 0))
    cyl((ex + side * 0.028, cy, hz + H * 0.5), 0.035, 0.01, "ceo_seam", "Head", rot=(0, math.pi / 2, 0))
# the red band, its wafer badge, the knot and tails at the back
box((cx, cy, hz + H * 0.88), (W + 0.025, D + 0.025, 0.07), "ceo_red", "Head", bevel=0.02)
cyl((cx, F - 0.02, hz + H * 0.88), 0.035, 0.012, "ceo_wafer3", "Head", rot=(math.pi / 2, 0, 0), verts=24)
box((cx, cy + D / 2 + 0.03, hz + H * 0.88), (0.08, 0.05, 0.08), "ceo_red", "Head", bevel=0.02)
for side in (-1, 1):
    box((cx + side * 0.13, cy + D / 2 + 0.09, hz + H * 0.8), (0.2, 0.012, 0.06), "ceo_red", "Head",
        rot=(0, side * math.radians(25), side * math.radians(30)))
# the lamp tower and the curled quiff on top
top = hz + H
cyl((cx - 0.12, cy, top + 0.03), 0.035, 0.06, "ceo_metal", "Head")
for k, m in enumerate(("ceo_lamp_g", "ceo_lamp_a", "ceo_lamp_r")):
    cyl((cx - 0.12, cy, top + 0.08 + k * 0.05), 0.04, 0.048, m, "Head", bevel=0.006)
tube([Vector((cx + 0.02, cy + 0.12, top - 0.01)), Vector((cx + 0.06, cy, top + 0.13)), Vector((cx + 0.14, cy - 0.12, top + 0.16)),
      Vector((cx + 0.2, cy - 0.16, top + 0.08)), Vector((cx + 0.16, cy - 0.08, top + 0.05))], 0.05, "ceo_metal", "Head")
# the coiled cable neck
for k in range(4):
    torus((neck.x, neck.y, neck.z + 0.01 + k * 0.025), 0.06, 0.014, "ceo_seam", "neck_01")
# shirt, tie, lapels, lanyard and badge on the chest
chest = bone_world("spine_03")
fz = chest.z
fy = chest.y - 0.16
box((chest.x, fy, fz + 0.06), (0.16, 0.02, 0.2), "ceo_shirt", "spine_03")
box((chest.x, fy - 0.012, fz + 0.03), (0.05, 0.012, 0.22), "ceo_red", "spine_03", bevel=0.008)
box((chest.x, fy - 0.014, fz + 0.15), (0.06, 0.012, 0.04), "ceo_red", "spine_03", bevel=0.008)
for side in (-1, 1):
    box((chest.x + side * 0.1, fy - 0.006, fz + 0.04), (0.07, 0.016, 0.24), "ceo_suit", "spine_03",
        rot=(0, side * math.radians(-18), 0), bevel=0.01)
tube([Vector((chest.x - 0.1, fy + 0.04, fz + 0.18)), Vector((chest.x - 0.04, fy - 0.03, fz - 0.05)),
      Vector((chest.x + 0.05, fy - 0.03, fz - 0.15))], 0.006, "ceo_lanyard", "spine_03")
box((chest.x + 0.06, fy - 0.035, fz - 0.19), (0.08, 0.01, 0.055), "ceo_white", "spine_03", bevel=0.005)
# jacket buttons and pocket flaps on the belly
belly = bone_world("spine_01")
for k in range(2):
    cyl((belly.x, belly.y - 0.16, belly.z + 0.02 + k * 0.08), 0.012, 0.01, "ceo_seam", "spine_01", rot=(math.pi / 2, 0, 0), verts=12)
for side in (-1, 1):
    box((belly.x + side * 0.1, belly.y - 0.155, belly.z - 0.04), (0.09, 0.01, 0.018), "ceo_suit", "spine_01", bevel=0.003)
# robot arms: white segments on the upper and lower arm bones, joints, mint pads; shoes on the feet
for s in "lr":
    a, b, c = sh[s] + (el[s] - sh[s]) * 0.36, el[s], bone_world(f"hand_{s}")
    for p0, p1, bone, r in ((a, b, f"upperarm_{s}", 0.088), (b, c, f"lowerarm_{s}", 0.082)):
        mid = (p0 + p1) / 2
        L = (p1 - p0).length
        cyl(mid, r, L * 0.84, "ceo_white", bone, rot=(0, math.pi / 2, 0), verts=28, bevel=0.03)
        cyl(p0 + (p1 - p0) * 0.12, r + 0.006, 0.022, "ceo_mint", bone, rot=(0, math.pi / 2, 0), verts=28)   # a mint band
        cyl(p0 + (p1 - p0) * 0.5, r + 0.003, 0.006, "ceo_seam", bone, rot=(0, math.pi / 2, 0), verts=28)    # a panel seam
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=0.075, location=b)               # the elbow ball
    part(bpy.context.active_object, "ceo_seam", f"lowerarm_{s}")
    cyl(c + (b - c).normalized() * 0.025, 0.07, 0.04, "ceo_seam", f"lowerarm_{s}", rot=(0, math.pi / 2, 0))
    f, bl = bone_world(f"foot_{s}"), bone_world(f"ball_{s}")
    sy = (f.y + bl.y) / 2 - 0.04
    box((f.x, sy + 0.03, 0.06), (0.13, 0.26, 0.1), "ceo_shoe", f"foot_{s}", bevel=0.04)                       # the upper
    cyl((f.x, sy - 0.1, 0.045), 0.066, 0.13, "ceo_shoe", f"foot_{s}", rot=(0, math.pi / 2, 0), verts=24)     # a rounded toe
    box((f.x, sy - 0.02, 0.008), (0.14, 0.36, 0.016), "ceo_seam", f"foot_{s}", bevel=0.006)                  # the sole
    box((f.x, sy + 0.13, 0.03), (0.12, 0.07, 0.04), "ceo_seam", f"foot_{s}", bevel=0.01)                     # the heel
# robot arm detail: elbow rings, mint pads, the wafer watch on the right wrist
for side, sfx in ((-1, "r"), (1, "l")):
    el = bone_world(f"lowerarm_{sfx}")
    wr = bone_world(f"hand_{sfx}")
    cyl(el, 0.06, 0.05, "ceo_seam", f"lowerarm_{sfx}", rot=(0, math.pi / 2, 0))
    box((el.x - side * 0.08, el.y - 0.06, el.z), (0.05, 0.012, 0.03), "ceo_mint", f"upperarm_{sfx}", bevel=0.005)
    if sfx == "r":
        w = wr + (el - wr).normalized() * 0.07
        cyl(w, 0.09, 0.05, "ceo_metal", "lowerarm_r", rot=(0, math.pi / 2, 0))                 # the strap
        cyl((w.x, w.y, w.z + 0.09), 0.062, 0.025, "ceo_metal", "lowerarm_r", verts=32)            # the case, on the back of the wrist
        for k in range(5):                                                                    # its face: a wafer, rainbow sheen
            cyl((w.x, w.y, w.z + 0.104 + k * 0.0004), 0.052 - k * 0.009, 0.004, f"ceo_wafer{k}", "lowerarm_r", verts=32)
    else:
        rb = bone_world("ring_01_l")
        torus((rb.x + 0.02, rb.y, rb.z), 0.018, 0.006, "ceo_metal", "ring_01_l", rot=(0, math.pi / 2, 0))
        cyl((rb.x + 0.02, rb.y, rb.z + 0.024), 0.012, 0.006, "ceo_wafer2", "ring_01_l", verts=16)

# ------------------------------------------------------------------ fix the parts to their bones, join, export

for i, (ob, bone) in enumerate(PARTS):
    bpy.ops.object.select_all(action="DESELECT")
    if ob.type == "CURVE":
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.convert(target="MESH")
        ob = bpy.context.active_object
        PARTS[i] = (ob, bone)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    for md in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    vg = ob.vertex_groups.new(name=bone)
    vg.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
bpy.ops.object.select_all(action="DESELECT")
for ob, _ in PARTS:
    ob.select_set(True)
for ob in CLOTH:
    ob.select_set(True)
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
body.name = "CEO_body"
unweighted = sum(1 for v in body.data.vertices if sum(g.weight for g in v.groups) < 1e-4)
assert unweighted == 0, f"{unweighted} vertices have no bone weight"
bpy.ops.object.shade_smooth()
arm.data.pose_position = "POSE"

os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_skins=True, export_animations=True,
                          export_animation_mode="ACTIONS", export_materials="EXPORT")
xs = [(body.matrix_world @ v.co) for v in body.data.vertices]
print(f"ceo: {len(body.data.polygons)} faces, {len(body.data.materials)} materials, {len(bpy.data.actions)} clips, "
      f"height {max(v.z for v in xs):.2f} m -> {OUT}")
