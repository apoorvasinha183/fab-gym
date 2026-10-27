"""Small helpers shared by the visitor film's Blender scripts (people.py, props.py, visitor.py):
colours, materials, boxes and cylinders gathered into meshes, keyframes in bulk.
Imported by those scripts from this folder; Blender's own Python only."""

import math

import bpy


def srgb(h):
    h = h.lstrip("#")
    return [(int(h[i : i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)]


def rgba(h, a=1.0):
    return srgb(h) + [a]


MATS = {}


def principled(name, colour, metal=0.0, rough=0.5, emit=0.0, alpha=1.0, emit_colour=None, coat=0.0, sheen=0.0, trans=0.0):
    """A Principled material, made once per name. `colour` is #rrggbb as seen (sRGB)."""
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgba(colour)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    for k, v in (("Coat Weight", coat), ("Sheen Weight", sheen), ("Transmission Weight", trans)):
        if v and k in b.inputs:
            b.inputs[k].default_value = v
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
    m["colour"] = colour  # as authored, for the report
    MATS[name] = m
    return m


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
    ra, rb = (hi[a] - lo[a]) / 2, (hi[b] - lo[b]) / 2
    k = len(V)
    for end in (lo[i], hi[i]):
        for s in range(n):
            p = [0.0, 0.0, 0.0]
            p[i] = end
            p[a] = c[a] + ra * math.cos(2 * math.pi * s / n)
            p[b] = c[b] + rb * math.sin(2 * math.pi * s / n)
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

    def mesh(self, name, smooth=False):
        return mesh(name, self.V, self.F, self.MI, self.mats, smooth)

    def make(self, name, col, smooth=False):
        if not self.V:
            return None
        ob = bpy.data.objects.new(name, self.mesh(name, smooth))
        col.objects.link(ob)
        return ob


def collection(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    p = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in p.children]:
        p.children.link(c)
    return c


def fcurves(owner):
    """The f-curves of an ID's action, for both the old and the layered (Blender 4.4+) actions."""
    ad = owner.animation_data
    if ad is None or ad.action is None:
        return []
    act = ad.action
    if hasattr(act, "fcurves") and not getattr(act, "is_action_layered", False):
        return list(act.fcurves)
    from bpy_extras.anim_utils import action_ensure_channelbag_for_slot

    return list(action_ensure_channelbag_for_slot(act, ad.action_slot).fcurves)


def action_curves(act):
    """Every f-curve of an action, whichever slot holds it."""
    if hasattr(act, "fcurves") and not getattr(act, "is_action_layered", False):
        return list(act.fcurves)
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out += list(bag.fcurves)
    return out


def fill(owner, data_path, frames, values, constant=False, n=None):
    """Keyframes in bulk on owner.data_path: values is a list of tuples (or numbers), one per frame."""
    if not data_path.startswith("["):
        getattr(owner, data_path)
    owner.keyframe_insert(data_path, frame=frames[0])
    for fc in fcurves(owner):
        if fc.data_path != data_path:
            continue
        i = fc.array_index
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(frames))
        vals = [v[i] if isinstance(v, (tuple, list)) else v for v in values]
        fc.keyframe_points.foreach_set("co", [x for f, v in zip(frames, vals) for x in (f, v)])
        fc.keyframe_points.foreach_set("interpolation", [0 if constant else 1] * len(frames))
        fc.update()


def hold(owner, data_path, pairs):
    """A few constant keys: pairs of (frame, value)."""
    for f, v in pairs:
        setattr(owner, data_path, v)
        owner.keyframe_insert(data_path, frame=f)
    for fc in fcurves(owner):
        if fc.data_path == data_path:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
