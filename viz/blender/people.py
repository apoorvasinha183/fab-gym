"""Build the visitor, a person asset for the film "A Walk Through the Fab": people.blend.

    Blender -b -P viz/blender/people.py -- PEOPLE_DIR OUT.blend [--stills DIR]

PEOPLE_DIR is the staged folder of viz/blender/push_assets.sh (assets/people on the render machine).
The body is Quaternius's Universal Base Characters man and the clips are the Universal Animation
Library's (both CC0, docs/ASSETS.md); the two share one skeleton. Over the body we make his clothes
from the body's own surface, pushed out a little and cut by which bone moves each part, so they bend
with him:
  street: shirt, trousers, shoes and the kit's parted hair;
  suit:   coverall, hood, mask, goggles, nitrile gloves and booties (a cleanroom gown of our own).
visitor.py shows one outfit or the other. The walk clip's stride is measured here, so the film can
play the walk by distance walked and the planted foot stays put.

Collection "visitor": the rig "visitor rig" (faces -y, stands at the origin), the body, eyes, brows
and each garment (custom property "garment" and "outfit" on it). Every clip is kept with a fake user.
With --stills, renders him in each outfit, standing and mid-stride, for a check by eye.
"""

import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bkit import collection, principled  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1 :]
PEOPLE, OUT = Path(argv[0]), Path(argv[1])
STILLS = Path(argv[argv.index("--stills") + 1]) if "--stills" in argv else None
FPS = 24

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS


def imp(path):
    before, acts = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before], [a for a in bpy.data.actions if a not in acts]


# ------------------------------------------------------------------------- body and clips
body_obs, _ = imp(PEOPLE / "Superhero_Male_FullBody.gltf")
rig = [o for o in body_obs if o.type == "ARMATURE"][0]
rig.name = rig.data.name = "visitor rig"
body = [o for o in body_obs if o.type == "MESH" and o.name.startswith("SuperHero")][0]
eyes = [o for o in body_obs if o.type == "MESH" and o.name.startswith("Eyes")][0]
brows = [o for o in body_obs if o.type == "MESH" and o.name.startswith("Eyebrows")][0]
for o in body_obs:
    if o not in (rig, body, eyes, brows):
        bpy.data.objects.remove(o)
body.name, eyes.name, brows.name = "visitor body", "visitor eyes", "visitor brows"

ual_obs, clips = imp(PEOPLE / "ual.glb")
for o in ual_obs:
    bpy.data.objects.remove(o)
for a in clips:
    a.use_fake_user = True
NEEDED = ("Walk_Loop", "Idle_Loop", "Interact", "Sitting_Enter", "Sitting_Idle_Loop", "Sitting_Exit")
for n in NEEDED:
    assert n in bpy.data.actions, n

# the kit's parted hair, rigged to the head bone: bound to our rig
hair_obs, _ = imp(PEOPLE / "Hair_SimpleParted.gltf")
hair = [o for o in hair_obs if o.type == "MESH"][0]
mw = hair.matrix_world.copy()
for o in hair_obs:
    if o is not hair:
        bpy.data.objects.remove(o)
hair.parent = rig
hair.matrix_world = mw
for md in list(hair.modifiers):
    hair.modifiers.remove(md)
if "Head" not in hair.vertex_groups:
    vg = hair.vertex_groups.new(name="Head")
    vg.add(range(len(hair.data.vertices)), 1.0, "REPLACE")
hm = hair.modifiers.new("rig", "ARMATURE")
hm.object = rig
hair.name = "visitor hair"

# ------------------------------------------------------------------------- where his face is
ew = [eyes.matrix_world @ v.co for v in eyes.data.vertices]
EYE_Z = sum(w.z for w in ew) / len(ew)
EYE_Y = min(w.y for w in ew)
groups = {g.index: g.name for g in body.vertex_groups}


def dominant(v):
    best = max(v.groups, key=lambda g: g.weight, default=None)
    return groups.get(best.group) if best else None


