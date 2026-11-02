"""The fab's building for the 3D fab (docs/FAB-3D.md): the design-development IFC's glTF (1,004 meshes) joined into one
mesh per material, so the scene draws it in a handful of calls; the roof and the filter ceiling stay their own meshes so
the scene can hide them when the visitor flies above. From the SMT2020 testbed; a layout of our own design; not a real fab.

    Blender -b --factory-startup -P viz/blender/buildings/merge_bim.py -- IN.glb OUT.glb
"""
import sys

import bpy

src, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
by_mat = {}
for o in meshes:
    m = o.data.materials[0].name if o.data.materials else "none"
    by_mat.setdefault(m, []).append(o)
for m, obs in by_mat.items():
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(obs) > 1:
        bpy.ops.object.join()
    j = bpy.context.active_object
    j.name = j.data.name = f"building_{m}"
    j.parent = None
for o in list(bpy.data.objects):
    if o.type != "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_yup=True, export_apply=True)
print("merged", len(meshes), "meshes into", len(by_mat), "->", out)
