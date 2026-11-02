"""A cleanroom worker for the 3D fab (docs/FAB-3D.md, step 3), modelled from the turnaround Meta's Muse Image drew
(Character Sheet, staff). Our own model on the CC0 skeleton of Quaternius's Universal Animation Library, so its CC0
clips drive it: the CC0 body lends its hands (gloved) and its bone weights; the coverall, hood, mask, goggles, boots and
badge are ours. The hood trim is one material, `staff_trim`, that the scene recolours by job (blue operators, orange
maintenance, green engineers: our own convention). From the SMT2020 testbed; not a real fab.

    Blender -b --factory-startup -P viz/blender/characters/staff.py -- --out data/fab3d/models/staff.glb
"""

import glob
import math
import os
import sys

import bpy
from mathutils import Vector

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGV[ARGV.index("--out") + 1] if "--out" in ARGV else "data/fab3d/models/staff.glb"
UAL = glob.glob(os.path.expanduser(
    "~/evalzero_work/fab-gym/data/assets/quaternius/universal-animation-library-standard/*/Unreal-Godot/UAL1_Standard.glb"))[0]
KEEP = ["Walk_Loop", "Idle_Loop", "Fixing_Kneeling", "PickUp_Table", "Interact", "Sitting_Enter", "Sitting_Idle_Loop",
        "Sitting_Exit"]
COLOURS = {
    "staff_suit": ((0.95, 0.96, 0.97), 0.0, 0.75, None),
    "staff_fold": ((0.84, 0.86, 0.89), 0.0, 0.8, None),
    "staff_trim": ((0.23, 0.48, 0.84), 0.0, 0.5, None),
    "staff_glove": ((0.62, 0.78, 0.92), 0.0, 0.45, None),
    "staff_tape": ((0.66, 0.86, 0.80), 0.0, 0.5, None),
    "staff_boot": ((0.93, 0.94, 0.95), 0.0, 0.35, None),
    "staff_sole": ((0.70, 0.72, 0.75), 0.0, 0.6, None),
    "staff_goggle": ((0.06, 0.07, 0.09), 0.3, 0.12, None),
    "staff_frame": ((0.30, 0.32, 0.36), 0.2, 0.4, None),
    "staff_mask": ((0.97, 0.97, 0.96), 0.0, 0.85, None),
    "staff_skin": ((0.86, 0.66, 0.52), 0.0, 0.6, None),
    "staff_badge": ((0.16, 0.24, 0.36), 0.2, 0.4, None),
    "staff_badge_lines": ((0.45, 0.75, 0.95), 0.0, 0.3, ((0.45, 0.75, 0.95), 0.6)),
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
    m.diffuse_color = (*base, 1)
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=UAL)
for o in list(bpy.data.objects):
    if o.type == "MESH" and (o.parent is None or o.name.startswith("Icosphere")):   # the library's preview sphere
        bpy.data.objects.remove(o, do_unlink=True)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = next(o for o in bpy.data.objects if o.type == "MESH")
arm.name = "Staff"
for a in list(bpy.data.actions):
    if not any(a.name.startswith(k) for k in KEEP):
        bpy.data.actions.remove(a)


def bw(name, tail=False):
    b = arm.data.bones[name]
    return arm.matrix_world @ (b.tail_local if tail else b.head_local)


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
body.data.materials.append(material("staff_glove"))
for poly in body.data.polygons:
    poly.material_index = 0
d = body.modifiers.new("glove", "DISPLACE")
d.strength = 0.008
d.mid_level = 0.0
bpy.ops.object.modifier_move_to_index(modifier="glove", index=0)
bpy.ops.object.modifier_apply(modifier="glove")

# a texture of soft creases for the coverall, so the cloth reads loose (Blender's own noise; no image files)
creases = bpy.data.textures.new("creases", "CLOUDS")
creases.noise_scale = 0.06
creases.noise_depth = 1

CLOTH, PARTS = [], []


