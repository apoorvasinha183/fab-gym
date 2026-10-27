"""Build the realistic fab in Blender and render the film "Where the Time Goes"
(docs/FAB-FILM-SCRIPT.md). A gigafab-style layout of our own design on the SMT2020 model; not a
real fab. Every model comes from viz/look/kit.py's parts, every carrier and tool state from the
run (viz/look/scene.py), the lot, the captions and the clock from viz/film/film.py.

    Blender -b -P viz/blender/real.py -- SCENE MODELS FILM OUT [--still S1,S2 | --frames A:B]
                                          [--res 1920x1080] [--samples 16] [--nosave]

SCENE, MODELS and FILM are data/layout-real/{scene-optimised,models,film}.json. Writes
OUT/fab.blend, OUT/frames/f0001.jpg ... (or OUT/still-S.png for film second S), and
OUT/overlay.json: per frame, where the labels sit on screen, for viz/film/compose.py.
Everything outside the cleanroom is drawn only, at assumed places and sizes.
"""

import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :]
SCENE, MODELS, FILM, OUT = (Path(x) for x in argv[:4])


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


OUT.mkdir(parents=True, exist_ok=True)
RES = [int(v) for v in opt("--res", "1920x1080").split("x")]
SAMPLES = int(opt("--samples", "16"))
STILLS = [float(v) for v in opt("--still").split(",")] if opt("--still") else None
FR = [int(v) for v in opt("--frames").split(":")] if opt("--frames") else None
S = json.loads(SCENE.read_text())
M = json.loads(MODELS.read_text())
F = json.loads(FILM.read_text())
FPS = 24
SHOTS = {x["id"]: x for x in F["shots"]}
END_S = F["shots"][-1]["end"]
NFRAMES = int(round(END_S * FPS))
CZ, PORT_Z, RAIL_Z, RIDE_Z = S["clean_z"], S["port_z"], S["rail_z"], S["ride_z"]
CEIL = CZ + [f for f in S["floors"] if f["name"] == "cleanroom"][0]["z1"] - [f for f in S["floors"] if f["name"] == "cleanroom"][0]["z0"]
AIR_TOP = [f for f in S["floors"] if f["name"] == "air space"][0]["z1"]
ROOF_TOP = [f for f in S["floors"] if f["name"] == "roof"][0]["z1"]
SUPPORT_TOP = [f for f in S["floors"] if f["name"] == "support floor"][0]["z1"]
WAFFLE_TOP = [f for f in S["floors"] if f["name"] == "waffle slab"][0]["z1"]
random.seed(7)

# ------------------------------------------------------------------------- time
TM = F["timemap"]


def sim_at(s):
    """Fab minute at film second s."""
    for a, b, c, d in TM:
        if a <= s <= b:
            return c + (d - c) * (s - a) / (b - a)
    if s < TM[0][0]:
        a, b, c, d = TM[0]
    else:
        a, b, c, d = TM[-1]
    return c + (d - c) * (s - a) / (b - a)


def film_s(t):
    """Film second at fab minute t; inside a jump, the second the jump happens."""
    for a, b, c, d in TM:
        if c <= t <= d:
            return a + (b - a) * (t - c) / (d - c)
    if t < TM[0][2]:
        a, b, c, d = TM[0]
        return a + (b - a) * (t - c) / (d - c)
    if t > TM[-1][3]:
        a, b, c, d = TM[-1]
        return a + (b - a) * (t - c) / (d - c)
    for x, y in zip(TM, TM[1:]):
        if x[3] < t < y[2]:
            return y[0]
    return TM[-1][1]


def frame_of_s(s):
    return 1 + s * FPS


def frame_of(t):
    return frame_of_s(film_s(t))


def increasing(frames):
    out, last = [], -1e18
    for f in frames:
        f = max(f, last + 1e-3)
        out.append(f)
        last = f
    return out


# ------------------------------------------------------------------------- setup
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, NFRAMES
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = RES
scene.render.resolution_percentage = 100
ee = scene.eevee
for k, v in (("taa_render_samples", SAMPLES), ("use_shadows", True), ("use_raytracing", True), ("volumetric_end", 2500.0),
             ("volumetric_tile_size", "8"), ("use_gtao", True), ("fast_gi_distance", 6.0)):
    try:
        setattr(ee, k, v)
    except (AttributeError, TypeError):
        pass
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    pass


def srgb(h):
    h = h.lstrip("#")
    return [(int(h[i : i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)]


def rgba(h, a=1.0):
    return srgb(h) + [a]


# ------------------------------------------------------------------------- sky and sun
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
wn = world.node_tree.nodes
sky = wn.new("ShaderNodeTexSky")
types = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
for want in ("MULTIPLE_SCATTERING", "NISHITA", "SINGLE_SCATTERING", "HOSEK_WILKIE", "PREETHAM"):
    if want in types:
        sky.sky_type = want
        break
for k, v in (("altitude", 50.0), ("air_density", 1.0), ("dust_density", 2.5), ("ozone_density", 1.0), ("sun_intensity", 0.6),
             ("sun_size", math.radians(1.2))):
    try:
        setattr(sky, k, v)
    except (AttributeError, TypeError):
        pass
bg = wn["Background"]
world.node_tree.links.new(sky.outputs[0], bg.inputs[0])
bg.inputs[1].default_value = 0.35

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4.0
sun.data.angle = math.radians(1.0)
scene.collection.objects.link(sun)
SUN_AZ = math.radians(-35)  # from the east, toward the south: dawn behind the cooling towers


def set_sun(frame, elev_deg):
    e = math.radians(elev_deg)
    d = Vector((math.cos(e) * math.cos(SUN_AZ), math.cos(e) * math.sin(SUN_AZ), math.sin(e)))
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sun.data.color = (1.0, 0.72 + 0.25 * min(1, elev_deg / 25), 0.5 + 0.42 * min(1, elev_deg / 25))
    sun.keyframe_insert("rotation_euler", frame=frame)
    sun.data.keyframe_insert("color", frame=frame)
    try:
        sky.sun_elevation = e
        sky.sun_rotation = math.pi / 2 - SUN_AZ
        sky.keyframe_insert("sun_elevation", frame=frame)
        sky.keyframe_insert("sun_rotation", frame=frame)
    except (AttributeError, TypeError):
        pass


for s_, el in ((0, 3.0), (22, 7.0), (115, 16.0), (END_S, 18.0)):
    set_sun(frame_of_s(s_), el)

# ------------------------------------------------------------------------- materials
MATS = {}


def principled(name, colour, metal=0.0, rough=0.5, emit=0.0, alpha=1.0, emit_colour=None):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgba(colour)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit > 0:
        b.inputs["Emission Color"].default_value = rgba(emit_colour or colour)
        b.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "HASHED")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    MATS[name] = m
    return m


def coords(nt, plane, scale=1.0):
    """World coordinates on a plane (xy, xz or yz) as a 2D vector for a texture."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    com = nt.nodes.new("ShaderNodeCombineXYZ")
    a, b = {"xy": (0, 1), "xz": (0, 2), "yz": (1, 2)}[plane]
    nt.links.new(sep.outputs[a], com.inputs[0])
    nt.links.new(sep.outputs[b], com.inputs[1])
    if scale != 1.0:
        mul = nt.nodes.new("ShaderNodeVectorMath")
        mul.operation = "SCALE"
        mul.inputs["Scale"].default_value = scale
        nt.links.new(com.outputs[0], mul.inputs[0])
        return mul.outputs[0]
    return com.outputs[0]


def panels(name, plane, base, line, w, h, mortar=0.012, rough=0.45, metal=0.0, emit=0.0, emit_lines=False, noise=0.0):
    """A surface of rectangular panels w by h with seams: tiles, filters, cladding, road marks."""
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.squash_frequency = 1
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = w
    br.inputs["Row Height"].default_value = h
    br.inputs["Mortar Size"].default_value = mortar
    br.inputs["Mortar Smooth"].default_value = 0.1
    br.inputs["Bias"].default_value = 0.0
    c1 = rgba(base)
    br.inputs["Color1"].default_value = c1
    br.inputs["Color2"].default_value = [min(1, x * (1.0 + noise)) for x in c1[:3]] + [1]
    br.inputs["Mortar"].default_value = rgba(line)
    nt.links.new(coords(nt, plane), br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit > 0:
        if emit_lines:
            nt.links.new(br.outputs["Color"], b.inputs["Emission Color"])
        else:
            inv = nt.nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.inputs[0].default_value = 1.0
            nt.links.new(br.outputs["Fac"], inv.inputs[1])
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            mul.inputs[1].default_value = emit
            nt.links.new(inv.outputs[0], mul.inputs[0])
            b.inputs["Emission Color"].default_value = c1
            nt.links.new(mul.outputs[0], b.inputs["Emission Strength"])
        if emit_lines:
            b.inputs["Emission Strength"].default_value = emit
    MATS[name] = m
    return m


def noisy(name, a, b, scale=0.08, rough=0.9, plane="xy", bump=0.0):
    """Two colours mixed by noise in world space: grass, asphalt, concrete."""
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes["Principled BSDF"]
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = 8.0
    nt.links.new(coords(nt, plane), nz.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = rgba(a)
    mix.inputs[7].default_value = rgba(b)
    nt.links.new(nz.outputs["Fac"], mix.inputs[0])
    nt.links.new(mix.outputs[2], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = rough
    MATS[name] = m
    return m


def lamp_mat(name, colour, channel):
    """A status lamp lit by one channel of its object's colour (R red, G green, B blue, A amber)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = [x * 0.35 for x in srgb(colour)] + [1]
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Emission Color"].default_value = rgba(colour)
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    if channel == "A":
        src = oi.outputs["Alpha"]
    else:
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(oi.outputs["Color"], sep.inputs[0])
        src = sep.outputs["RGB".index(channel)]
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY_ADD"
    mul.inputs[1].default_value = 9.0
    mul.inputs[2].default_value = 0.05
    nt.links.new(src, mul.inputs[0])
    nt.links.new(mul.outputs[0], b.inputs["Emission Strength"])
    return m


GLOW = None


def shell_mat(name, colour, tag=None):
    """The carrier shell; the red channel of the object's colour makes it glow while it waits
    (shot 12), scaled by one animated value."""
    global GLOW
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgba(colour)
    b.inputs["Roughness"].default_value = 0.3
    b.inputs["Emission Color"].default_value = rgba("6fe3ff")
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(oi.outputs["Color"], sep.inputs[0])
    val = nt.nodes.new("ShaderNodeValue")
    val.name = "glow"
    val.outputs[0].default_value = 0.0
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    nt.links.new(sep.outputs[0], mul.inputs[0])
    nt.links.new(val.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], b.inputs["Emission Strength"])
    for frame, v in ((frame_of_s(SHOTS["12"]["start"]) - 1, 0.0), (frame_of_s(SHOTS["12"]["start"]) + 24, 40.0),
                     (frame_of_s(SHOTS["13"]["start"]), 40.0), (frame_of_s(SHOTS["13"]["start"]) + 24, 0.0)):
        val.outputs[0].default_value = v
        val.outputs[0].keyframe_insert("default_value", frame=frame)
    return m


