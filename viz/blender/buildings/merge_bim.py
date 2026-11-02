"""The fab's building for the 3D fab (docs/FAB-3D.md): the design-development IFC's glTF (1,004 meshes) joined into one
mesh per material, so the scene draws it in a handful of calls; the roof and the filter ceiling stay their own meshes so
the scene can hide them when the visitor flies above. From the SMT2020 testbed; a layout of our own design; not a real fab.

    Blender -b --factory-startup -P viz/blender/buildings/merge_bim.py -- IN.glb OUT.glb [CAMPUS.json]

With the campus file, the entrance's openings (docs/FAB-3D.md, F9: the ground door into the lift, the gowning room's
two doors, the lift shaft through the waffle slab and the raised floor) are cut out of the walls and slabs they meet
before the merge.
"""
import json
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
src, out = args[:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]


def world_box(o):
    from mathutils import Vector
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return [min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts),
            max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)]


cut = 0
if len(args) > 2:
    campus = json.load(open(args[2]))
    openings = campus["entrance"]["openings"] + [{"name": "bridge doorway", "box": b}
                                                 for b in campus.get("exterior", {}).get("bridge", {}).get("openings", [])]
    cuttable = ("bim_wall", "bim_slab_floor", "bim_covering_flooring")
    for op in openings:
        b = op["box"]
        # a little past the wall's faces, so the hole goes clean through
        lo = [b[0] - 0.05, b[1] - 0.05, b[2] - 0.01]
        hi = [b[3] + 0.05, b[4] + 0.05, b[5]]
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=[(lo[i] + hi[i]) / 2 for i in range(3)])
        cutter = bpy.context.active_object
        cutter.scale = [hi[i] - lo[i] for i in range(3)]
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        for o in meshes:
            if not o.data.materials or o.data.materials[0].name not in cuttable:
                continue
            w = world_box(o)
            if all(lo[i] < w[i + 3] and w[i] < hi[i] for i in range(3)):
                mod = o.modifiers.new("opening", "BOOLEAN")
                mod.operation = "DIFFERENCE"
                mod.solver = "EXACT"
                mod.object = cutter
                bpy.ops.object.select_all(action="DESELECT")
                o.select_set(True)
                bpy.context.view_layer.objects.active = o
                bpy.ops.object.modifier_apply(modifier=mod.name)
                cut += 1
        bpy.data.objects.remove(cutter, do_unlink=True)
# the fabs' outer walls get their own material, so the outside can be clad without cladding the cleanroom's walls
if len(args) > 2:
    fabs = [f for f in json.load(open(args[2]))["fabs"] if f[5] == "fab"]
    outer = None
    for o in meshes:
        if not o.data.materials or o.data.materials[0].name != "bim_wall":
            continue
        w = world_box(o)
        long_y, long_x = w[4] - w[1] > 50, w[3] - w[0] > 50
        on_edge = any((long_y and (abs(w[0] - f[0]) < 0.5 or abs(w[3] - f[1]) < 0.5))
                      or (long_x and (abs(w[1] - f[2]) < 0.5 or abs(w[4] - f[3]) < 0.5)) for f in fabs)
        if on_edge:
            # only the faces that look out of the building are clad; the faces inside stay the cleanroom's wall
            if outer is None:
                outer = o.data.materials[0].copy()
                outer.name = "bim_wall_outer"
            o.data.materials.append(outer)
            f = next(f for f in fabs if f[0] - 0.5 <= (w[0] + w[3]) / 2 <= f[1] + 0.5)
            cx, cy = (f[0] + f[1]) / 2, (f[2] + f[3]) / 2
            mw = o.matrix_world
            for poly in o.data.polygons:
                c = mw @ poly.center
                n = (mw.to_3x3() @ poly.normal).normalized()
                if abs(n.z) < 0.5 and n.x * (c.x - cx) + n.y * (c.y - cy) > 0:
                    poly.material_index = len(o.data.materials) - 1
# slabs, raised floor, filter ceiling and roof end exactly on the walls' outside faces; drawn together the two fight
# for the same pixels (bands that flicker along the walls), so their edges move 6 cm inside the walls
if len(args) > 2:
    from mathutils import Vector
    edges_x = [v for f in fabs for v in (f[0], f[1])]
    edges_y = [v for f in fabs for v in (f[2], f[3])]
    flat = ("bim_slab_floor", "bim_covering_flooring", "bim_covering_ceiling", "bim_slab_roof")
    moved = 0
    for o in meshes:
        if not o.data.materials or o.data.materials[0].name not in flat:
            continue
        mw, inv = o.matrix_world, o.matrix_world.inverted()
        for v in o.data.vertices:
            p = mw @ v.co
            q = p.copy()
            for e in edges_x:
                if abs(p.x - e) < 0.03:
                    q.x = e + (0.06 if any(abs(e - f[0]) < 0.03 for f in fabs) else -0.06)
            for e in edges_y:
                if abs(p.y - e) < 0.03:
                    q.y = e + (0.06 if any(abs(e - f[2]) < 0.03 for f in fabs) else -0.06)
            if q != p:
                v.co = inv @ q
                moved += 1
    print("slab edges moved in:", moved)
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
print("merged", len(meshes), "meshes into", len(by_mat), "with", cut, "openings cut ->", out)