def cloth(ob, mat, bevel=0.0, subdiv=1, folds=0.0):
    ob.data.materials.clear()
    ob.data.materials.append(material(mat))
    if bevel:
        md = ob.modifiers.new("bevel", "BEVEL")
        md.width = bevel
        md.segments = 3
    if subdiv:
        md = ob.modifiers.new("sub", "SUBSURF")
        md.levels = subdiv
    if folds:
        md = ob.modifiers.new("folds", "SUBSURF")
        md.levels = 1
        md = ob.modifiers.new("creases", "DISPLACE")
        md.texture = creases
        md.strength = folds
        md.texture_coords = "GLOBAL"
    CLOTH.append(ob)
    return ob


def part(ob, mat, bone, bevel=0.0):
    ob.data.materials.clear()
    ob.data.materials.append(material(mat))
    if bevel:
        md = ob.modifiers.new("bevel", "BEVEL")
        md.width = bevel
        md.segments = 3
    PARTS.append((ob, bone))
    return ob


WEIGHTED = {}


def tube_between(a, b, r0, r1, mat, verts=24, folds=0.012, bones=None):
    """A loose sleeve or trouser leg from a to b, wider at a. With `bones` [(name, t)], each vertex is weighted along the
    tube between the two bones whose stations t (0 at a, 1 at b) it falls between; otherwise by the body's weights."""
    mid = (a + b) / 2
    dvec = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r0, depth=dvec.length, location=mid, end_fill_type="NOTHING")
    ob = bpy.context.active_object
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(-dvec.normalized())
    bpy.ops.object.transform_apply(rotation=True)
    me = ob.data
    # rings of slack: the tube bulges a little between gathered points, like loose cloth
    for v in me.vertices:
        t = ((v.co @ (-dvec.normalized())) / dvec.length) + 0.5
        bulge = 1.0 + 0.10 * math.sin(t * math.pi * 3) ** 2
        r = Vector((v.co.x, v.co.y, v.co.z)) - (-dvec.normalized()) * (v.co @ (-dvec.normalized()))
        v.co += r * (bulge - 1.0)
    ob = cloth(ob, mat, subdiv=0, folds=folds)
    if bones:
        WEIGHTED[ob.name] = (a.copy(), b.copy(), bones)
    return ob


def weigh_along(ob, a, b, bones):
    axis = b - a
    L2 = axis.length_squared
    vgs = {n: ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n) for n, _ in bones}
    for v in ob.data.vertices:
        t = max(0.0, min(1.0, (v.co - a).dot(axis) / L2))
        w = {}
        for (n0, t0), (n1, t1) in zip(bones, bones[1:]):
            if t0 <= t <= t1:
                u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                w[n0] = w.get(n0, 0.0) + 1.0 - u      # summed: two stations may name the same bone
                w[n1] = w.get(n1, 0.0) + u
                break
        else:
            w[bones[0][0] if t < bones[0][1] else bones[-1][0]] = 1.0
        for n, x in w.items():
            if x > 0:
                vgs[n].add([v.index], x, "REPLACE")


pel, sp3, nk, hd = bw("pelvis"), bw("spine_03"), bw("neck_01"), bw("Head")
sh = {s: bw(f"upperarm_{s}") for s in "lr"}
el = {s: bw(f"lowerarm_{s}") for s in "lr"}
wr = {s: bw(f"hand_{s}") for s in "lr"}
th = {s: bw(f"thigh_{s}") for s in "lr"}
kn = {s: bw(f"calf_{s}") for s in "lr"}
an = {s: bw(f"foot_{s}") for s in "lr"}

# the coverall's body: roomy from the crotch to the shoulders
z0, z1 = pel.z - 0.14, nk.z + 0.03
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, sp3.y + 0.01, (z0 + z1) / 2))
bodyc = bpy.context.active_object
bodyc.scale = (0.5, 0.33, z1 - z0)
bpy.ops.object.transform_apply(scale=True)
for v in bodyc.data.vertices:
    t = (v.co.z - z0) / (z1 - z0)
    v.co.x *= 0.92 + 0.12 * t
    if t > 0.95:
        v.co.x *= 0.62
