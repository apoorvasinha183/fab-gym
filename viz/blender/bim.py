"""The faithful BIM in Blender (docs/BIM-FAITHFUL.md, "Into Blender"): reads the GLB that viz/bim/gltf.py --all
writes, with our own reader (Blender's importer makes one object per instance, which does not scale to the 226,506
repeats), and builds the scene: one object per element with its properties, each repeat as one point cloud instanced
by Geometry Nodes, collections by building, storey and trade, materials by name, and the visitor film's tool models
placed in each tool's IFC box as dressing outside the IFC.

    Blender -b --factory-startup -P viz/blender/bim.py -- GLB SCENE MODELS OUT [--stills | --still NAME[,NAME]]
        [--res 1920x1080] [--samples 32]

Writes OUT/fab-bim.blend, OUT/report.json (what was built, read back from Blender's data) and OUT/<still>.png.
A gigafab-style layout of our own design on the SMT2020 model; not a real fab. NOT FOR CONSTRUCTION.
"""

import json
import math
import re
import struct
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, SCENE, MODELS, OUT = (Path(x) for x in argv[:4])


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


OUT.mkdir(parents=True, exist_ok=True)
RES = [int(v) for v in opt("--res", "1920x1080").split("x")]
SAMPLES = int(opt("--samples", "32"))
STILL_NAMES = ["campus", "cutaway", "subfab", "bay09", "stair", "gowning"]
STILLS = STILL_NAMES if "--stills" in argv else (opt("--still").split(",") if opt("--still") else [])
TRUTH = "On the SMT2020 model. A layout of our own design. Not a real fab."
S = json.loads(SCENE.read_text())
M = json.loads(MODELS.read_text())

# trades by IFC class (docs/BIM-FAITHFUL.md)
TRADE = {
    "Architecture": {"IfcWall", "IfcDoor", "IfcCovering", "IfcStair", "IfcStairFlight", "IfcRailing", "IfcFurniture",
                     "IfcBuildingElementPart"},
    "Structure": {"IfcColumn", "IfcBeam", "IfcSlab", "IfcFooting", "IfcMember", "IfcPlate", "IfcReinforcingBar",
                  "IfcMechanicalFastener"},
    "Mechanical": {"IfcDuctSegment", "IfcAirTerminal", "IfcFan", "IfcFilter", "IfcChiller", "IfcUnitaryEquipment"},
    "Plumbing": {"IfcPipeSegment", "IfcValve", "IfcSanitaryTerminal", "IfcWasteTerminal"},
    "Fire": {"IfcFireSuppressionTerminal", "IfcAlarm", "IfcSensor"},
    "Electrical": {"IfcCableCarrierSegment", "IfcElectricDistributionBoard", "IfcTransformer", "IfcElectricGenerator",
                   "IfcLightFixture", "IfcTransportElement"},
}
CLASS_TRADE = {c: t for t, cs in TRADE.items() for c in cs}

# looks by material name: (metallic, roughness, emission strength, alpha)
TINT = {"concrete": (0.46, 0.45, 0.42), "imp_panel": (0.52, 0.57, 0.63), "gypsum": (0.78, 0.77, 0.73), "rf_tile": (0.70, 0.73, 0.76),
        "cleanroom_panel": (0.86, 0.88, 0.90), "steel": (0.30, 0.34, 0.40), "duct_coated": (0.18, 0.35, 0.50),
        "pipe_plastic": (0.75, 0.80, 0.86), "galvanised": (0.62, 0.65, 0.68)}