for name, (hexc, metal, rough, emit, alpha) in M["materials"].items():
    if name.startswith("led_"):
        continue
    principled("kit " + name, hexc, metal, rough, emit, 1.0 if alpha >= 0.8 else alpha)
LAMPS = {"led_green": lamp_mat("lamp green", "34c759", "G"), "led_amber": lamp_mat("lamp amber", "ffb020", "A"),
         "led_blue": lamp_mat("lamp blue", "4aa3ff", "B"), "led_red": lamp_mat("lamp red", "ff3b30", "R")}


def kit_mat(name):
    if name in LAMPS:
        return LAMPS[name]
    return MATS["kit " + name]


# ------------------------------------------------------------------------- meshes
def add_box(V, Fc, MI, mi, x0, y0, z0, x1, y1, z1):
    k = len(V)
    V += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    Fc += [(k, k + 3, k + 2, k + 1), (k + 4, k + 5, k + 6, k + 7), (k, k + 1, k + 5, k + 4), (k + 1, k + 2, k + 6, k + 5),
           (k + 2, k + 3, k + 7, k + 6), (k + 3, k, k + 4, k + 7)]
    MI += [mi] * 6


def add_cyl(V, Fc, MI, mi, lo, hi, axis, n=16):
    i = "xyz".index(axis)
    a, b = [j for j in range(3) if j != i]
    c = [(lo[j] + hi[j]) / 2 for j in range(3)]
    r = (hi[a] - lo[a]) / 2
    k = len(V)
    for end in (lo[i], hi[i]):
        for s in range(n):
            p = [0.0, 0.0, 0.0]
            p[i] = end
            p[a] = c[a] + r * math.cos(2 * math.pi * s / n)
            p[b] = c[b] + r * math.sin(2 * math.pi * s / n)
            V.append(tuple(p))
    for s in range(n):
        t = (s + 1) % n
        Fc.append((k + s, k + t, k + n + t, k + n + s))
        MI.append(mi)
    Fc.append(tuple(k + s for s in reversed(range(n))))
    Fc.append(tuple(k + n + s for s in range(n)))
    MI += [mi, mi]


def mesh(name, V, Fc, MI, mats, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(V, [], Fc)
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", MI)
    if smooth:
        me.shade_smooth()
    me.update()
    return me


def obj(name, me, loc=(0, 0, 0), yaw=0.0, col=None):
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = (0, 0, math.radians(yaw))
    (col or scene.collection).objects.link(ob)
    return ob


class Batch:
    """Boxes and cylinders gathered into one mesh, each with its material."""

    def __init__(self):
        self.V, self.F, self.MI, self.mats = [], [], [], []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def box(self, m, x0, y0, z0, x1, y1, z1):
        add_box(self.V, self.F, self.MI, self.mi(m), min(x0, x1), min(y0, y1), min(z0, z1), max(x0, x1), max(y0, y1), max(z0, z1))

    def cyl(self, m, lo, hi, axis="z", n=16):
        add_cyl(self.V, self.F, self.MI, self.mi(m), lo, hi, axis, n)

    def make(self, name, col=None):
        if not self.V:
            return None
        return obj(name, mesh(name, self.V, self.F, self.MI, self.mats), col=col)


def parts_mesh(name, parts, keep):
    b = Batch()
    for p in parts:
        if not keep(p):
            continue
        m = kit_mat(p["mat"])
        if p["shape"] == "box":
            b.box(m, *p["min"], *p["max"])
        else:
            b.cyl(m, p["min"], p["max"], p.get("axis", "z"), 20)
    return mesh(name, b.V, b.F, b.MI, b.mats)


def curves(ob, data_path=None):
    ad = ob.animation_data
    act = ad.action
    if hasattr(act, "fcurves"):
        fcs = list(act.fcurves)
    else:
        from bpy_extras.anim_utils import action_ensure_channelbag_for_slot

        fcs = list(action_ensure_channelbag_for_slot(act, ad.action_slot).fcurves)
    return [f for f in fcs if data_path is None or f.data_path == data_path]


def fill(ob, data_path, frames, values, constant=False):
    """Keyframes in bulk: values is a list of tuples, one per frame."""
    getattr(ob, data_path)  # exists
    ob.keyframe_insert(data_path, frame=frames[0])
    for fc in curves(ob, data_path):
        i = fc.array_index
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(frames))
        fc.keyframe_points.foreach_set("co", [x for f, v in zip(frames, values) for x in (f, v[i])])
        fc.keyframe_points.foreach_set("interpolation", [0 if constant else 1] * len(frames))
        fc.update()


def hold(ob, data_path, pairs):
    """A few constant keys: pairs of (frame, value)."""
    for f, v in pairs:
        setattr(ob, data_path, v)
        ob.keyframe_insert(data_path, frame=f)
    for fc in curves(ob, data_path):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"


COLS = {}


def col(name):
    if name not in COLS:
        c = bpy.data.collections.new(name)
        scene.collection.children.link(c)
        COLS[name] = c
    return COLS[name]


# ------------------------------------------------------------------------- materials for the place
M_TILE = panels("raised floor", "xy", "a9b0b8", "6c737b", 0.6, 0.6, mortar=0.02, rough=0.3, noise=0.05)
M_FFU = panels("filter ceiling", "xy", "f4f6f8", "8a929b", 1.2, 0.6, mortar=0.025, rough=0.6, emit=0.9)
M_FFU_Y = panels("filter ceiling yellow", "xy", "ffc23a", "7a5a10", 1.2, 0.6, mortar=0.025, rough=0.6, emit=1.2)
M_FFU_TOP = panels("filter tops", "xy", "8f979f", "5a6168", 1.2, 0.6, mortar=0.06, rough=0.7)
M_WALL_X = panels("bay wall x", "xz", "e6e9ec", "b4bac1", 1.2, 2.75, mortar=0.006, rough=0.5)
M_WALL_Y = panels("bay wall y", "yz", "e6e9ec", "b4bac1", 1.2, 2.75, mortar=0.006, rough=0.5)
M_FACADE_X = panels("facade x", "xz", "d9dee3", "9aa3ad", 1.0, 2.0, mortar=0.006, rough=0.35, metal=0.2)
M_FACADE_Y = panels("facade y", "yz", "d9dee3", "9aa3ad", 1.0, 2.0, mortar=0.006, rough=0.35, metal=0.2)
M_LOUVRE_X = panels("louvre x", "xz", "6f7781", "3d434a", 6.0, 0.25, mortar=0.25, rough=0.5, metal=0.3)
M_LOUVRE_Y = panels("louvre y", "yz", "6f7781", "3d434a", 6.0, 0.25, mortar=0.25, rough=0.5, metal=0.3)
M_BAND_X = panels("band x", "xz", "2f6fb4", "245a93", 3.0, 1.2, mortar=0.004, rough=0.3, metal=0.4)
M_BAND_Y = panels("band y", "yz", "2f6fb4", "245a93", 3.0, 1.2, mortar=0.004, rough=0.3, metal=0.4)
M_ROOF = noisy("roof", "8e949a", "7b8187", scale=0.3, rough=0.8)
M_CONC = noisy("concrete", "a7a9a6", "93958f", scale=0.4, rough=0.85)
M_SLAB = principled("slab", "9a9c98", rough=0.9)
M_WAFFLE_Y = panels("waffle cut", "yz", "2a2c2e", "9a9c98", 0.6, 0.6, mortar=0.25, rough=0.9)
M_PLENUM = principled("plenum", "3a3f45", rough=0.8)
M_STEEL = principled("struct steel", "8a939c", metal=0.8, rough=0.4)
M_DUCT = principled("duct", "c3c9cf", metal=0.9, rough=0.3)
M_PIPE_COLS = [principled("pipe " + c, c, metal=0.5, rough=0.4) for c in ("d7dbe0", "3f7fd0", "e0b030", "4caf50", "d04a3a")]
M_PUMP = principled("pump", "5c6f88", metal=0.2, rough=0.5)
M_SCRUB = principled("scrubber", "b7bfc7", rough=0.5)
M_YELLOW = principled("safety yellow", "f2c230", rough=0.6)
M_RAIL = principled("rail", "aeb7c2", metal=1.0, rough=0.3)
M_HANGER = principled("hanger", "6b737c", metal=0.8, rough=0.4)
M_SHELF = principled("shelf", "9ca6b1", metal=0.8, rough=0.35)
M_GRASS = noisy("grass", "3f5f2a", "5b7a37", scale=0.02, rough=0.95)
M_ASPHALT = noisy("asphalt", "2e3032", "3a3c3e", scale=0.5, rough=0.9)
M_MARK = panels("road mark", "xy", "2e3032", "e8e8e2", 6.0, 3.0, mortar=0.0, rough=0.9)
M_PARK = panels("parking", "xy", "34373a", "e8e8e2", 2.6, 5.2, mortar=0.02, rough=0.9)
M_GLASS = principled("glass", "86a9c6", metal=0.6, rough=0.08, alpha=0.35)
M_CURTAIN_X = panels("curtain x", "xz", "3b5a78", "c9d1d8", 1.5, 3.8, mortar=0.012, rough=0.08, metal=0.7)
M_CURTAIN_Y = panels("curtain y", "yz", "3b5a78", "c9d1d8", 1.5, 3.8, mortar=0.012, rough=0.08, metal=0.7)
M_TANK = principled("tank", "eef1f3", metal=0.3, rough=0.25)
M_TOWER = panels("tower louvre", "xz", "7e8a93", "4b545b", 2.0, 0.3, mortar=0.3, rough=0.6)
M_TOWER_Y = panels("tower louvre y", "yz", "7e8a93", "4b545b", 2.0, 0.3, mortar=0.3, rough=0.6)
M_FAN = principled("fan stack", "5d6871", metal=0.4, rough=0.5)
M_TRUNK = principled("trunk", "5a4632", rough=0.9)
M_LEAF = [principled("leaf " + c, c, rough=0.8) for c in ("3c6b2f", "4f7d34", "2f5a2a")]
M_CAR = [principled("car " + c, c, metal=0.6, rough=0.25) for c in ("e8eaec", "1d1f22", "8c9196", "b23a2e", "2d4f86", "c9cdd1")]
M_TYRE = principled("tyre", "141516", rough=0.9)
M_CARGLASS = principled("car glass", "1e2a35", metal=0.5, rough=0.05)
M_PATH = principled("lot path", "0fb6ff", rough=0.4, emit=7.0)
M_STRIP = principled("strip light", "fff4e0", rough=0.5, emit=12.0)
M_SIGN = {a: principled("sign " + a, v["colour"], rough=0.5, emit=0.8) for a, v in S["areas"].items()}