cloth(bodyc, "staff_suit", bevel=0.06, subdiv=1, folds=0.012)
TORSO = [("pelvis", 0.0), ("pelvis", 0.12), ("spine_01", 0.32), ("spine_02", 0.55), ("spine_03", 0.78), ("spine_03", 1.0)]
WEIGHTED[bodyc.name] = (Vector((0, 0, z0)), Vector((0, 0, z1)), TORSO)
# sleeves: shoulder to wrist, gathered at the cuff
for s in "lr":
    a, b = sh[s] + (el[s] - sh[s]).normalized() * 0.04, wr[s] + (el[s] - wr[s]).normalized() * 0.03
    te = (el[s] - a).length / (b - a).length
    tube_between(a, b, 0.088, 0.072, "staff_suit",
                 bones=[(f"upperarm_{s}", 0.0), (f"upperarm_{s}", te - 0.08), (f"lowerarm_{s}", te + 0.08), (f"lowerarm_{s}", 1.0)])
# legs: hip to the top of the boot, loose
for s in "lr":
    boot_top = kn[s] + (an[s] - kn[s]) * 0.15
    a = th[s] + Vector((0, 0, 0.08))
    tk = (kn[s] - a).length / (boot_top - a).length
    tube_between(a, boot_top, 0.115, 0.1, "staff_suit",
                 bones=[("pelvis", 0.0), (f"thigh_{s}", 0.15), (f"thigh_{s}", tk - 0.08), (f"calf_{s}", tk + 0.08), (f"calf_{s}", 1.0)])
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, pel.y, pel.z - 0.08))
seat = bpy.context.active_object
seat.scale = (0.34, 0.28, 0.2)
cloth(seat, "staff_suit", bevel=0.06, subdiv=1, folds=0.01)
WEIGHTED[seat.name] = (Vector((0, 0, z0 - 0.2)), Vector((0, 0, z0 + 0.2)), [("pelvis", 0.0), ("pelvis", 1.0)])
# a zip line and the waist seam
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, sp3.y - 0.172, (z0 + z1) / 2 + 0.05))
z = bpy.context.active_object
z.scale = (0.006, 0.006, (z1 - z0) * 0.8)
cloth(z, "staff_fold", subdiv=0)
WEIGHTED[z.name] = (Vector((0, 0, z0)), Vector((0, 0, z1)), TORSO)

# skin the cloth with the body's weights, then drop the donor
for ob in CLOTH:
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    for md in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if ob.name in WEIGHTED:
        weigh_along(ob, *WEIGHTED[ob.name])
        continue
    for g in donor.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    dt = ob.modifiers.new("weights", "DATA_TRANSFER")
    dt.object = donor
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    bpy.ops.object.modifier_apply(modifier="weights")
    if False:
        for g in list(ob.vertex_groups):
            if not g.name.startswith(("spine", "pelvis")):
                ob.vertex_groups.remove(g)
        top = ob.vertex_groups.get("spine_03") or ob.vertex_groups.new(name="spine_03")
        for v in ob.data.vertices:                  # a vertex left with no weight would stay behind: give it the chest
            if sum(g.weight for g in v.groups) < 0.05:
                top.add([v.index], 1.0, "REPLACE")
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
bpy.data.objects.remove(donor, do_unlink=True)

# ------------------------------------------------------------------ rigid parts on their bones


def add_box(c, size, mat, bone, bevel=0.0, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rot)
    ob = bpy.context.active_object
    ob.scale = size
    return part(ob, mat, bone, bevel)


def add_cyl(c, r, depth, mat, bone, rot=(0, 0, 0), verts=24, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=c, rotation=rot)
    return part(bpy.context.active_object, mat, bone, bevel)


def add_torus(c, R, r, mat, bone, rot=(0, 0, 0), scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, location=c, rotation=rot, major_segments=32, minor_segments=8)
    ob = bpy.context.active_object
    ob.scale = scale
    return part(ob, mat, bone)