LOOK = {"concrete": (0.0, 0.85, 0, 1), "steel": (0.6, 0.45, 0, 1), "galvanised": (0.8, 0.4, 0, 1), "stainless": (1.0, 0.22, 0, 1),
        "pipe_fire": (0.2, 0.5, 0, 1), "imp_panel": (0.3, 0.45, 0, 1), "coping": (0.7, 0.35, 0, 1), "hm_frame": (0.5, 0.4, 0, 1),
        "hm_door": (0.4, 0.4, 0, 1), "rf_tile": (0.3, 0.5, 0, 1), "pedestal": (0.8, 0.4, 0, 1), "mirror": (1.0, 0.03, 0, 1),
        "ceramic": (0.0, 0.08, 0, 1), "luminaire": (0.0, 0.3, 2.0, 1), "filter_face": (0.0, 0.7, 0.4, 1), "roof_deck": (0.0, 0.8, 0, 1),
        "asphalt": (0.0, 0.95, 0, 1), "lift": (0.7, 0.35, 0, 1), "space": (0.0, 1.0, 0, 0.05)}


# ------------------------------------------------------------------ reading the GLB

def read_glb(path):
    b = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", b, 0)
    assert magic == b"glTF" and version == 2 and length == len(b)
    jlen, _ = struct.unpack_from("<I4s", b, 12)
    doc = json.loads(b[20:20 + jlen])
    off = 20 + jlen
    blen, _ = struct.unpack_from("<I4s", b, off)
    return doc, memoryview(b)[off + 8:off + 8 + blen]


DOC, BIN = read_glb(GLB)


def acc(i):
    a = DOC["accessors"][i]
    v = DOC["bufferViews"][a["bufferView"]]
    n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[a["type"]]
    return np.frombuffer(BIN, dtype="<f4", count=a["count"] * n, offset=v["byteOffset"] + a.get("byteOffset", 0)).reshape(-1, n)


def to_blender(p):
    """glTF (x, y, z) Y up to Blender (x, -z, y) Z up: the IFC's own axes."""
    return np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1)


# ------------------------------------------------------------------ scene, materials

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
scene = bpy.context.scene


def srgb(c):
    return [x for x in c] + [1.0]


MATS = {}


def material(name, colour=None):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    if not m.node_tree:
        m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    metal, rough, emit, alpha = LOOK.get(name, (0.0, 0.6, 0, 1))
    b.inputs["Base Color"].default_value = srgb(colour or (0.8, 0.8, 0.8))
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = srgb(colour or (1, 1, 1))
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    MATS[name] = m
    return m


GL_MATS = [material(m["name"], TINT.get(m["name"], m["pbrMetallicRoughness"]["baseColorFactor"][:3])) for m in DOC["materials"]]

ROOT_COL = bpy.data.collections.new("Fab BIM")
scene.collection.children.link(ROOT_COL)
COLS = {}


def col(path, hidden=False):
    """A nested collection by path, e.g. ("P1", "support floor", "Structure")."""
    key = tuple(path)
    if key in COLS:
        return COLS[key]
    parent = ROOT_COL if len(key) == 1 else col(key[:-1])
    c = bpy.data.collections.new(" / ".join(key))
    parent.children.link(c)
    COLS[key] = c
    if hidden:
        c.hide_render = True
        c.hide_viewport = True
    return c


# ------------------------------------------------------------------ meshes

MESHES = {}