def wall_mat(dx, dy, mx, my):
    """Pick the x-plane or y-plane material for a box by its long side."""
    return mx if abs(dx) >= abs(dy) else my


# ------------------------------------------------------------------------- the ground and campus
G = S["ground"]
gb = Batch()
fb_ = Batch()
fb_.box(M_GRASS, G["x0"] - 150000, G["y0"] - 150000, -60.0, G["x1"] + 150000, G["y1"] + 150000, -40.5)
fb_.make("far ground")

fabs = [c for c in S["campus"] if c["kind"] == "fab"]
site = Batch()
x0 = min(c["x0"] for c in S["campus"] if c["kind"] in ("fab", "pad", "cub", "upw", "office", "gas")) - 25
x1 = max(c["x1"] for c in S["campus"] if c["kind"] in ("fab", "pad", "cub", "upw", "office", "gas")) + 25
y0 = min(c["y0"] for c in S["campus"] if c["kind"] != "road") - 20
y1 = max(c["y1"] for c in S["campus"] if c["kind"] in ("fab", "office", "gas")) + 15
site.box(M_CONC, x0, y0, -0.05, x1, y1, 0.0)
site.make("site apron")
# On the GPU a grass slab under the paving wins some hits from far away and hides it: the near
# grass is a ring around the site, never under it; the far field to the horizon sits 40 m lower.
R_ = 3000
gb.box(M_GRASS, x0 - R_, y0 - R_, -40.0, x1 + R_, y0, -0.05)
gb.box(M_GRASS, x0 - R_, y1, -40.0, x1 + R_, y1 + R_, -0.05)
gb.box(M_GRASS, x0 - R_, y0, -40.0, x0, y1, -0.05)
gb.box(M_GRASS, x1, y0, -40.0, x1 + R_, y1, -0.05)
gb.make("ground")

LABEL_ANCHORS = []  # (text, x, y, z, shots)