# the hood: a soft dome over the head with a face opening; goggles, mask and a strip of skin between them
hc = hd + Vector((0, 0.01, 0.1))
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.15, location=hc)
hood = bpy.context.active_object
hood.scale = (0.98, 1.0, 1.08)
part(hood, "staff_suit", "Head")
fy = hc.y - 0.135
add_box((hc.x, fy + 0.015, hc.z - 0.005), (0.15, 0.04, 0.17), "staff_skin", "Head", bevel=0.03)          # the face in the opening
add_box((hc.x, fy - 0.012, hc.z + 0.025), (0.17, 0.035, 0.06), "staff_goggle", "Head", bevel=0.02)         # goggles
add_box((hc.x, fy - 0.014, hc.z + 0.025), (0.18, 0.025, 0.07), "staff_frame", "Head", bevel=0.02)
add_box((hc.x, fy - 0.006, hc.z - 0.055), (0.14, 0.035, 0.08), "staff_mask", "Head", bevel=0.025)        # mask
add_torus((hc.x, fy - 0.002, hc.z - 0.005), 0.098, 0.009, "staff_trim", "Head", rot=(math.pi / 2, 0, 0), scale=(0.95, 1, 1.3))  # trim
add_torus((nk.x, nk.y, nk.z + 0.01), 0.095, 0.01, "staff_trim", "neck_01", scale=(1.15, 1.0, 1.0))      # the collar line
# a rounded cap over each shoulder joint, riding the upper arm
for s in "lr":
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=0.098, location=sh[s])
    part(bpy.context.active_object, "staff_suit", f"upperarm_{s}")
# taped cuffs
for s in "lr":
    c = wr[s] + (el[s] - wr[s]).normalized() * 0.03
    add_cyl(c, 0.068, 0.05, "staff_tape", f"lowerarm_{s}", rot=(0, math.pi / 2, 0))
# boots: a shaft on the calf and a foot on the foot bone
for s in "lr":
    top = kn[s] + (an[s] - kn[s]) * 0.15
    mid = (top + an[s]) / 2
    add_cyl((an[s].x, an[s].y, (top.z + 0.06) / 2), 0.085, top.z - 0.06, "staff_boot", f"calf_{s}", bevel=0.01)
    bl = bw(f"ball_{s}")
    add_box((an[s].x, (an[s].y + bl.y) / 2 - 0.03, 0.06), (0.14, 0.32, 0.12), "staff_boot", f"foot_{s}", bevel=0.045)
    add_box((an[s].x, (an[s].y + bl.y) / 2 - 0.03, 0.01), (0.15, 0.34, 0.02), "staff_sole", f"foot_{s}", bevel=0.008)
# the badge on the chest
add_box((sp3.x + 0.1, sp3.y - 0.175, sp3.z + 0.05), (0.075, 0.01, 0.055), "staff_badge", "spine_03", bevel=0.005)
for k in range(3):
    add_box((sp3.x + 0.085 + k * 0.012, sp3.y - 0.181, sp3.z + 0.05), (0.004, 0.004, 0.035), "staff_badge_lines", "spine_03")

for i, (ob, bone) in enumerate(PARTS):
    bpy.ops.object.select_all(action="DESELECT")
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
body.name = "Staff_body"
unweighted = sum(1 for v in body.data.vertices if sum(g.weight for g in v.groups) < 1e-4)
assert unweighted == 0, f"{unweighted} vertices have no bone weight"
bpy.ops.object.shade_smooth()
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_skins=True, export_animations=True,
                          export_animation_mode="ACTIONS", export_materials="EXPORT")
zs = [(body.matrix_world @ v.co).z for v in body.data.vertices]
print(f"staff: {len(body.data.polygons)} faces, {len(body.data.materials)} materials, {len(bpy.data.actions)} clips, "
      f"height {max(zs):.2f} m -> {OUT}")