bw = body.matrix_world
head_vs = [bw @ v.co for v in body.data.vertices if dominant(v) == "Head"]
HEAD_CY = sum(w.y for w in head_vs) / len(head_vs)
HEAD_TOP = max(w.z for w in head_vs)


def face(p, lo, hi, half):
    """In front of the head, between heights lo and hi (from the eyes), within half a width of the middle."""
    return p.y < HEAD_CY - 0.03 and EYE_Z + lo <= p.z <= EYE_Z + hi and abs(p.x) <= half


TRUNK = {"pelvis", "spine_01", "spine_02", "spine_03", "clavicle_l", "clavicle_r"}
ARMS = {"upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r"}
LEGS = {"thigh_l", "thigh_r", "calf_l", "calf_r"}
FEET = {"foot_l", "foot_r", "ball_l", "ball_r"}
HAND = {b for b in groups.values() if b.startswith(("hand_", "index_", "middle_", "ring_", "pinky_", "thumb_"))}
OPENING = (-0.125, 0.04, 0.085)  # the hood's face opening, which the mask and goggles fill

WRIST = 0.64  # |x| in the rest pose past which a forearm is the wrist, under a glove's cuff

# name: (outfit, keep(bone, point), push out m, smoothing passes, colour as seen, roughness, extra material
# settings). Smoothing takes the body's muscle out of the cloth; the push puts the cloth back outside him.
# Edges overlap (the hood over the collar, the booties and gloves over the cuffs), so no skin shows between.
GARMENTS = {
    "shirt": ("street", lambda b, p: b in (TRUNK - {"pelvis"}) | ARMS or (b == "neck_01" and p.z < 1.50), 0.016, 12, "#7d8ea3", 0.8, {"sheen": 0.3}),
    "trousers": ("street", lambda b, p: (b in LEGS or b == "pelvis") and p.z > 0.09, 0.02, 12, "#3a3f47", 0.75, {"sheen": 0.2}),
    "shoes": ("street", lambda b, p: b in FEET or (b in LEGS and p.z <= 0.13), 0.028, 16, "#2f2823", 0.4, {"coat": 0.3}),
    "coverall": ("suit", lambda b, p: (b in TRUNK | ARMS | LEGS or b == "neck_01") and p.z > 0.16 and abs(p.x) < WRIST + 0.02, 0.03, 14, "#eef1f4", 0.85, {"sheen": 0.4}),
    "hood": ("suit", lambda b, p: (b == "Head" or (b == "neck_01" and p.z >= 1.42) or (b == "spine_03" and p.z >= 1.40 and abs(p.x) < 0.14))
             and not face(p, *OPENING), 0.036, 10, "#f3f5f7", 0.85, {"sheen": 0.4}),
    "mask": ("suit", lambda b, p: b in ("Head", "neck_01") and face(p, OPENING[0], -0.028, OPENING[2] + 0.01), 0.026, 6, "#d9e7f0", 0.9, {}),
    "goggles": ("suit", lambda b, p: b == "Head" and face(p, -0.034, OPENING[1] + 0.006, OPENING[2] + 0.01), 0.03, 4, "#262f38", 0.06, {"coat": 1.0}),
    "gloves": ("suit", lambda b, p: b in HAND or (b in ARMS and abs(p.x) >= WRIST - 0.05), 0.008, 3, "#6b7fd6", 0.35, {}),
    "booties": ("suit", lambda b, p: b in FEET or (b in LEGS and p.z <= 0.3), 0.034, 10, "#f1f3f5", 0.85, {"sheen": 0.3}),
}

col = collection("visitor")
for o in (rig, body, eyes, brows, hair):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    col.objects.link(o)