def mesh(i):
    if i in MESHES:
        return MESHES[i]
    g = DOC["meshes"][i]
    me = bpy.data.meshes.new(g["name"])
    pos, mi = [], []
    for k, p in enumerate(g["primitives"]):
        v = to_blender(acc(p["attributes"]["POSITION"]))
        pos.append(v)
        mi.append(np.full(len(v) // 3, k, dtype=np.int32))
        me.materials.append(GL_MATS[p["material"]])
    v = np.concatenate(pos).astype(np.float32)
    n = len(v)
    me.vertices.add(n)
    me.vertices.foreach_set("co", v.ravel())
    me.loops.add(n)
    me.loops.foreach_set("vertex_index", np.arange(n, dtype=np.int32))
    me.polygons.add(n // 3)
    me.polygons.foreach_set("loop_start", np.arange(0, n, 3, dtype=np.int32))
    me.polygons.foreach_set("material_index", np.concatenate(mi))
    me.update()
    me.validate(clean_customdata=False)
    MESHES[i] = me
    return me


def instancer(src):
    """A Geometry Nodes group for one repeat shape: put src on every point, turned by the point's rotation."""
    name = f"bim repeats {src.name}"
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    info = N.new("GeometryNodeObjectInfo")
    info.transform_space = "ORIGINAL"
    info.inputs["Object"].default_value = src
    rot = N.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "QUATERNION"
    rot.inputs["Name"].default_value = "rot"
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(gi.outputs[0], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    L.new(rot.outputs["Attribute"], inst.inputs["Rotation"])
    L.new(inst.outputs["Instances"], go.inputs[0])
    return ng


MAP_OBS = {}


def map_object(i):
    if i not in MAP_OBS:
        ob = bpy.data.objects.new(f"map {DOC['meshes'][i]['name']}", mesh(i))
        col(("Repeat shapes",), hidden=True).objects.link(ob)
        MAP_OBS[i] = ob
    return MAP_OBS[i]


# ------------------------------------------------------------------ the tree

nodes = DOC["nodes"]
parent = {}
for i, n in enumerate(nodes):
    for c in n.get("children", []):
        parent[c] = i


def building_of(i):
    while i in parent:
        i = parent[i]
        x = nodes[i].get("extras", {})
        if x.get("Class") == "IfcBuilding":
            m = re.search(r"(\d+)", x.get("Name", ""))
            return f"P{m.group(1)}" if m else x.get("Name")
    return "Site"


ELEMENTS, INSTANCES, GIDS = 0, 0, 0
by_gid = {}
tool_boxes = []
for i, n in enumerate(nodes):
    x = n.get("extras", {})
    cls = x.get("Class")
    if not cls or cls in ("IfcSite", "IfcBuilding", "IfcBuildingStorey"):
        continue
    ELEMENTS += 1
    b = building_of(i)
    storey = x.get("Storey") or ("site" if b == "Site" else "unplaced")
    if cls == "IfcSpace":
        c = col((b, storey, "Spaces"), hidden=True)
    elif cls == "IfcBuildingElementProxy" and "FabGym_Tool.SceneIndex" in x:
        c = col(("IFC tool envelopes",), hidden=True)
    elif b == "Site":
        c = col(("Site", "Process" if (x.get("ObjectType") or "").startswith("hoist") else "Site"))
    else:
        c = col((b, storey, CLASS_TRADE.get(cls, "Process")))
    ob = bpy.data.objects.new(n["name"], mesh(n["mesh"]) if "mesh" in n else None)
    if "mesh" not in n:
        ob.empty_display_size = 0.2
    for k, v in x.items():
        if isinstance(v, (str, int, float, bool)):
            ob[k] = v
    GIDS += "GlobalId" in ob.keys()
    c.objects.link(ob)
    by_gid[x["GlobalId"]] = ob
    if "FabGym_Tool.SceneIndex" in x:
        tool_boxes.append((x["FabGym_Tool.SceneIndex"], x["GlobalId"]))
    for ci in n.get("children", []):
        k = nodes[ci]
        if "EXT_mesh_gpu_instancing" not in k.get("extensions", {}):
            continue
        at = k["extensions"]["EXT_mesh_gpu_instancing"]["attributes"]
        tr = to_blender(acc(at["TRANSLATION"])).astype(np.float32)
        if "ROTATION" in at:
            q = acc(at["ROTATION"])                # glTF (x, y, z, w) about Y up; Blender (w, x, y, z) about Z up
            rq = np.stack([q[:, 3], q[:, 0], -q[:, 2], q[:, 1]], axis=1).astype(np.float32)
        else:
            rq = np.tile(np.array([1, 0, 0, 0], dtype=np.float32), (len(tr), 1))
        pts = bpy.data.meshes.new(k["name"])
        pts.vertices.add(len(tr))
        pts.vertices.foreach_set("co", tr.ravel())
        a = pts.attributes.new("rot", "QUATERNION", "POINT")
        a.data.foreach_set("value", rq.ravel())
        po = bpy.data.objects.new(k["name"], pts)
        mod = po.modifiers.new("repeats", "NODES")
        mod.node_group = instancer(map_object(k["mesh"]))
        c.objects.link(po)
        po.parent = ob
        INSTANCES += len(tr)

# ------------------------------------------------------------------ dressing: the film's tool models in the IFC's boxes

kit = {name: material("kit " + name, [(int(h[j:j + 2], 16) / 255) ** 2.2 for j in (0, 2, 4)]) for name, (h, *_r) in M["materials"].items()}
for name, (h, metal, rough, emit, alpha) in M["materials"].items():
    bsdf = kit[name].node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Emission Color"].default_value = bsdf.inputs["Base Color"].default_value
        bsdf.inputs["Emission Strength"].default_value = emit


def kit_mesh(kind, lights=False):
    me = bpy.data.meshes.new(f"tool model {kind}" + (" lights" if lights else ""))
    V, F, MI, mats = [], [], [], []
    for p in M["kinds"][kind]:
        if (p["role"] == "light") != lights:
            continue
        m = kit[p["mat"]]
        if m not in mats:
            mats.append(m)
        mi = mats.index(m)
        lo, hi = p["min"], p["max"]
        if p["shape"] == "box":
            k = len(V)
            x0, y0, z0 = lo
            x1, y1, z1 = hi
            V += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            F += [(k, k + 3, k + 2, k + 1), (k + 4, k + 5, k + 6, k + 7), (k, k + 1, k + 5, k + 4), (k + 1, k + 2, k + 6, k + 5),
                  (k + 2, k + 3, k + 7, k + 6), (k + 3, k, k + 4, k + 7)]
            MI += [mi] * 6
        else:
            ax = "xyz".index(p.get("axis", "z"))
            a, b = [j for j in range(3) if j != ax]
            c = [(lo[j] + hi[j]) / 2 for j in range(3)]
            r = (hi[a] - lo[a]) / 2
            k, n = len(V), 20
            for end in (lo[ax], hi[ax]):
                for s in range(n):
                    q = [0.0, 0.0, 0.0]
                    q[ax], q[a], q[b] = end, c[a] + r * math.cos(2 * math.pi * s / n), c[b] + r * math.sin(2 * math.pi * s / n)
                    V.append(tuple(q))
            for s in range(n):
                t = (s + 1) % n
                F.append((k + s, k + t, k + n + t, k + n + s))
                MI.append(mi)
            F += [tuple(k + s for s in reversed(range(n))), tuple(k + n + s for s in range(n))]
            MI += [mi, mi]
    me.from_pydata(V, [], F)
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", MI)
    me.update()
    return me


DRESS = col(("Dressing (not in the IFC)",))
kits = {}
dressing = []
scene_tools = {i: t for i, t in enumerate(S["tools"])}
for si, gid in sorted(tool_boxes):
    t = scene_tools[si]
    if t["kind"] not in kits:
        kits[t["kind"]] = (kit_mesh(t["kind"]), kit_mesh(t["kind"], lights=True))
    body, lights = kits[t["kind"]]
    for me, what in ((body, ""), (lights, " lights")):
        if not me.vertices:
            continue
        ob = bpy.data.objects.new(f"tool model {si}{what}", me)
        ob.location = t["o"]
        ob.rotation_euler = (0, 0, math.radians(t["yaw"]))
        ob["dressing"] = ("the visitor film's tool model, placed in the IFC tool's box; not part of the IFC" if not what else
                          "the tool's status light tower, standing on top of its box; not part of the IFC")
        ob["GlobalId of its IFC box"] = gid
        DRESS.objects.link(ob)
        if not what:
            dressing.append((ob, gid))
bpy.context.view_layer.update()


def world_bounds(ob):
    cs = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(c[k] for c in cs) for k in range(3)], [max(c[k] for c in cs) for k in range(3)]


# ------------------------------------------------------------------ light, camera, stills

world = bpy.data.worlds.new("bim sky")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.55, 0.72, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55
scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4.5
sun.data.color = (1.0, 0.95, 0.88)
sun.data.angle = math.radians(1.5)
sun.rotation_euler = (math.radians(55), math.radians(0), math.radians(-35))
# ground under the campus: dressing, not in the IFC
gx0 = min(c["x0"] for c in S["campus"]) - 300
gx1 = max(c["x1"] for c in S["campus"]) + 300
gy0 = min(c["y0"] for c in S["campus"]) - 300
gy1 = max(c["y1"] for c in S["campus"]) + 300
gme = bpy.data.meshes.new("ground")
gme.from_pydata([(gx0, gy0, -0.02), (gx1, gy0, -0.02), (gx1, gy1, -0.02), (gx0, gy1, -0.02)], [], [(0, 1, 2, 3)])
gme.materials.append(material("ground (dressing)", (0.23, 0.27, 0.18)))
gob = bpy.data.objects.new("ground (dressing, not in the IFC)", gme)
DRESS.objects.link(gob)
for c in [c for c in S["campus"] if c["kind"] == "fab"]:       # under each fab: no sheet draws its slab on grade
    sme = bpy.data.meshes.new("fab ground")
    sme.from_pydata([(c["x0"], c["y0"], -0.01), (c["x1"], c["y0"], -0.01), (c["x1"], c["y1"], -0.01), (c["x0"], c["y1"], -0.01)], [], [(0, 1, 2, 3)])
    sme.materials.append(material("ground under the fab (dressing)", (0.36, 0.36, 0.35)))
    DRESS.objects.link(bpy.data.objects.new(f"ground under {c['name']} (dressing, not in the IFC)", sme))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
scene.collection.objects.link(cam)
scene.camera = cam
engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else engines[0]
if hasattr(scene, "eevee"):
    scene.eevee.taa_render_samples = SAMPLES
    for k, v in (("use_raytracing", True), ("use_shadows", True), ("shadow_ray_count", 2), ("use_fast_gi", True)):
        if hasattr(scene.eevee, k):
            setattr(scene.eevee, k, v)
scene.render.resolution_x, scene.render.resolution_y = RES
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "AgX" if "AgX" in [v.identifier for v in bpy.types.ColorManagedViewSettings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
looks = [i.identifier for i in bpy.types.ColorManagedViewSettings.bl_rna.properties["look"].enum_items]
for want in ("AgX - Medium High Contrast", "Medium High Contrast"):
    if want in looks:
        scene.view_settings.look = want
        break
r = scene.render
r.use_stamp = True
for k in dir(r):
    if k.startswith("use_stamp_") and k not in ("use_stamp_note", "use_stamp_labels"):
        try:
            setattr(r, k, False)
        except (AttributeError, TypeError):
            pass
r.use_stamp_note = True
r.stamp_note_text = TRUTH
r.stamp_font_size = max(12, RES[1] // 45)


def find(pred):
    return [ob for ob in by_gid.values() if pred(ob)]


def box_of(obs):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for ob in obs:
        a, b = world_bounds(ob)
        lo = [min(lo[k], a[k]) for k in range(3)]
        hi = [max(hi[k], b[k]) for k in range(3)]
    return lo, hi


def look(eye, target, lens=24):
    cam.location = eye
    d = Vector(target) - Vector(eye)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens
    cam.data.clip_end = 5000


def hide_storeys(names, hidden=True):
    for key, c in COLS.items():
        if len(key) == 2 and key[1] in names:
            c.hide_render = hidden


fab = [c for c in S["campus"] if c["kind"] == "fab"]
B1 = fab[0]
cz = S["clean_z"]
bay9 = S["bays"][8]


LOW = {}


def low_z(ob):
    if ob.name not in LOW:
        LOW[ob.name] = world_bounds(ob)[0][2]
    return LOW[ob.name]


CUTTABLE = [ob for ob in bpy.data.objects if ob.type in ("MESH", "EMPTY") and not ob.name.startswith("map ")
            and not ob.name.startswith("ground")]


def cut(z, also=()):
    """Hide everything that starts above z (a section cut), and the named extras."""
    for ob in CUTTABLE:
        ob.hide_render = (ob.type == "MESH" and low_z(ob) > z) or ob in also


STAIRS = sorted(find(lambda o: o.get("Class") == "IfcStair" and o.get("ObjectType") != "fixed ladder"), key=lambda o: o.name)


def shot(name):
    scene.view_settings.exposure = 0.0
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55
    if name == "campus":
        cut(1e9)
        look((B1["x0"] - 260, B1["y0"] - 420, 330), ((B1["x0"] + fab[-1]["x1"]) / 2, 0, 0), 28)
    elif name == "cutaway":
        cut(cz + 4.5)
        look((B1["x0"] + 40, B1["y0"] - 90, 75), (B1["x0"] + 100, -10, cz), 24)
    elif name == "subfab":
        cut(1e9)
        scene.view_settings.exposure = 1.2
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.08
        y = (bay9["y0"] + bay9["y1"]) / 2
        look((bay9["x0"] - 10, y - 4, 3.0), (bay9["x1"] + 20, y + 2, 2.4), 18)
    elif name == "bay09":
        cut(cz + 4.5)
        look((bay9["x0"] - 6, bay9["y0"] - 8, cz + 14), ((bay9["x0"] + bay9["x1"]) / 2, (bay9["y0"] + bay9["y1"]) / 2, cz), 18)
    elif name == "stair":
        st = STAIRS[0]
        parts = find(lambda o: (o.get("Name") or "").startswith(st.get("Name") + ",") and o.data is not None)
        lo, hi = box_of(parts)
        cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        walls = find(lambda o: (o.get("Name") or "") == "Stair enclosure " + st.get("Name").split()[-1])
        cut(cz + 1.0, also=walls)
        look((cx - 7, cy - 8, cz + 7), (cx, cy, cz / 2), 22)
    elif name == "gowning":
        sp = sorted(find(lambda o: o.get("Class") == "IfcSpace" and "Gowning" in (o.get("Name") or "")), key=lambda o: o.name)[0]
        lo, hi = world_bounds(sp)
        cut(lo[2] + 2.5)
        cx = (lo[0] + hi[0]) / 2
        look((cx + 0.5, lo[1] - 3.0, lo[2] + 6.5), (cx, lo[1] + 8.0, lo[2]), 16)
    for ob in bpy.data.objects:
        if ob.name.startswith("map "):
            ob.hide_render = True
    path = OUT / f"{name}.png"
    r.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    cut(1e9)
    return path.name


stills = {}
for name in STILLS:
    stills[name] = {"file": shot(name), "caption": TRUTH}

# ------------------------------------------------------------------ the report, read back from Blender

tree = {}
for key in COLS:
    if key[0] in ("Repeat shapes", "IFC tool envelopes", "Dressing (not in the IFC)"):
        continue
    t = tree.setdefault(key[0], {})
    if len(key) >= 2:
        t2 = t.setdefault(key[1], [])
        if len(key) == 3 and key[2] not in t2:
            t2.append(key[2])
report = {
    "truth": TRUTH, "elements": ELEMENTS, "global_ids": GIDS, "instances": INSTANCES,
    "objects": len(bpy.data.objects), "collections": tree,
    "spaces_hidden": all(c.hide_render for k, c in COLS.items() if k[-1] == "Spaces"),
    "dressing": {"collection": DRESS.name.split(" / ")[-1], "boxes_hidden": COLS[("IFC tool envelopes",)].hide_render,
                 "tools": [dict(zip(("lo", "hi"), world_bounds(ob)), GlobalId=gid) for ob, gid in dressing]},
    "stills": stills, "engine": scene.render.engine,
}
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "fab-bim.blend"), compress=True)
(OUT / "report.json").write_text(json.dumps(report, indent=1))
print(f"bim: {ELEMENTS} elements, {INSTANCES} repeats, {len(stills)} stills -> {OUT}")
