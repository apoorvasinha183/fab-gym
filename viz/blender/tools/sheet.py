"""A contact sheet of the 3D fab's models (docs/FAB-3D.md, step 2): each model rendered on its own, then tiled by
ffmpeg, for the founder to look at before they go into Godot. From the SMT2020 testbed; not a real fab.

    Blender -b -P viz/blender/tools/sheet.py -- --models data/fab3d/models --out data/fab3d/sheet --name scanner
"""

import math
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODELS = argv[argv.index("--models") + 1]
OUT = argv[argv.index("--out") + 1]
NAME = argv[argv.index("--name") + 1]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, f"{NAME}.glb"))
obs = [o for o in bpy.data.objects if o.type == "MESH"]
pts = [o.matrix_world @ v.co for o in obs for v in o.data.vertices]
lo = [min(p[i] for p in pts) for i in range(3)]
hi = [max(p[i] for p in pts) for i in range(3)]
cx, cy, cz = [(a + b) / 2 for a, b in zip(lo, hi)]
size = max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

bpy.ops.mesh.primitive_plane_add(size=size * 8, location=(cx, cy, 0))
floor = bpy.context.active_object
m = bpy.data.materials.new("floor")
m.use_nodes = True
p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
p.inputs["Base Color"].default_value = (0.36, 0.38, 0.41, 1)
p.inputs["Roughness"].default_value = 0.5
floor.data.materials.append(m)

bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
sun = bpy.context.active_object
sun.data.energy = 2.2
sun.rotation_euler = (math.radians(48), math.radians(8), math.radians(-35))
bpy.ops.object.light_add(type="AREA", location=(cx - size, cy - size * 1.5, size * 1.6))
fill = bpy.context.active_object
fill.data.energy = 120 * size * size
fill.data.size = size
fill.rotation_euler = (math.radians(50), 0, math.radians(-30))

dist = size * 1.55
bpy.ops.object.camera_add(location=(cx - dist * 0.55, cy - dist * 0.95, cz + dist * 0.62))
cam = bpy.context.active_object
direction = (bpy.data.objects[obs[0].name].matrix_world.translation * 0)  # placeholder
import mathutils  # noqa: E402
look = mathutils.Vector((cx, cy, cz * 0.8)) - cam.location
cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
cam.data.lens = 35
sc.camera = cam
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.16, 0.18, 0.22, 1)
bg.inputs["Strength"].default_value = 0.6
engines = [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = next((e for e in engines if "EEVEE" in e), engines[0])
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass
sc.render.resolution_x, sc.render.resolution_y = 640, 480
os.makedirs(OUT, exist_ok=True)
sc.render.filepath = os.path.join(OUT, f"{NAME}.png")
bpy.ops.render.render(write_still=True)
print("wrote", sc.render.filepath)