# the cloth wraps around this twin of him; the body itself loses the skin each outfit covers
proxy = body.copy()
proxy.name = "visitor body for cloth"
# in the render (else it is not posed) but seen by nothing: no camera ray, shadow or reflection
for k in ("visible_camera", "visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
    setattr(proxy, k, False)
proxy["cloth_target"] = True
col.objects.link(proxy)
COVERED = {"street": set(), "suit": set()}


def garment(name, outfit, keep, push, passes, colour, rough, extra):
    me = body.data.copy()
    me.name = "visitor " + name
    ob = bpy.data.objects.new("visitor " + name, me)
    col.objects.link(ob)
    ob.parent = rig
    ob.matrix_world = body.matrix_world
    for g in body.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    # vertex groups come with the mesh's own weights (stored on the mesh), so the names are enough
    bm = bmesh.new()
    bm.from_mesh(me)
    dl = bm.verts.layers.deform.verify()
    gone = []
    for v in bm.verts:
        w = v[dl]
        b = groups.get(max(w.items(), key=lambda kv: kv[1])[0]) if w else None
        if not keep(b, bw @ v.co):
            gone.append(v)
        else:
            COVERED[outfit].add(v.index)
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    bm.verts.index_update()
    bm.verts.ensure_lookup_table()
    # how far each vertex is from the garment's edge, in rings: the edge is held, the inside smoothed
    ring = {v.index: 0 for v in bm.verts if any(e.is_boundary for e in v.link_edges) or not v.link_faces}
    front = list(ring)
    for d in (1, 2, 3):
        nxt = []
        bm.verts.ensure_lookup_table()
        for i in front:
            for e in bm.verts[i].link_edges:
                j = e.other_vert(bm.verts[i]).index
                if j not in ring:
                    ring[j] = d
                    nxt.append(j)
        front = nxt
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(principled("visitor " + name, colour, rough=rough, **extra))
    for p in me.polygons:
        p.use_smooth = True
    arm = ob.modifiers.new("rig", "ARMATURE")
    arm.object = rig
    d = ob.modifiers.new("loose", "DISPLACE")
    d.strength, d.mid_level, d.direction = push, 0.0, "NORMAL"
    inner = ob.vertex_groups.new(name="inside")
    for i in range(len(me.vertices)):
        inner.add([i], {0: 0.0, 1: 0.3, 2: 0.7}.get(ring.get(i, 9), 1.0), "REPLACE")
    sm = ob.modifiers.new("cloth", "SMOOTH")  # plain averaging, stable on small pieces; the edge held
    sm.factor, sm.iterations, sm.vertex_group = 0.6, passes, inner.name
    # where smoothing took the cloth inside a bulge of him, it goes back over it, as cloth drapes
    sw = ob.modifiers.new("over him", "SHRINKWRAP")
    sw.target, sw.wrap_method, sw.wrap_mode, sw.offset = proxy, "NEAREST_SURFACEPOINT", "OUTSIDE_SURFACE", push * 0.5
    ob["garment"], ob["outfit"] = name, outfit
    return ob


GOBS = {n: garment(n, *spec) for n, spec in GARMENTS.items()}
hair["garment"], hair["outfit"] = "hair", "street"
hair.data.materials.clear()
hair.data.materials.append(principled("visitor hair", "#1d1713", rough=0.5, sheen=0.3))
for n, ob in GOBS.items():
    assert len(ob.data.vertices) > 30, (n, len(ob.data.vertices))

# the skin under each outfit, less a ring at its edge so the garments' edges overlap living skin
nbr = {v.index: set() for v in body.data.vertices}
for e in body.data.edges:
    a, b = e.vertices
    nbr[a].add(b)
    nbr[b].add(a)
for outfit, cov in COVERED.items():
    inner = {i for i in cov if nbr[i] <= cov}
    vg = body.vertex_groups.new(name="under " + outfit)
    vg.add(sorted(inner), 1.0, "REPLACE")
    mk = body.modifiers.new("skin under " + outfit, "MASK")
    mk.vertex_group, mk.invert_vertex_group = vg.name, True
    mk.show_render = mk.show_viewport = outfit == "street"
    body.modifiers.move(len(body.modifiers) - 1, 0)
brows["hidden_in"] = "suit"  # under the hood

# ------------------------------------------------------------------------- the walk's stride, measured
walk = bpy.data.actions["Walk_Loop"]
ad = rig.animation_data or rig.animation_data_create()
ad.action = walk
ad.action_slot = walk.slots[0]
f0, f1 = int(walk.frame_range[0]), int(walk.frame_range[1])
balls = {"l": [], "r": []}
pel = []
for f in range(f0, f1 + 1):
    scene.frame_set(f)
    for s in "lr":
        balls[s].append(rig.pose.bones["ball_" + s].head.copy())
    pel.append(rig.pose.bones["pelvis"].head.copy())
speeds = []
for s in "lr":
    zs = [p.z for p in balls[s]]
    lo = min(zs)
    for a, b in zip(balls[s], balls[s][1:]):
        if a.z <= lo + 0.012 and b.z <= lo + 0.012:
            speeds.append((b.y - a.y) * FPS)  # a planted foot slides back (+y) as he walks forward (-y)
v_anim = sum(speeds) / len(speeds)
cycle = (f1 - f0) / FPS
rig["walk_speed"] = v_anim
rig["walk_cycle_s"] = cycle
rig["walk_m_per_cycle"] = v_anim * cycle
rig["walk_pelvis_drift"] = (pel[-1] - pel[0]).length
rig["foot_floor"] = min(min(p.z for p in balls["l"]), min(p.z for p in balls["r"]))
rig["eye"] = EYE_Z
rig["height"] = HEAD_TOP
ad.action = None
for b in rig.pose.bones:
    b.matrix_basis.identity()
print("walk", round(v_anim, 3), "m/s, cycle", round(cycle, 3), "s,", round(v_anim * cycle, 3), "m; drift", round(rig["walk_pelvis_drift"], 3),
      "eye", round(EYE_Z, 3), "height", round(HEAD_TOP, 3))

bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT), compress=True)

