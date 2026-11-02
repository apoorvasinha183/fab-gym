"""Render a character glTF as a turnaround (front, side, back) in one of its clips, to compare with the character
sheet. From the SMT2020 testbed; not a real fab.

    Blender -b --factory-startup -P viz/blender/characters/turn.py -- --glb data/fab3d/models/ceo.glb --clip Idle_Loop --out data/fab3d/ceo-turn.png
"""

import math
import os
import sys

import bpy
import mathutils

A = sys.argv[sys.argv.index("--") + 1:]
GLB = A[A.index("--glb") + 1]
CLIP = A[A.index("--clip") + 1] if "--clip" in A else "Idle_Loop"
OUT = A[A.index("--out") + 1]
FRAME = int(A[A.index("--frame") + 1]) if "--frame" in A else 12

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=GLB)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
act = next((a for a in bpy.data.actions if a.name.startswith(CLIP)), None)
if act:
    arm.animation_data_create()
    arm.animation_data.action = act
    try:
        arm.animation_data.action_slot = act.slots[0]
    except (AttributeError, IndexError):
        pass
sc.frame_set(FRAME)
bpy.context.view_layer.update()

bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
fl = bpy.context.active_object
m = bpy.data.materials.new("floor")
m.use_nodes = True
p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
p.inputs["Base Color"].default_value = (0.82, 0.84, 0.87, 1)
fl.data.materials.append(m)
bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
s = bpy.context.active_object
s.data.energy = 2.2
s.rotation_euler = (math.radians(40), math.radians(10), math.radians(-30))
bpy.ops.object.light_add(type="AREA", location=(0, -4, 3))
f = bpy.context.active_object
f.data.energy = 250
f.data.size = 4
f.rotation_euler = (math.radians(70), 0, 0)
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.93, 0.94, 0.96, 1)
bg.inputs["Strength"].default_value = 0.35
engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = next((e for e in engines if "EEVEE" in e), engines[0])
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass
sc.render.resolution_x, sc.render.resolution_y = 600, 900
bpy.ops.object.camera_add()
cam = bpy.context.active_object
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2.8
sc.camera = cam
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
paths = []
for name, ang in (("front", 0), ("side", 90), ("back", 180)):
    a = math.radians(ang)
    cam.location = (8 * math.sin(a), -8 * math.cos(a), 1.2)
    look = mathutils.Vector((0, 0, 1.2)) - cam.location
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    p = OUT.replace(".png", f"-{name}.png")
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    paths.append(p)
print("wrote", " ".join(paths))