for c in S["campus"]:
    k, b = c["kind"], Batch()
    X0, X1, Y0, Y1, H = c["x0"], c["x1"], c["y0"], c["y1"], c["h"]
    if k == "road":
        b.box(M_ASPHALT, X0, Y0, 0.0, X1, Y1, 0.04)
        if X1 - X0 > Y1 - Y0:
            ym = (Y0 + Y1) / 2
            b.box(M_MARK, X0, ym - 0.08, 0.04, X1, ym + 0.08, 0.045)
        else:
            xm = (X0 + X1) / 2
            b.box(M_MARK, xm - 0.08, Y0, 0.04, xm + 0.08, Y1, 0.045)
    elif k == "parking":
        b.box(M_PARK, X0, Y0, 0.0, X1, Y1, 0.04)
    elif k == "pad":
        b.box(M_CONC, X0, Y0, 0.0, X1, Y1, 0.3)
        for i in range(int((X1 - X0) // 12)):
            b.box(M_STEEL, X0 + 6 + i * 12, Y0 + 6, 0.3, X0 + 6.8 + i * 12, Y0 + 6.8, 4.0)
            b.box(M_STEEL, X0 + 6 + i * 12, Y1 - 6.8, 0.3, X0 + 6.8 + i * 12, Y1 - 6, 4.0)
        LABEL_ANCHORS.append(("Pad for Phase 3", (X0 + X1) / 2, (Y0 + Y1) / 2, 10))
    elif k in ("cub", "upw"):
        b.box(M_FACADE_X, X0, Y0, 0.0, X1, Y0 + 0.5, H)
        b.box(M_FACADE_X, X0, Y1 - 0.5, 0.0, X1, Y1, H)
        b.box(M_FACADE_Y, X0, Y0, 0.0, X0 + 0.5, Y1, H)
        b.box(M_FACADE_Y, X1 - 0.5, Y0, 0.0, X1, Y1, H)
        b.box(M_LOUVRE_X, X0 - 0.05, Y0 - 0.05, H * 0.55, X1 + 0.05, Y0 + 0.1, H * 0.85)
        b.box(M_LOUVRE_X, X0 - 0.05, Y1 - 0.1, H * 0.55, X1 + 0.05, Y1 + 0.05, H * 0.85)
        b.box(M_ROOF, X0, Y0, H - 0.6, X1, Y1, H)
        for i in range(int((X1 - X0) // 18)):
            x = X0 + 9 + i * 18
            b.box(M_DUCT, x - 3, Y0 + 8, H, x + 3, Y0 + 20, H + 3.2)
            b.cyl(M_FAN, (x - 2.2, Y1 - 14.4, H), (x + 2.2, Y1 - 10, H + 2.5))
        if k == "upw":
            for i in range(4):
                x = X0 + 12 + i * ((X1 - X0 - 24) / 3)
                b.cyl(M_TANK, (x - 4, Y1 + 3, 0), (x + 4, Y1 + 11, 12), n=28)
        LABEL_ANCHORS.append((c["label"], (X0 + X1) / 2, (Y0 + Y1) / 2, H + 6))
    elif k == "office":
        b.box(M_CURTAIN_X, X0, Y0, 0.0, X1, Y0 + 0.3, H)
        b.box(M_CURTAIN_X, X0, Y1 - 0.3, 0.0, X1, Y1, H)
        b.box(M_CURTAIN_Y, X0, Y0, 0.0, X0 + 0.3, Y1, H)
        b.box(M_CURTAIN_Y, X1 - 0.3, Y0, 0.0, X1, Y1, H)
        b.box(M_ROOF, X0, Y0, H - 0.5, X1, Y1, H + 0.6)
        b.box(M_CONC, X0 + 20, Y0 - 6, 4.0, X0 + 50, Y0, 4.5)
        LABEL_ANCHORS.append((c["label"], (X0 + X1) / 2, (Y0 + Y1) / 2, H + 6))
    elif k == "gas":
        b.box(M_CONC, X0, Y0, 0.0, X1, Y1, 0.3)
        for i in range(6):
            x = X0 + 8 + i * 9
            b.box(principled("iso", "e4e7ea", metal=0.3, rough=0.4), x, Y1 - 16, 0.3, x + 2.4, Y1 - 4, 2.9)
        LABEL_ANCHORS.append((c["label"], (X0 + X1) / 2, (Y0 + Y1) / 2, 28))
    elif k == "tank":
        cx, cy, r = (X0 + X1) / 2, (Y0 + Y1) / 2, (X1 - X0) / 2
        b.cyl(M_TANK, (cx - r, cy - r, 0.3), (cx + r, cy + r, H), n=28)
        b.cyl(M_STEEL, (cx - r * 1.05, cy - r * 1.05, 0.3), (cx + r * 1.05, cy + r * 1.05, 1.2), n=28)
        for i in range(4):
            a = i * math.pi / 2
            b.box(M_STEEL, cx + r * math.cos(a) - 0.1, cy + r * math.sin(a) - 0.1, 0.3, cx + r * math.cos(a) + 0.1, cy + r * math.sin(a) + 0.1, H + 0.5)
    elif k == "cooling_tower":
        b.box(M_TOWER, X0, Y0, 0, X1, Y0 + 0.3, H)
        b.box(M_TOWER, X0, Y1 - 0.3, 0, X1, Y1, H)
        b.box(M_TOWER_Y, X0, Y0, 0, X0 + 0.3, Y1, H)
        b.box(M_TOWER_Y, X1 - 0.3, Y0, 0, X1, Y1, H)
        b.box(M_ROOF, X0, Y0, H - 0.4, X1, Y1, H)
        cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
        b.cyl(M_FAN, (cx - 4.5, cy - 4.5, H), (cx + 4.5, cy + 4.5, H + 3.0), n=28)
        if c["label"]:
            LABEL_ANCHORS.append(("Cooling towers", cx, cy, H + 16))
    elif k == "stack":
        cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
        b.cyl(M_DUCT, (cx - 1.5, cy - 1.5, 0), (cx + 1.5, cy + 1.5, H), n=24)
        b.cyl(M_STEEL, (cx - 1.7, cy - 1.7, H - 1.0), (cx + 1.7, cy + 1.7, H), n=24)
        b.box(M_STEEL, cx - 0.4, cy + 1.5, 0, cx + 0.4, cy + 2.2, H - 1)
    elif k == "corridor":
        b.box(M_FACADE_Y, X0, Y0, c["z0"], X1, Y1, H)
    elif k == "bridge":
        z0 = c["z0"]
        b.box(M_GLASS, X0, Y0, z0, X1, Y0 + 0.1, H)
        b.box(M_GLASS, X0, Y1 - 0.1, z0, X1, Y1, H)
        b.box(M_STEEL, X0, Y0, z0 - 0.6, X1, Y1, z0)
        b.box(M_STEEL, X0, Y0, H, X1, Y1, H + 0.5)
        n = int((X1 - X0) // 6)
        for i in range(n + 1):
            x = X0 + i * (X1 - X0) / n
            b.box(M_STEEL, x - 0.15, Y0 - 0.1, z0, x + 0.15, Y0 + 0.15, H)
            b.box(M_STEEL, x - 0.15, Y1 - 0.15, z0, x + 0.15, Y1 + 0.1, H)
        xm = (X0 + X1) / 2
        b.box(M_CONC, xm - 1.2, -1.2, 0, xm + 1.2, 1.2, z0 - 0.6)
        LABEL_ANCHORS.append(("Overhead hoist bridge", xm, 0, H + 8))
    b.make(c["name"], col("campus"))

# steam over the cooling towers: a soft volume, drawn only
steam_m = bpy.data.materials.new("steam")
steam_m.use_nodes = True
nt = steam_m.node_tree
nt.nodes.remove(nt.nodes["Principled BSDF"])
vol = nt.nodes.new("ShaderNodeVolumePrincipled")
vol.inputs["Color"].default_value = (0.95, 0.95, 0.97, 1)
nz = nt.nodes.new("ShaderNodeTexNoise")
nz.inputs["Scale"].default_value = 0.08
nz.inputs["Detail"].default_value = 4.0
tc = nt.nodes.new("ShaderNodeTexCoord")
nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
grad = nt.nodes.new("ShaderNodeSeparateXYZ")
nt.links.new(tc.outputs["Generated"], grad.inputs[0])
fade = nt.nodes.new("ShaderNodeMath")
fade.operation = "SUBTRACT"
fade.inputs[0].default_value = 1.0
nt.links.new(grad.outputs[2], fade.inputs[1])
d1 = nt.nodes.new("ShaderNodeMath")
d1.operation = "MULTIPLY"
nt.links.new(nz.outputs["Fac"], d1.inputs[0])
nt.links.new(fade.outputs[0], d1.inputs[1])
d2 = nt.nodes.new("ShaderNodeMath")
d2.operation = "MULTIPLY"
d2.inputs[1].default_value = 0.09
nt.links.new(d1.outputs[0], d2.inputs[0])
nt.links.new(d2.outputs[0], vol.inputs["Density"])
nt.links.new(vol.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
for c in S["campus"]:
    if c["kind"] == "cooling_tower":
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2
        sb = Batch()
        sb.cyl(steam_m, (cx - 7, cy - 7, c["h"] + 3), (cx + 7, cy + 7, c["h"] + 40), n=20)
        so = sb.make("steam " + c["name"], col("campus"))
        so.location.z = 0
        for i, fr in enumerate(range(1, NFRAMES + 1, 240)):
            so.location.x = 2.0 * math.sin(i)
            so.keyframe_insert("location", frame=fr)

# trees and parked cars, drawn only
tb = Batch()
for i in range(240):
    side = random.random()
    if side < 0.3:
        x, y = random.uniform(x0, x1), random.uniform(y1 + 6, y1 + 26)
    elif side < 0.6:
        x, y = random.uniform(x0, x1), random.uniform(y0 - 70, y0 - 8)
    elif side < 0.8:
        x, y = random.uniform(x0 - 40, x0 - 6), random.uniform(y0, y1)
    else:
        x, y = random.uniform(x1 + 6, x1 + 40), random.uniform(y0, y1)
    if any(cc["x0"] - 3 < x < cc["x1"] + 3 and cc["y0"] - 3 < y < cc["y1"] + 3 for cc in S["campus"]):
        continue
    h = random.uniform(6, 11)
    r = random.uniform(2.2, 3.6)
    tb.cyl(M_TRUNK, (x - 0.25, y - 0.25, 0), (x + 0.25, y + 0.25, h * 0.45), n=8)
    tb.cyl(random.choice(M_LEAF), (x - r, y - r, h * 0.35), (x + r, y + r, h), n=10)
tb.make("trees", col("campus"))


def car_parts(b, x, y, yaw, m):
    c, s = math.cos(yaw), math.sin(yaw)

    def p(u, v):
        return (x + u * c - v * s, y + u * s + v * c)

    # an axis-aligned car (yaw 0 or 90 only)
    L, W = (4.4, 1.8) if abs(s) < 0.5 else (1.8, 4.4)
    b.box(m, x - L / 2, y - W / 2, 0.3, x + L / 2, y + W / 2, 0.95)
    l2, w2 = (2.4, 1.6) if abs(s) < 0.5 else (1.6, 2.4)
    b.box(M_CARGLASS, x - l2 / 2, y - w2 / 2, 0.95, x + l2 / 2, y + w2 / 2, 1.42)
    for du in (-1.4, 1.4):
        for dv in (-0.8, 0.8):
            px, py = (x + du, y + dv) if abs(s) < 0.5 else (x + dv, y + du)
            if abs(s) < 0.5:
                b.cyl(M_TYRE, (px - 0.33, py - 0.12, 0.0), (px + 0.33, py + 0.12, 0.66), axis="y", n=10)
            else:
                b.cyl(M_TYRE, (px - 0.12, py - 0.33, 0.0), (px + 0.12, py + 0.33, 0.66), axis="x", n=10)


park = [c for c in S["campus"] if c["kind"] == "parking"][0]
cb = Batch()
for i in range(int((park["x1"] - park["x0"]) // 2.6)):
    for j in range(int((park["y1"] - park["y0"]) // 5.2)):
        if random.random() < 0.55:
            car_parts(cb, park["x0"] + (i + 0.5) * 2.6, park["y0"] + (j + 0.5) * 5.2, math.pi / 2, random.choice(M_CAR))
cb.make("parked cars", col("campus"))
road = [c for c in S["campus"] if c["name"] == "R1"][0]
for i in range(6):
    vb = Batch()
    car_parts(vb, 0, 0, 0, random.choice(M_CAR))
    v = vb.make(f"arriving car {i}", col("campus"))
    yy = (road["y0"] + road["y1"]) / 2 + 2.0
    x_start, x_end = road["x1"] - 40 - i * 55, park["x0"] + 60 + i * 12
    v.location = (x_start, yy, 0)
    v.keyframe_insert("location", frame=1)
    v.location = (x_end, yy, 0)
    v.keyframe_insert("location", frame=frame_of_s(30 + i * 3))

# ------------------------------------------------------------------------- the fab buildings
SP, DEPTH, AISLE = S["spine"], S["depth"], S["aisle"]
FAC = {}  # façade bands of each building and side: name -> object
for ph, c in enumerate(fabs):
    X0, X1, Y0, Y1 = c["x0"], c["x1"], c["y0"], c["y1"]
    ox, L = S["offsets"][ph], S["lengths"][ph]
    ix0, ix1, iy0, iy1 = ox, ox + L, -(SP / 2 + DEPTH), SP / 2 + DEPTH
    pre = c["name"]
    # support floor: slab on grade, columns, pumps and scrubbers under every tool, ducts, pipe racks
    sb = Batch()
    sb.box(M_CONC, X0, Y0, -0.05, X1, Y1, 0.0)
    for gx in range(int((X1 - X0) // 12) + 1):
        for gy in range(int((Y1 - Y0) // 12) + 1):
            x, y = X0 + 3 + gx * 12, Y0 + 3 + gy * 12
            if x < X1 - 1 and y < Y1 - 1 and abs(y) > SP / 2 + 0.5:
                sb.box(M_SLAB, x - 0.4, y - 0.4, 0, x + 0.4, y + 0.4, SUPPORT_TOP)
    for t in S["tools"]:
        if S["bays"][t["bay"]]["phase"] != ph:
            continue
        cx, cy = (t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2
        sb.box(M_PUMP, cx - 0.35, cy - 0.5, 0, cx + 0.35, cy + 0.5, 1.0)
        back = t["x0"] - 0.5 if t["wall"] == 0 else t["x1"] + 0.5
        sb.cyl(M_SCRUB, (back - 0.4, cy - 0.4, 0), (back + 0.4, cy + 0.4, 1.9), n=12)
        sb.cyl(M_PIPE_COLS[0], (cx - 0.08, cy - 0.08, 1.0), (cx + 0.08, cy + 0.08, SUPPORT_TOP), n=8)
    for b in S["bays"]:
        if b["phase"] != ph:
            continue
        for xx in (b["x0"] + 0.9, b["x1"] - 0.9):
            sb.cyl(M_DUCT, (xx - 0.45, b["y0"], 4.6), (xx + 0.45, b["y1"], 5.5), axis="y", n=14)
    for i, y in enumerate((-2.4, -1.4, -0.4, 0.6, 1.6, 2.6)):
        sb.cyl(M_PIPE_COLS[i % len(M_PIPE_COLS)], (ix0, y - 0.25, 4.3), (ix1, y + 0.25, 4.8), axis="x", n=12)
    sb.box(M_STEEL, ix0, -3.0, 4.0, ix1, 3.0, 4.1)
    for gy in range(int((Y1 - Y0) // 8)):
        y = Y0 + 4 + gy * 8
        sb.box(M_STRIP, X0 + 1, y - 0.06, SUPPORT_TOP - 0.12, X1 - 1, y + 0.06, SUPPORT_TOP - 0.05)
    sb.make(pre + " support floor", col("building"))
    # waffle slab, raised floor plenum and tiles
    wb = Batch()
    wb.box(M_SLAB, X0, Y0, SUPPORT_TOP, X1 - 0.3, Y1, WAFFLE_TOP)
    wb.box(M_WAFFLE_Y, X1 - 0.3, Y0, SUPPORT_TOP, X1, Y1, WAFFLE_TOP)
    wb.box(M_PLENUM, X0, Y0, WAFFLE_TOP, X1, Y1, CZ - 0.04)
    wb.box(M_TILE, X0, Y0, CZ - 0.04, X1, Y1, CZ)
    for y in (-SP / 2 - 0.08, SP / 2):
        wb.box(M_YELLOW, ix0, y, CZ, ix1, y + 0.08, CZ + 0.005)
    wb.make(pre + " floors", col("building"))
    # bay walls between bays, from the spine to the back wall
    bw = Batch()
    for side, sgn in ((0, 1), (1, -1)):
        mine = [b for b in S["bays"] if b["phase"] == ph and b["side"] == side]
        bx = sorted({round(b["x0"], 3) for b in mine} | {round(b["x1"], 3) for b in mine})
        ya, yb = sgn * (SP / 2), sgn * (SP / 2 + DEPTH)
        for x in bx[1:-1]:
            bw.box(M_WALL_Y, x - 0.06, min(ya, yb), CZ, x + 0.06, max(ya, yb), CEIL)
    for b in S["bays"]:
        if b["phase"] != ph:
            continue
        cx = (b["x0"] + b["x1"]) / 2
        ys = SP / 2 + 0.2 if b["side"] == 0 else -SP / 2 - 0.2
        bw.box(M_SIGN[b["area"]], cx - 1.6, ys - 0.03, CEIL - 1.1, cx + 1.6, ys + 0.03, CEIL - 0.5)
    bw.make(pre + " bay walls", col("building"))
    for side, sgn in (("north", 1), ("south", -1)):
        ew = Batch()
        ew.box(M_WALL_X, ix0, sgn * (SP / 2 + DEPTH) - 0.06, CZ, ix1, sgn * (SP / 2 + DEPTH) + 0.06, CEIL)
        FAC[(pre, side, "end wall")] = ew.make(f"{pre} {side} end wall", col("building"))
    # the filter ceiling: yellow over lithography, white elsewhere
    ce = Batch()
    for b in S["bays"]:
        if b["phase"] != ph:
            continue
        ce.box(M_FFU_Y if b["light"] == "yellow" else M_FFU, b["x0"], b["y0"], CEIL, b["x1"], b["y1"], CEIL + 0.12)
    ce.box(M_FFU, ix0, -SP / 2, CEIL, ix1, SP / 2, CEIL + 0.12)
    ce.box(M_FFU_TOP, X0, Y0, CEIL + 0.12, X1, Y1, CEIL + 0.14)
    ceiling = ce.make(pre + " ceiling", col("building"))
    # the air space: trusses and ducts under the roof
    ab = Batch()
    for gx in range(int((X1 - X0) // 12) + 1):
        x = X0 + 3 + gx * 12
        if x < X1:
            ab.box(M_STEEL, x - 0.2, Y0, AIR_TOP - 0.9, x + 0.2, Y1, AIR_TOP - 0.1)
            for gy in range(int((Y1 - Y0) // 12) + 1):
                y = Y0 + 3 + gy * 12
                if y < Y1:
                    ab.box(M_STEEL, x - 0.15, y - 0.15, CEIL + 0.14, x + 0.15, y + 0.15, AIR_TOP - 0.9)
    for y in (-48, -20, 20, 48):
        ab.cyl(M_DUCT, (X0 + 1, y - 0.9, CEIL + 1.4), (X1 - 1, y + 0.9, CEIL + 3.2), axis="x", n=20)
    for gy in range(int((Y1 - Y0) // 12)):
        y = Y0 + 9 + gy * 12
        ab.box(M_STRIP, X0 + 1, y - 0.06, AIR_TOP - 1.05, X1 - 1, y + 0.06, AIR_TOP - 0.98)
    air = ab.make(pre + " air space", col("building"))
    # roof and rooftop plant
    rb = Batch()
    rb.box(M_ROOF, X0, Y0, AIR_TOP, X1, Y1, ROOF_TOP)
    for i in range(int((X1 - X0) // 24)):
        x = X0 + 12 + i * 24
        for y in (Y0 + 18, Y1 - 30):
            rb.box(M_DUCT, x - 5, y, ROOF_TOP, x + 5, y + 12, ROOF_TOP + 3.5)
            rb.cyl(M_FAN, (x - 1.8, y + 3, ROOF_TOP + 3.5), (x + 1.8, y + 6.6, ROOF_TOP + 4.6))
    roof = rb.make(pre + " roof", col("building"))
    # interior lights: one panel per bay under the filters, the spine, the support floor, the air space
    for b in S["bays"]:
        if b["phase"] != ph:
            continue
        ld = bpy.data.lights.new(f"bay light {ph}", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = b["x1"] - b["x0"] - 1, b["y1"] - b["y0"] - 1
        ld.energy = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) * (6.0 if b["light"] == "yellow" else 4.5)
        ld.color = (1.0, 0.62, 0.12) if b["light"] == "yellow" else (0.93, 0.96, 1.0)
        lo = bpy.data.objects.new(f"bay light {ph}", ld)
        lo.location = ((b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2, CEIL - 0.05)
        col("lights").objects.link(lo)
    for z, e, name in ((CEIL - 0.05, 3.0, "spine"),):
        ld = bpy.data.lights.new(f"{name} light {ph}", "AREA")
        ld.shape = "RECTANGLE"
        w = (SP if name == "spine" else (Y1 - Y0))
        ld.size, ld.size_y = (ix1 - ix0) if name == "spine" else (X1 - X0), w
        ld.energy = ld.size * ld.size_y * e
        lo = bpy.data.objects.new(f"{name} light {ph}", ld)
        lo.location = ((X0 + X1) / 2, 0, z)
        col("lights").objects.link(lo)
    # the façade, in bands so the cut can take them away floor by floor
    T = 0.4
    for side, (ax0, ay0, ax1, ay1) in {"south": (X0, Y0, X1, Y0 + T), "north": (X0, Y1 - T, X1, Y1),
                                       "west": (X0, Y0, X0 + T, Y1), "east": (X1 - T, Y0, X1, Y1)}.items():
        mx = side in ("south", "north")
        for band, za, zb, mat in (("support", 0.0, WAFFLE_TOP, M_LOUVRE_X if mx else M_LOUVRE_Y),
                                  ("clean", WAFFLE_TOP, CEIL + 0.14, M_FACADE_X if mx else M_FACADE_Y),
                                  ("air", CEIL + 0.14, AIR_TOP, M_FACADE_X if mx else M_FACADE_Y),
                                  ("roof", AIR_TOP, ROOF_TOP + 0.8, M_BAND_X if mx else M_BAND_Y)):
            fb = Batch()
            fb.box(mat, ax0, ay0, za, ax1, ay1, zb)
            if band == "clean":
                zz = (za + zb) / 2
                fb.box(M_BAND_X if mx else M_BAND_Y, ax0 - (0.02 if not mx else 0), ay0 - (0.02 if mx else 0), zz - 0.4,
                       ax1 + (0.02 if not mx else 0), ay1 + (0.02 if mx else 0), zz + 0.4)
            FAC[(pre, side, band)] = fb.make(f"{pre} {side} {band}", col("facade"))
    LABEL_ANCHORS.append((f"Phase {ph + 1} fab", (X0 + X1) / 2, (Y0 + Y1) / 2, ROOF_TOP + 14))
    FAC[(pre, "inside", "ceiling")] = ceiling
    FAC[(pre, "inside", "air")] = air
    FAC[(pre, "inside", "roof")] = roof


def vanish(ob, at_s, back_s=None, slide=None):
    """Take an object away at film second at_s (sliding it by `slide` first), back at back_s."""
    f = frame_of_s(at_s)
    ob.keyframe_insert("location", frame=1)
    if slide:
        ob.keyframe_insert("location", frame=f - 18)
        ob.location = Vector(slide)
        ob.keyframe_insert("location", frame=f)
    pairs = [(1, False), (f, True)]
    if back_s is not None:
        pairs.append((frame_of_s(back_s), False))
        ob.location = (0, 0, 0)
        ob.keyframe_insert("location", frame=frame_of_s(back_s))
    hold(ob, "hide_render", pairs)
    hold(ob, "hide_viewport", pairs)


# shot 3: Phase 2's east face falls away, top first: roof and air space, cleanroom, support floor
s3 = SHOTS["3"]
third = (s3["end"] - s3["start"]) / 3
back_in = SHOTS["4"]["start"] + 2.5  # the camera is inside: close the building again
for i, bands in enumerate((("roof", "air"), ("clean", "end wall"), ("support",))):
    for band in bands:
        vanish(FAC[("P2", "south", band)], s3["start"] + 1.2 + i * third, back_in, slide=(0, -8, -2) if band != "end wall" else None)
# shots 11 and 12: up through the ceiling; the ceiling, air space and roof of both buildings go
s11 = SHOTS["11"]
for pre in ("P1", "P2"):
    for key in (("inside", "ceiling"), ("inside", "air"), ("inside", "roof"), ("north", "air"), ("north", "roof"),
                ("south", "air"), ("south", "roof"), ("west", "air"), ("west", "roof"), ("east", "air"), ("east", "roof")):
        if (pre,) + key in FAC:
            ob = FAC[(pre,) + key]
            vanish(ob, s11["start"] + 0.6, SHOTS["13"]["start"] + 1)

# ------------------------------------------------------------------------- rails, hangers, shelves, stockers
rb = Batch()
for (ax, ay, az), (bx, by, bz) in S["rails"]:
    w = 0.08
    rb.box(M_RAIL, min(ax, bx) - w, min(ay, by) - w, az, max(ax, bx) + w, max(ay, by) + w, az + 0.12)
    L = math.dist((ax, ay), (bx, by))
    n = max(1, int(L // 3))
    for i in range(n + 1):
        x, y = ax + (bx - ax) * i / n, ay + (by - ay) * i / n
        rb.box(M_HANGER, x - 0.02, y - 0.02, az + 0.12, x + 0.02, y + 0.02, CEIL)
rb.make("hoist rails", col("rails"))
shelves = set()
for L_ in S["lots"]:
    k = L_["k"]
    for a, b in zip(k, k[1:]):
        if a[1:] == b[1:] and a[3] > PORT_Z + 0.01 and abs(a[2]) > SP / 2:
            shelves.add((round(a[1], 2), round(a[2], 2), round(a[3], 3)))
sh = Batch()
fw, fd, fh = S["foup"]
for x, y, z in shelves:
    sh.box(M_SHELF, x - fw / 2 - 0.03, y - fd / 2 - 0.03, z - 0.03, x + fw / 2 + 0.03, y + fd / 2 + 0.03, z)
    sh.box(M_HANGER, x - 0.015, y - 0.015, z, x + 0.015, y + 0.015, CEIL)
sh.make("shelves", col("rails"))
stocker_me = parts_mesh("stocker", M["kinds"]["stocker"], lambda p: p["role"] != "light")
for i, st in enumerate(S["stockers"]):
    obj(f"stocker {i}", stocker_me, st["o"], st["yaw"], col("tools"))

# ------------------------------------------------------------------------- tools and their status lights
BODY, LIGHT = {}, {}
for kind, parts in M["kinds"].items():
    BODY[kind] = parts_mesh(kind, parts, lambda p: p["role"] != "light")
    LIGHT[kind] = parts_mesh(kind + " light", parts, lambda p: p["role"] == "light")
STATE_RGBA = {0: (0, 1, 0, 0), 1: (0, 0, 0, 1), 2: (0, 0, 1, 0), 3: (1, 0, 0, 0)}
by_tool = {}
for t, ti, code in S["states"]:
    by_tool.setdefault(ti, []).append((t, code))
TOOL_OBS = []
for ti, t in enumerate(S["tools"]):
    ob = obj(f"tool {ti}", BODY[t["kind"]], t["o"], t["yaw"], col("tools"))
    lo = obj(f"light {ti}", LIGHT[t["kind"]], t["o"], t["yaw"], col("tools"))
    seq = by_tool.get(ti, [(S["from"], 1)])
    frames = increasing([1] + [frame_of(x[0]) for x in seq[1:]])
    vals = [STATE_RGBA[seq[0][1]]] + [STATE_RGBA[x[1]] for x in seq[1:]]
    lo.color = vals[0]
    if len(frames) > 1:
        fill(lo, "color", frames, vals, constant=True)
    TOOL_OBS.append(ob)

# ------------------------------------------------------------------------- carriers and hoist cars
HERO = F["lot"]
shell = shell_mat("carrier shell", "2f353c")
shell_hot = shell_mat("carrier shell hot", "c4582a")
shell_hero = shell_mat("carrier shell hero", "2f353c")


def carrier_mesh(name, shell_m, tag=None):
    b = Batch()
    for p in M["carrier"]:
        m = shell_m if p["mat"] == "foup_shell" else kit_mat(p["mat"])
        if p["shape"] == "box":
            b.box(m, *p["min"], *p["max"])
        else:
            b.cyl(m, p["min"], p["max"], p.get("axis", "z"))
    if tag:
        w, d, h = S["foup"]
        b.box(principled("tag " + tag, tag, emit=5.0), -w / 2 - 0.004, -0.06, h - 0.1, w / 2 + 0.004, 0.06, h - 0.06)
    return mesh(name, b.V, b.F, b.MI, b.mats)


ME_LOT = carrier_mesh("carrier", shell)
ME_HOT = carrier_mesh("carrier hot", shell_hot, tag="ff7a1a")
ME_HERO = carrier_mesh("carrier hero", shell_hero, tag="39d5ff")
vb = Batch()
for p in M["vehicle"]:
    m = kit_mat(p["mat"])
    vb.box(m, *p["min"], *p["max"])
ME_CAR = mesh("hoist car", vb.V, vb.F, vb.MI, vb.mats)


def lot_track(keys):
    frames = increasing([frame_of(k[0]) for k in keys])
    return frames, [tuple(k[1:4]) for k in keys]


HERO_KEYS = None
for L_ in S["lots"]:
    keys = L_["k"]
    is_hero = L_["id"] == HERO
    me = ME_HERO if is_hero else (ME_HOT if L_["hot"] else ME_LOT)
    ob = obj("lot " + L_["id"], me, keys[0][1:4], 0, col("lots"))
    frames, pos = lot_track(keys)
    fill(ob, "location", frames, pos)
    vis = [(frames[0] - 0.01, 0.0), (frames[0], 1.0), (frames[-1], 1.0), (frames[-1] + 0.01, 0.0)]
    fill(ob, "scale", [v[0] for v in vis], [(v[1],) * 3 for v in vis], constant=True)
    # waiting on a shelf: the red channel, for the glow in shot 12
    wf, wv = [frames[0] - 0.02], [(0, 0, 0, 1)]
    for i, (a, b) in enumerate(zip(keys, keys[1:])):
        waiting = a[1:] == b[1:] and a[3] > PORT_Z + 0.01 and abs(a[2]) > SP / 2
        wf.append(frames[i])
        wv.append((1, 0, 0, 1) if waiting else (0, 0, 0, 1))
    fill(ob, "color", increasing(wf), wv, constant=True)
    if is_hero:
        HERO_KEYS = keys
    # its hoist car, there only while it carries the lot
    cf, cv, sf, sv = [], [], [], []
    for m0, m1 in L_["m"]:
        inside = [k for k in keys if m0 - 1e-6 <= k[0] <= m1 + 1e-6]
        for k in inside:
            cf.append(frame_of(k[0]))
            cv.append((k[1], k[2], RAIL_Z))
        sf += [frame_of(m0) - 0.01, frame_of(m0), frame_of(m1), frame_of(m1) + 0.01]
        sv += [(0,) * 3, (1,) * 3, (1,) * 3, (0,) * 3]
    if cf:
        car = obj("car " + L_["id"], ME_CAR, cv[0], 0, col("cars"))
        fill(car, "location", increasing(cf), cv)
        order = sorted(range(len(sf)), key=lambda i: sf[i])
        fill(car, "scale", increasing([sf[i] for i in order]), [sv[i] for i in order], constant=True)


def hero_at(t):
    k = HERO_KEYS
    if t <= k[0][0]:
        return Vector(k[0][1:4])
    for a, b in zip(k, k[1:]):
        if a[0] <= t <= b[0]:
            u = 0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
            return Vector(a[1:4]).lerp(Vector(b[1:4]), u)
    return Vector(k[-1][1:4])


# the hero's car comes along its rail before the pick-up, and its gripper lowers
leave = F["beats"][0]["t"]
p0 = hero_at(leave)
hcar = obj("hero car approach", ME_CAR, (p0.x, p0.y - 18, RAIL_Z), 0, col("cars"))
pairs = [(leave - 0.32, p0.y - 18), (leave - 0.14, p0.y)]
for t, y in pairs:
    hcar.location = (p0.x, y, RAIL_Z)
    hcar.keyframe_insert("location", frame=frame_of(t))
hold(hcar, "hide_render", [(1, False), (frame_of(leave) + 0.5, True)])
grip_m = principled("gripper", "3a3f45", metal=0.6, rough=0.3)
gb = Batch()
gb.box(grip_m, -0.19, -0.16, -0.03, 0.19, 0.16, 0.0)
grip = gb.make("hero gripper", col("cars"))
belt = Batch()
for dx in (-0.12, 0.12):
    belt.box(principled("belt", "15181b", rough=0.5), dx - 0.012, -0.012, -1.0, dx + 0.012, 0.012, 0.0)
belts = belt.make("hero belts", col("cars"))
car_bottom = RAIL_Z - S["vehicle"][2]
gt = [leave - 0.14, leave, leave + 0.4]
gz = [car_bottom, p0.z + fh, RIDE_Z + fh]
for t, z in zip(gt, gz):
    grip.location = (p0.x, p0.y, z + 0.03)
    grip.keyframe_insert("location", frame=frame_of(t))
    belts.location = (p0.x, p0.y, car_bottom)
    belts.scale = (1, 1, max(0.001, car_bottom - z))
    belts.keyframe_insert("scale", frame=frame_of(t))
    belts.keyframe_insert("location", frame=frame_of(t))
for ob in (grip, belts):
    hold(ob, "hide_render", [(1, True), (frame_of(leave - 0.14), False), (frame_of(leave + 0.4) + 1, True)])

# the hero's path, drawn in shot 11
cu = bpy.data.curves.new("hero path", "CURVE")
cu.dimensions = "3D"
cu.bevel_depth = 0.7
cu.use_fill_caps = True
sp = cu.splines.new("POLY")
pts = [k for k in HERO_KEYS if leave <= k[0] <= F["beats"][-1]["start"]]
sp.points.add(len(pts) - 1)
for p, k in zip(sp.points, pts):
    p.co = (k[1], k[2], CEIL + 0.5, 1)
path = bpy.data.objects.new("hero path", cu)
path.data.materials.append(M_PATH)
scene.collection.objects.link(path)
cu.bevel_factor_end = 0.0
cu.keyframe_insert("bevel_factor_end", frame=frame_of_s(s11["start"] + 1.0))
cu.bevel_factor_end = 1.0
cu.keyframe_insert("bevel_factor_end", frame=frame_of_s(s11["end"] - 1.0))
hold(path, "hide_render", [(1, True), (frame_of_s(s11["start"] + 1.0), False), (frame_of_s(SHOTS["13"]["start"] + 1), True)])

# ------------------------------------------------------------------------- the camera
cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
cam.data.clip_start = 0.05
cam.data.clip_end = 200000
cam.data.sensor_width = 36
scene.collection.objects.link(cam)
scene.camera = cam
target = bpy.data.objects.new("look at", None)
scene.collection.objects.link(target)
tcon = cam.constraints.new("TRACK_TO")
tcon.target = target
tcon.track_axis = "TRACK_NEGATIVE_Z"
tcon.up_axis = "UP_Y"

C = Vector(((S["offsets"][0] + S["offsets"][-1] + S["lengths"][-1]) / 2, -25, 0))


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def orbit(az_deg, dist, z, centre=C):
    a = math.radians(az_deg)
    return centre + Vector((dist * math.cos(a), dist * math.sin(a), z))


def spline(pts, u):
    """Catmull-Rom through points, u in 0..1 over the whole run."""
    n = len(pts) - 1
    x = min(max(u, 0.0), 1.0) * n
    i = min(int(x), n - 1)
    f = x - i
    p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n)]
    return 0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f + (-p0 + 3 * p1 - 3 * p2 + p3) * f * f * f)


def tool(ti):
    return S["tools"][ti]


def port_of(ti, i=0):
    p = tool(ti)["ports"][i]
    return Vector((p[0], p[1], PORT_Z))


def aisle_x(ti):
    b = S["bays"][tool(ti)["bay"]]
    return (b["x0"] + b["x1"]) / 2


B = F["beats"]
wet0, trk, scn, *mid, wet1 = B
mid_beats = mid
tool_leave = tool(wet0["tool"])
p_leave = hero_at(leave)


def front_dir(ti):
    return 1.0 if tool(ti)["wall"] == 0 else -1.0


def ride_path(t0, t1):
    """The hero's path between two fab minutes, as points at ride height."""
    out = [hero_at(t0)]
    for k in HERO_KEYS:
        if t0 < k[0] < t1:
            v = Vector(k[1:4])
            if (v - out[-1]).length > 0.05:
                out.append(v)
    out.append(hero_at(t1))
    return out


def trail_time(t, dist=3.5):
    """The fab minute at which the hero was `dist` metres back along its path."""
    p = hero_at(t)
    tt = t
    for _ in range(400):
        tt -= 0.005
        if (hero_at(tt) - p).length >= dist:
            break
    return tt


def offset_point(t):
    """A point beside the hero's rail, in free space: in a bay, toward the aisle's middle; on the
    spine, toward the bays; on a crossover, east."""
    p = hero_at(t)
    q = hero_at(t + 0.05)
    d = q - p
    if abs(p.y) > SP / 2 + 0.3:
        bays = [b for b in S["bays"] if b["x0"] <= p.x <= b["x1"] and b["y0"] <= p.y <= b["y1"]]
        cx = (bays[0]["x0"] + bays[0]["x1"]) / 2 if bays else p.x
        return Vector((cx, p.y, RIDE_Z + 0.9))
    if abs(d.y) > abs(d.x) and abs(p.y) < 2.1:
        return Vector((p.x + 1.4, p.y, RIDE_Z + 0.9))
    sgn = 1 if p.y >= 0 else -1
    return Vector((p.x, sgn * 3.4, RIDE_Z + 0.9))


CAM = []  # per frame: (location, target, lens)


def shot_frames(sid):
    s = SHOTS[sid]
    a, b = int(round(frame_of_s(s["start"]))), int(round(frame_of_s(s["end"])))
    return range(a, b)


def put(fr, loc, tgt, lens):
    CAM.append((fr, Vector(loc), Vector(tgt), lens))


# shot 1: establishing, 900 m out to 450 m, drifting 10 degrees
for fr in shot_frames("1"):
    u = ease((fr - 1) / (24 * 10))
    az = -40 + 10 * u
    d = 900 + (450 - 900) * u
    z = 350 + (160 - 350) * u
    put(fr, orbit(az, d, z), C + Vector((0, 0, 8)), 24)
# shot 2: orbit north at about 400 m
for fr in shot_frames("2"):
    u = ease((fr - frame_of_s(10)) / (24 * 12))
    put(fr, orbit(-30 + 130 * u, 450 - 70 * u, 160 - 40 * u), C + Vector((0, 0, 8)), 24)
# shot 3: crane down to Phase 2's east face, 60 m out, then push in slowly while it opens
p2 = fabs[1]
ax = aisle_x(wet0["tool"])
pp = port_of(wet0["tool"], 0)
# the side-2 bay whose aisle is nearest the wet etch bay's: the way in from the south
south_bays = [b for b in S["bays"] if b["phase"] == 1 and b["side"] == 1]
sb_ = min(south_bays, key=lambda b: abs((b["x0"] + b["x1"]) / 2 - ax))
sx = (sb_["x0"] + sb_["x1"]) / 2
south = Vector((sx, p2["y0"] - 34, CZ + 4.5))
look_south = Vector((sx, p2["y0"] + 40, CZ + 0.5))
start3 = orbit(100, 380, 120)
crane = [start3, Vector((sx + 30, 40, 150)), Vector((sx + 10, p2["y0"] - 30, 70)), south]
for fr in shot_frames("3"):
    s = (fr - 1) / 24 - SHOTS["3"]["start"]
    if s < 3.0:
        u = ease(s / 3.0)
        loc = spline(crane, u)
        tgt = (C + Vector((0, 0, 8))).lerp(look_south, ease(min(1, s / 2.2)))
    else:
        u = ease((s - 3.0) / 7.0)
        loc = south + Vector((0, 10 * u, -1.0 * u))
        tgt = look_south
    put(fr, loc, tgt, 24)
# shot 4: through the cut and up a bay's aisle, across the spine under the rails, into the wet etch bay
z4 = CZ + 2.4
pts4 = [south + Vector((0, 10, -1.0)), Vector((sx, p2["y0"] + 4, z4)), Vector((sx, -(SP / 2 + 3), z4)), Vector((sx, -SP / 2 + 0.5, z4)),
        Vector((ax, SP / 2 - 1.0, z4)), Vector((ax, SP / 2 + 3, z4 + 0.3)), Vector((ax, pp.y - 5.0, CZ + 3.4))]
tg4 = [look_south, Vector((sx, -20, z4 - 0.4)), Vector((sx, 0, z4 - 0.2)), Vector((ax, SP / 2 + 2, z4 - 0.2)),
       Vector((ax, SP / 2 + 9, z4 - 0.4)), Vector((ax - 0.6, pp.y - 1, CZ + 1.2)), pp + Vector((0, 0, 0.3))]
for fr in shot_frames("4"):
    u = ease((fr - frame_of_s(SHOTS["4"]["start"])) / (24 * 8))
    put(fr, spline(pts4, u), spline(tg4, u), 35)
# shot 5: the pick-up, close, the camera following the carrier up
for fr in shot_frames("5"):
    s = (fr - 1) / 24
    t = sim_at(s)
    h = hero_at(t)
    zc = min(max(h.z + 0.4, PORT_Z + 0.5), RIDE_Z + 0.2)
    side = front_dir(wet0["tool"])
    loc = Vector((pp.x + side * 1.15, pp.y - 2.4, PORT_Z + 0.45))
    put(fr, loc, Vector((h.x, h.y, (h.z + RAIL_Z) / 2 - 0.2)), 24)
# shot 6: the ride, tracking beside the car
prev_loc = CAM[-1][1]
for fr in shot_frames("6"):
    t = sim_at((fr - 1) / 24)
    want = offset_point(trail_time(t))
    h = hero_at(t) + Vector((0, 0, fh / 2))
    loc = want if prev_loc is None else prev_loc.lerp(want, 0.25)
    prev_loc = loc
    put(fr, loc, h, 35)
# shot 7: yellow light; rise and pull back along the track's aisle
tp = port_of(trk["tool"])
tax = aisle_x(trk["tool"])
back7 = -1 if tp.y > 0 else 1
for fr in shot_frames("7"):
    u = ease((fr - frame_of_s(SHOTS["7"]["start"])) / (24 * 10))
    start = Vector((tax, tp.y + back7 * 3.0, CZ + 2.4))
    end = Vector((tax, tp.y + back7 * 24.0, CEIL - 0.35))
    put(fr, start.lerp(end, u), (tp + Vector((0, 0, 0.6))).lerp(Vector((tax, tp.y - back7 * 2, CZ + 1.0)), u), 35)
# shot 8: tracking to the scanner, then along its long body
sp_ = port_of(scn["tool"])
st_ = tool(scn["tool"])
sax = aisle_x(scn["tool"])
s8 = SHOTS["8"]["start"]
prev_loc = CAM[-1][1]
for fr in shot_frames("8"):
    s = (fr - 1) / 24 - s8
    t = sim_at(s + s8)
    if s < 3.0:
        want = offset_point(trail_time(t))
        h = hero_at(t) + Vector((0, 0, fh / 2))
        loc = want if prev_loc is None else prev_loc.lerp(want, 0.3)
        prev_loc = loc
        put(fr, loc, h, 35)
    else:
        u = ease((s - 3.0) / 5.0)
        top = CZ + st_.get("h", 2.9)
        x_front, x_back = (st_["x1"], st_["x0"]) if st_["wall"] == 0 else (st_["x0"], st_["x1"])
        cy = (st_["y0"] + st_["y1"]) / 2
        away = 1 if cy < 0 else -1
        fd = front_dir(scn["tool"])
        loc = Vector((sax + fd * 1.0, cy + away * (7.0 - 2.0 * u), CZ + 1.7))
        tgt = Vector((x_front - fd * 2.0, cy - away * 1.5, CZ + 1.3))
        put(fr, loc, tgt, 35)
# shot 9: three beats at load-port height, hard cuts
s9, e9 = SHOTS["9"]["start"], SHOTS["9"]["end"]
for fr in shot_frames("9"):
    s = (fr - 1) / 24 - s9
    i = min(int(s / ((e9 - s9) / len(mid_beats))), len(mid_beats) - 1)
    bt = mid_beats[i]
    p = port_of(bt["tool"])
    side = front_dir(bt["tool"])
    loc = Vector((p.x + side * 2.3, p.y - 1.4, PORT_Z + 0.55))
    put(fr, loc, p + Vector((0, 0, 0.25)), 50)
# shot 10: set down at wet etch; pull back and rise to show the carriers waiting
wt = tool(wet1["tool"])
wax = aisle_x(wet1["tool"])
wy = (wt["y0"] + wt["y1"]) / 2
dirn = 1 if wy > 0 else -1
for fr in shot_frames("10"):
    u = ease((fr - frame_of_s(SHOTS["10"]["start"])) / (24 * 11))
    start = Vector((wax, wy - dirn * 3.0, RIDE_Z + 0.2))
    end = Vector((wax, wy + dirn * 26.0, CEIL - 0.35))
    put(fr, start.lerp(end, u), Vector((wax - 1.0, wy, RIDE_Z - 0.3)).lerp(Vector((wax, wy + dirn * 4, CZ + 1.0)), u), 35)
# shot 11: up through the filter grid to a view from above the lot's path
xs = [k[1] for k in pts]
ys = [k[2] for k in pts]
mid_xy = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, CZ))
top11 = mid_xy + Vector((0, -12, 150))
end10 = Vector((wax, wy + dirn * 26.0, CEIL - 0.35))
for fr in shot_frames("11"):
    u = ease((fr - frame_of_s(SHOTS["11"]["start"])) / (24 * 9))
    loc = end10.lerp(top11, u)
    loc.z = end10.z + (top11.z - end10.z) * (u ** 1.6)
    put(fr, loc, Vector((wax, wy, CZ)).lerp(mid_xy, ease(u * 1.5)), 35)
# shot 12: the same view, opening out to both buildings
both = Vector(((S["offsets"][0] + S["offsets"][-1] + S["lengths"][-1]) / 2, 0, CZ))
for fr in shot_frames("12"):
    u = ease((fr - frame_of_s(SHOTS["12"]["start"])) / (24 * 11))
    loc = top11.lerp(both + Vector((0, -40, 470)), u)
    put(fr, loc, mid_xy.lerp(both, u), 35)
# shot 13 and the end card: up and out to the opening angle
last12 = both + Vector((0, -40, 470))
for fr in list(shot_frames("13")) + list(range(int(round(frame_of_s(SHOTS["end"]["start"]))), NFRAMES + 1)):
    u = ease((fr - frame_of_s(SHOTS["13"]["start"])) / (24 * 6))
    put(fr, last12.lerp(orbit(-30, 450, 160), u), both.lerp(C + Vector((0, 0, 8)), u), 35 + (24 - 35) * u)

CAM.sort(key=lambda x: x[0])
frames = [x[0] for x in CAM]
fill(cam, "location", frames, [tuple(x[1]) for x in CAM])
fill(target, "location", frames, [tuple(x[2]) for x in CAM])
fill(cam.data, "lens", frames, [(x[3],) for x in CAM])
# hard cuts in shot 9: hold each beat's camera, then jump
for fc in curves(cam, "location") + curves(target, "location"):
    for kp in fc.keyframe_points:
        if frame_of_s(s9) <= kp.co[0] < frame_of_s(e9):
            kp.interpolation = "CONSTANT"

for s_, w in ((0, 0.35), (SHOTS["4"]["start"] + 1.5, 0.35), (SHOTS["4"]["start"] + 3.0, 0.015), (SHOTS["11"]["start"] + 0.6, 0.015),
             (SHOTS["11"]["start"] + 2.0, 0.35)):
    bg.inputs[1].default_value = w
    bg.inputs[1].keyframe_insert("default_value", frame=frame_of_s(s_))
# exposure: interiors a little brighter than the morning outside
for s_, ex in ((0, 0.0), (SHOTS["3"]["start"] + 6, 0.0), (SHOTS["4"]["start"] + 2, -0.1), (SHOTS["11"]["start"] + 4, -0.1),
               (SHOTS["11"]["start"] + 6, -0.6), (SHOTS["13"]["start"] + 2, 0.0)):
    scene.view_settings.exposure = ex
    scene.view_settings.keyframe_insert("exposure", frame=frame_of_s(s_))

# ------------------------------------------------------------------------- overlay data and render
CAM_AT = {x[0]: x for x in CAM}


def screen(fr, p):
    """Where a world point falls in frame fr, from the camera list (0..1 across and down, and depth)."""
    _, loc, tgt, lens = CAM_AT[fr]
    q = (tgt - loc).to_track_quat("-Z", "Y")
    v = q.inverted() @ (Vector(p) - loc)
    if v.z >= -0.01:
        return [-1, -1, -1]
    f = lens / 36.0
    x = 0.5 + f * v.x / -v.z
    y = 0.5 - f * v.y / -v.z * RES[0] / RES[1]
    return [round(x, 4), round(y, 4), round(-v.z, 1)]


def overlay(frames):
    out = {"labels": [a[0] for a in LABEL_ANCHORS], "frames": {}}
    for fr in frames:
        if fr in CAM_AT:
            out["frames"][fr] = {"labels": [screen(fr, a[1:4]) for a in LABEL_ANCHORS], "hero": screen(fr, hero_at(sim_at((fr - 1) / 24)))}
    return out


if "--probe" in argv:
    dg = bpy.context.evaluated_depsgraph_get()
    for s_ in STILLS or []:
        fr = int(round(frame_of_s(s_)))
        scene.frame_set(fr)
        dg = bpy.context.evaluated_depsgraph_get()
        mw = cam.matrix_world
        o = mw.translation
        d = (mw.to_quaternion() @ Vector((0, 0, -1))).normalized()
        hit, loc, nor, idx, ob, _ = scene.ray_cast(dg, o, d)
        print("probe", s_, fr, tuple(round(v, 2) for v in o), tuple(round(v, 2) for v in d), ob.name if hit else None, round((loc - o).length, 2) if hit else None)
    sys.exit(0)
if "--nosave" not in argv:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "fab.blend"), compress=True)

scene.render.image_settings.file_format = "JPEG"
scene.render.image_settings.quality = 92
if STILLS is not None:
    scene.render.image_settings.file_format = "PNG"
    for s_ in STILLS:
        fr = int(round(frame_of_s(s_)))
        scene.frame_set(fr)
        scene.render.filepath = str(OUT / f"still-{s_:06.2f}.png")
        bpy.ops.render.render(write_still=True)
    (OUT / "overlay-stills.json").write_text(json.dumps(overlay([int(round(frame_of_s(s_))) for s_ in STILLS])))
else:
    a, b = FR if FR else (1, NFRAMES)
    (OUT / f"overlay-{a}-{b}.json").write_text(json.dumps(overlay(range(a, b + 1))))
    scene.frame_start, scene.frame_end = a, b
    scene.render.filepath = str(OUT / "frames" / "f")
    bpy.ops.render.render(animation=True)
print("done", OUT)