# ------------------------------------------------------------------------- stills, for a look by eye
if STILLS:
    STILLS.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 900, 900
    scene.view_settings.view_transform = "AgX"
    w = bpy.data.worlds.new("w")
    scene.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.57, 0.6, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    fl = bpy.data.objects.new("floor", bpy.data.meshes.new("floor"))
    fl.data.from_pydata([(-3, -3, 0), (3, -3, 0), (3, 3, 0), (-3, 3, 0)], [], [(0, 1, 2, 3)])
    fl.data.materials.append(principled("floor", "#9ea3a8", rough=0.6))
    scene.collection.objects.link(fl)
    key = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
    key.data.energy, key.data.size = 900, 2.0
    key.location = (-2.0, -2.5, 3.2)
    key.rotation_euler = (math.radians(50), 0, math.radians(-38))
    scene.collection.objects.link(key)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 50
    scene.collection.objects.link(cam)
    scene.camera = cam
    for o in GOBS.values():
        o.hide_render = False
    for outfit in ("street", "suit"):
        for o in list(GOBS.values()) + [hair]:
            o.hide_render = o["outfit"] != outfit
        for k in ("street", "suit"):
            body.modifiers["skin under " + k].show_render = k == outfit
        brows.hide_render = outfit == "suit"
        for pose, act, f in (("stand", "Idle_Loop", 10), ("stride", "Walk_Loop", 8)):
            ad.action = bpy.data.actions[act]
            ad.action_slot = ad.action.slots[0]
            scene.frame_set(f)
            for view, (x, y) in (("front", (1.4, -3.4)), ("side", (3.6, -0.3))):
                cam.location = (x, y, 1.25)
                d = Vector((0, 0, 0.95)) - cam.location
                cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
                scene.render.filepath = str(STILLS / f"visitor-{outfit}-{pose}-{view}.png")
                bpy.ops.render.render(write_still=True)
    print("stills", STILLS)
