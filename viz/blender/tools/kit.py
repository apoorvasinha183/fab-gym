"""Tool models for the 3D fab (docs/FAB-3D.md, step 2), made by script in Blender and exported as glTF. Our own
drawings of generic tool kinds at the sizes the campus uses; no maker's design is copied and no maker is named. From
the SMT2020 testbed; a gigafab-style layout of our own design; not a real fab.

    Blender -b -P viz/blender/tools/scanner.py -- --out data/fab3d/models/scanner.glb

Each model is one mesh, its footprint centred on the origin, standing on z = 0, w along x and d along y (the front,
where wafers come in, at -y). Materials are named so the scene can recolour them: body, panel, accent (the area's
colour), glass, steel, dark, screen, pad, liquid, lamp_green, lamp_amber, lamp_red, foup, foup_copper, rail.
"""

import math
import sys

import bpy

SIZES = {  # w, d, h in metres: the campus's kinds (data/layout-real/scene-optimised.json)
    "metrology": (1.8, 2.8, 2.2), "track": (3.5, 7.0, 2.5), "scanner": (4.5, 11.0, 2.9), "inspection": (2.2, 3.4, 2.3),
    "etch": (3.5, 5.5, 2.6), "deposition": (3.5, 5.5, 2.7), "epitaxy": (4.0, 6.0, 2.8), "furnace": (1.5, 2.0, 3.2),
    "implanter": (3.6, 8.1, 3.1), "polisher": (3.0, 6.0, 2.6), "wet_bench": (2.5, 10.0, 2.8), "stocker": (3.0, 12.0, 5.0),
}
PORTS = {"metrology": 1, "track": 4, "scanner": 4, "inspection": 2, "etch": 2, "deposition": 2, "epitaxy": 2,
         "furnace": 2, "implanter": 2, "polisher": 2, "wet_bench": 2}

COLOURS = {  # base colour, metallic, roughness, extras
    "body": ((0.90, 0.89, 0.86), 0.0, 0.42, {}),
    "panel": ((0.50, 0.54, 0.59), 0.2, 0.45, {}),
    "accent": ((0.08, 0.42, 0.95), 0.0, 0.35, {}),
    "glass": ((0.55, 0.78, 0.90), 0.0, 0.05, {"alpha": 0.28}),
    "steel": ((0.62, 0.64, 0.67), 1.0, 0.28, {}),
    "dark": ((0.10, 0.11, 0.13), 0.2, 0.5, {}),
    "screen": ((0.05, 0.25, 0.45), 0.0, 0.2, {"emit": ((0.25, 0.65, 1.0), 2.0)}),
    "pad": ((0.18, 0.16, 0.20), 0.0, 0.8, {}),
    "liquid": ((0.25, 0.55, 0.85), 0.0, 0.05, {"transmission": 0.6, "alpha": 0.6}),
    "lamp_green": ((0.1, 0.9, 0.3), 0.0, 0.3, {"emit": ((0.1, 1.0, 0.35), 3.0)}),
    "lamp_amber": ((1.0, 0.7, 0.1), 0.0, 0.3, {"emit": ((1.0, 0.65, 0.1), 0.2)}),
    "lamp_red": ((0.9, 0.1, 0.1), 0.0, 0.3, {"emit": ((1.0, 0.1, 0.1), 0.2)}),
    "foup": ((0.30, 0.42, 0.58), 0.0, 0.35, {}),
    "foup_copper": ((0.85, 0.42, 0.12), 0.1, 0.35, {}),
    "rail": ((0.55, 0.57, 0.60), 0.8, 0.35, {}),
    "label_yellow": ((0.98, 0.78, 0.05), 0.0, 0.4, {}),
    "label_red": ((0.85, 0.12, 0.10), 0.0, 0.4, {}),
    "hose": ((0.92, 0.92, 0.90), 0.0, 0.55, {}),
    "cable": ((0.08, 0.08, 0.09), 0.0, 0.6, {}),
    "quartz": ((0.85, 0.90, 0.95), 0.0, 0.05, {"alpha": 0.45}),
}


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    base, metal, rough, extra = COLOURS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*base, 1.0)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    if "transmission" in extra:
        for key in ("Transmission Weight", "Transmission"):
            if key in p.inputs:
                p.inputs[key].default_value = extra["transmission"]
                break
    if "alpha" in extra:
        p.inputs["Alpha"].default_value = extra["alpha"]
        try:
            m.surface_render_method = "BLENDED"
        except (AttributeError, TypeError):
            pass
    if "emit" in extra:
        col, strength = extra["emit"]
        for key in ("Emission Color", "Emission"):
            if key in p.inputs:
                p.inputs[key].default_value = (*col, 1.0)
                break
        p.inputs["Emission Strength"].default_value = strength
    m.diffuse_color = (*base, 1.0)
    return m


PARTS = []


def _take(ob, mat, bevel):
    ob.data.materials.append(material(mat))
    if bevel > 0:
        mod = ob.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    PARTS.append(ob)
    return ob


def box(x, y, z, sx, sy, sz, mat="body", bevel=0.02):
    """A box with its minimum corner at (x, y, z) and size (sx, sy, sz)."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x + sx / 2, y + sy / 2, z + sz / 2))
    ob = bpy.context.active_object
    ob.scale = (sx, sy, sz)
    return _take(ob, mat, min(bevel, sx / 4, sy / 4, sz / 4))


def cyl(x, y, z, r, h, mat="body", axis="z", verts=24, bevel=0.01):
    """A cylinder centred at (x, y) with its base at z (axis z), or lying along x or y centred at (x, y, z)."""
    rot = {"z": (0, 0, 0), "x": (0, math.pi / 2, 0), "y": (math.pi / 2, 0, 0)}[axis]
    loc = (x, y, z + h / 2) if axis == "z" else (x, y, z)
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    return _take(bpy.context.active_object, mat, bevel)


def dome(x, y, z, r, mat="glass"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=r, location=(x, y, z))
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for v in ob.data.vertices:
        v.select = v.co.z < -1e-4
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    return _take(ob, mat, 0)


# ------------------------------------------------------------------ small parts that make a cabinet read as a machine

def handle(x, y, z, length=0.18, facing=-1):
    """A pull handle on a face whose outward side is `facing` along y (-1: the front)."""
    box(x - length / 2, y + (0.0 if facing < 0 else -0.03) - 0.03 * (facing < 0), z, length, 0.03, 0.025, "steel", bevel=0.008)


def grille(x0, y, z0, width, height, facing=-1, slats=7):
    """Ventilation slats on a face at y."""
    box(x0, y - 0.006 * (facing < 0), z0, width, 0.006, height, "dark", bevel=0.0)
    for k in range(slats):
        z = z0 + (k + 0.5) * height / slats
        box(x0 + 0.01, y - 0.016 * (facing < 0) + 0.004 * (facing > 0), z - 0.006, width - 0.02, 0.012, 0.012, "panel", bevel=0.0)


def label(x, y, z, sx=0.12, sz=0.08, mat="label_yellow", facing=-1):
    box(x, y - 0.005 * (facing < 0), z, sx, 0.004, sz, mat, bevel=0.0)


def hatch(x0, y, z0, width, height, facing=-1):
    """A service hatch: a dark seam round a panel, and its handle."""
    box(x0, y - 0.004 * (facing < 0), z0, width, 0.004, height, "dark", bevel=0.0)
    box(x0 + 0.012, y - 0.008 * (facing < 0), z0 + 0.012, width - 0.024, 0.006, height - 0.024, "body", bevel=0.004)
    handle(x0 + width / 2, y - 0.008 * (facing < 0), z0 + height * 0.55, min(0.16, width * 0.4), facing)


def tube(points, r=0.03, mat="hose"):
    """A bent pipe or hose through points (a poly curve with a round bevel), turned into a mesh at build time."""
    cu = bpy.data.curves.new("tube", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for i, (x, y, z) in enumerate(points):
        sp.points[i].co = (x, y, z, 1.0)
    ob = bpy.data.objects.new("tube", cu)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(material(mat))
    PARTS.append(ob)
    return ob


def valve(x, y, z):
    cyl(x, y, z, 0.035, 0.08, "steel", verts=12, bevel=0.005)
    cyl(x, y, z + 0.08, 0.05, 0.02, "label_red", verts=12, bevel=0.0)


def robot_arm(x, y, z, reach=0.35):
    """A wafer-handling robot: a column, two links and a fork."""
    cyl(x, y, z, 0.09, 0.28, "panel", verts=16)
    box(x - 0.05, y - 0.05, z + 0.28, reach, 0.1, 0.06, "body", bevel=0.02)
    box(x + reach - 0.12, y - 0.04, z + 0.34, 0.1, reach * 0.8, 0.05, "body", bevel=0.02)
    box(x + reach - 0.1, y + reach * 0.8 - 0.06, z + 0.36, 0.06, 0.22, 0.01, "steel", bevel=0.0)


def foup(x, y, z, copper=False):
    box(x - 0.213, y - 0.178, z, 0.426, 0.355, 0.338, "foup_copper" if copper else "foup", bevel=0.03)
    box(x - 0.1, y - 0.04, z + 0.338, 0.2, 0.08, 0.04, "dark", bevel=0.01)   # its top flange


def cable_tray(x0, y0, x1, y1, z, width=0.25):
    """A tray of cables along the roof from (x0, y0) to (x1, y1)."""
    lx, ly = abs(x1 - x0), abs(y1 - y0)
    if ly >= lx:
        box(x0 - width / 2, min(y0, y1), z, width, ly, 0.03, "steel", bevel=0.0)
        for k in range(3):
            box(x0 - width / 2 + 0.04 + k * 0.07, min(y0, y1), z + 0.03, 0.05, ly, 0.04, "cable", bevel=0.01)
    else:
        box(min(x0, x1), y0 - width / 2, z, lx, width, 0.03, "steel", bevel=0.0)
        for k in range(3):
            box(min(x0, x1), y0 - width / 2 + 0.04 + k * 0.07, z + 0.03, lx, 0.05, 0.04, "cable", bevel=0.01)


# ------------------------------------------------------------------ shared pieces

def front_module(w, d, h, ports, depth=0.9):
    """The wafer-handling front: a cabinet across the front with load ports, a screen, a lamp tower. Returns its depth."""
    y0 = -d / 2 + 0.34            # the ports' shelves stand in front of the cabinet, inside the footprint
    box(-w / 2, y0, 0, w, depth - 0.34, h * 0.78, "body")
    box(-w / 2 + 0.05, y0 - 0.002, h * 0.78 - 0.18, w - 0.1, 0.02, 0.1, "accent", bevel=0.005)
    pw = min(0.55, (w - 0.3) / max(ports, 1) - 0.08)
    for k in range(ports):
        cx = -w / 2 + (k + 0.5) * w / ports
        box(cx - pw / 2, y0 - 0.32, 0.86, pw, 0.34, 0.06, "steel", bevel=0.01)       # the port's shelf
        box(cx - pw / 2 + 0.03, y0 - 0.02, 0.92, pw - 0.06, 0.03, 0.42, "dark", bevel=0.005)  # its door
    sx = min(0.5, w * 0.25)
    box(w / 2 - sx - 0.12, y0 - 0.015, 1.25, sx, 0.02, 0.32, "screen", bevel=0.005)
    box(w / 2 - sx - 0.12, y0 - 0.02, 1.08, sx, 0.12, 0.03, "dark", bevel=0.005)          # keyboard shelf
    lamp_tower(w / 2 - 0.15, y0 + 0.15, h * 0.78)
    # a window on top into the wafer handler, its robot inside
    box(-w / 2 + 0.15, y0 + 0.1, h * 0.78 - 0.005, w * 0.55, depth - 0.54, 0.01, "glass", bevel=0.0)
    robot_arm(-w / 2 + 0.15 + w * 0.2, y0 + (depth - 0.34) / 2 - 0.1, h * 0.78 - 0.45, reach=min(0.35, w * 0.12))
    foup(-w / 2 + 0.5 * w / ports, y0 - 0.15, 0.92)                                        # a carrier waiting on the first port
    grille(-w / 2 + 0.1, y0, 0.15, min(0.6, w * 0.3), 0.5)
    label(-w / 2 + 0.12, y0, h * 0.78 - 0.32)
    label(-w / 2 + 0.28, y0, h * 0.78 - 0.32, mat="label_red", sx=0.06)
    for k in range(ports):
        cx = -w / 2 + (k + 0.5) * w / ports
        handle(cx, y0 - 0.02, 0.72)
    return depth


def lamp_tower(x, y, z):
    cyl(x, y, z, 0.025, 0.12, "steel", verts=12)
    for k, m in enumerate(("lamp_red", "lamp_amber", "lamp_green")):
        cyl(x, y, z + 0.12 + k * 0.07, 0.04, 0.065, m, verts=16, bevel=0.005)


def windows(x0, x1, y, z0, z1, n, mat="glass"):
    gap = 0.08
    wd = (x1 - x0 - gap * (n + 1)) / n
    for k in range(n):
        box(x0 + gap + k * (wd + gap), y - 0.01, z0, wd, 0.02, z1 - z0, mat, bevel=0.005)


def stripe(w, d, z, inset=0.0, front=0.34):
    """The area's colour as a band round the body, standing 5 mm proud of it; it starts behind the load ports."""
    box(-w / 2 + inset - 0.005, -d / 2 + front + inset - 0.005, z, w - 2 * inset + 0.01, d - front - 2 * inset + 0.01, 0.06, "accent", bevel=0.004)


# ------------------------------------------------------------------ the kinds

def scanner(w, d, h):
    fd = front_module(w, d, h, PORTS["scanner"])
    y0 = -d / 2 + fd
    box(-w / 2, y0, 0, w, d - fd, h * 0.86, "body", bevel=0.05)
    box(-w / 2 + 0.6, y0 + 1.2, h * 0.86, w - 1.2, (d - fd) * 0.45, h * 0.14, "panel", bevel=0.04)  # the optics housing
    stripe(w, d, h * 0.62)
    for side in (-1, 1):
        box(side * w / 2 - (0.01 if side > 0 else 0.0) - (0 if side > 0 else 0.0), y0 + 0.5, 0.9, 0.02, d - fd - 1.0, 0.7, "glass", bevel=0.005)
    box(-w / 2 + 0.3, d / 2 - 1.6, 0.0, w - 0.6, 1.4, h * 0.5, "panel", bevel=0.03)                # the stage cabinet
    box(-w / 2 + 0.7, y0 + 0.4, h * 0.86, 1.2, 0.9, 0.35, "body", bevel=0.04)                       # the mask library
    label(-w / 2 + 0.75, y0 + 0.39, h * 0.86 + 0.2, sx=0.2, sz=0.05)
    for k in range(4):                                                                             # its cooling hoses
        x = w / 2 - 0.9 + k * 0.12
        tube([(x, y0 + 1.5, h * 0.86), (x, y0 + 1.5, h + 0.05), (x, d / 2 - 1.8, h + 0.05), (x, d / 2 - 1.8, h * 0.5)], r=0.025)


def track(w, d, h):
    fd = front_module(w, d, h, PORTS["track"])
    y0 = -d / 2 + fd
    box(-w / 2, y0, 0, w, d - fd, h * 0.7, "body", bevel=0.04)
    box(-w / 2 + 0.1, y0 + 0.1, h * 0.7, w - 0.2, d - fd - 0.2, 0.02, "glass", bevel=0.005)
    for k in range(4):
        cx = -w / 4 if k % 2 == 0 else w / 4
        cy = y0 + 0.9 + (k // 2) * 1.7
        cyl(cx, cy, h * 0.55, 0.42, 0.14, "steel")        # a coater bowl
        cyl(cx, cy, h * 0.55 + 0.1, 0.16, 0.05, "dark")
    for k in range(3):
        box(-w / 2 + 0.25, d / 2 - 1.9 + k * 0.55, h * 0.7, 0.9, 0.45, 0.55, "panel", bevel=0.02)  # hot plates
    robot_arm(0.0, y0 + 2.6, h * 0.5, reach=0.4)
    box(w / 2 - 1.0, d / 2 - 1.2, 0.1, 0.8, 1.0, 0.9, "panel", bevel=0.02)                       # chemical cabinet
    for k in range(4):
        cyl(w / 2 - 0.85 + k * 0.17, d / 2 - 1.35, 0.95, 0.06, 0.18, ("label_yellow", "liquid", "label_red", "liquid")[k], verts=12)
    stripe(w, d, h * 0.45)


def cluster(w, d, h, chamber_mat="steel", domes=False):
    fd = front_module(w, d, h, 2)
    y0 = -d / 2 + fd
    cy = y0 + (d - fd) * 0.42
    r = min(w, d - fd) * 0.2
    cyl(0, cy, 0, r, h * 0.62, "panel", verts=8, bevel=0.03)                 # the transfer chamber
    cyl(0, cy, h * 0.62, r * 0.9, 0.06, "glass", verts=8, bevel=0.005)
    box(-0.25, y0, h * 0.25, 0.5, cy - y0 - r * 0.8, 0.35, "panel", bevel=0.02)  # load lock
    for k, ang in enumerate((-60, 0, 60, 180)):
        if ang == 180 and d - fd < 4.0:
            continue
        a = math.radians(ang + 90)
        px, py = math.cos(a) * r * 2.0, cy + math.sin(a) * r * 2.0
        if ang == 180:
            continue
        cyl(px, py, 0, r * 0.75, h * 0.7, chamber_mat, verts=20, bevel=0.03)   # a process chamber
        if domes:
            dome(px, py, h * 0.7, r * 0.6)
        else:
            cyl(px, py, h * 0.7, r * 0.55, 0.12, "steel", verts=20)
        tube([(px, py, h * 0.7 + 0.1), (px, py, h * 0.95), (px * 0.5, d / 2 - 1.0, h * 0.95), (px * 0.5, d / 2 - 1.0, h * 0.8)], r=0.03)  # its gas and RF line
        valve(px + r * 0.5, py, h * 0.7)
        label(px - 0.05, py - r * 0.75 - 0.004, h * 0.4, sx=0.1, sz=0.07)
    box(-w / 2, d / 2 - 1.0, 0, w, 1.0, h, "body", bevel=0.04)                  # gas and power cabinet
    windows(-w / 2 + 0.1, w / 2 - 0.1, d / 2 - 1.0, 1.0, 1.8, 3, "panel")
    box(-w / 2 - 0.005, d / 2 - 1.005, h * 0.8, w + 0.01, 1.01, 0.06, "accent", bevel=0.004)
    box(-w / 2 + 0.05, y0, 0, w - 0.1, d - fd - 1.0, 0.35, "panel", bevel=0.03)  # the frame the chambers stand on
    for side in (-1, 1):                                                         # its railings
        box(side * (w / 2 - 0.08) - 0.02, y0 + 0.1, 0.35, 0.04, d - fd - 1.2, 0.04, "steel", bevel=0.005)


def etch(w, d, h):
    cluster(w, d, h, "steel")


def deposition(w, d, h):
    cluster(w, d, h, "panel")


def epitaxy(w, d, h):
    cluster(w, d, h, "steel", domes=True)


def furnace(w, d, h):
    box(-w / 2, -d / 2, 0, w, d, h, "body", bevel=0.04)
    box(-w / 2 + 0.2, -d / 2 - 0.01, 0.4, w - 0.4, 0.02, h - 0.9, "glass", bevel=0.005)
    cyl(0, -d / 2 + 0.45, 0.45, 0.22, h - 1.1, "quartz", verts=20)           # the quartz tube inside
    for k in range(10):
        cyl(0, -d / 2 + 0.45, 0.6 + k * (h - 1.5) / 10, 0.2, 0.012, "steel", verts=20, bevel=0.0)  # wafers in the boat
    for k in range(3):
        cyl(w / 2 - 0.3, d / 2 - 0.3, h + 0.02 + k * 0.0, 0.07, 0.15, "steel", verts=12)
    tube([(w / 2 - 0.3, d / 2 - 0.3, h + 0.15), (w / 2 - 0.3, d / 2 - 0.3, h + 0.3), (-w / 2 + 0.3, d / 2 - 0.3, h + 0.3)], r=0.04, mat="steel")
    label(-w / 2 + 0.25, -d / 2 - 0.004, 2.5, sx=0.2, sz=0.1)
    hatch(-w / 2 + 0.2, -d / 2, 0.08, w - 0.4, 0.28)
    box(-w / 2, -d / 2, h - 0.35, w, d, 0.35, "panel", bevel=0.03)            # heater head
    stripe(w, d, h - 0.45, front=0.0)
    box(w / 2 - 0.45, -d / 2 - 0.015, 1.3, 0.3, 0.02, 0.22, "screen", bevel=0.005)
    lamp_tower(w / 2 - 0.12, -d / 2 + 0.12, h)


def implanter(w, d, h):
    fd = front_module(w, d, h, PORTS["implanter"])
    y0 = -d / 2 + fd
    box(-w / 2, y0, 0, w * 0.55, 2.0, h * 0.75, "body", bevel=0.04)             # end station
    cyl(-w / 2 + w * 0.3, y0 + 3.2, 1.3, 0.22, 2.6, "steel", axis="y")          # beam tube
    box(-w / 2 + 0.1, y0 + 4.2, 0, w * 0.75, 1.5, h * 0.8, "accent", bevel=0.06)  # analyser magnet
    box(-w / 2, d / 2 - 1.8, 0, w, 1.8, h, "body", bevel=0.05)                  # ion source and its cabinet
    windows(-w / 2 + 0.1, w / 2 - 0.1, d / 2 - 1.8, 1.0, 2.0, 3)
    box(w / 2 - 1.3, y0 + 0.3, 0, 1.2, d - fd - 2.3, 1.1, "panel", bevel=0.03)  # power rack
    lamp_tower(-w / 2 + 0.2, y0 + 0.2, h * 0.75)
    for k in range(5):                                                          # insulator stacks under the source
        cyl(-w / 2 + 0.6 + k * 0.55, d / 2 - 2.1, 0, 0.12, 0.9, "body", verts=14)
        for j in range(4):
            cyl(-w / 2 + 0.6 + k * 0.55, d / 2 - 2.1, 0.15 + j * 0.2, 0.16, 0.04, "panel", verts=14)
    label(-w / 2 + 0.2, d / 2 - 1.805, 1.6, sx=0.3, sz=0.2)                      # high voltage
    label(-w / 2 + 0.55, d / 2 - 1.805, 1.6, sx=0.08, sz=0.2, mat="label_red")
    tube([(w / 2 - 0.7, y0 + 1.0, 1.1), (w / 2 - 0.7, y0 + 1.0, 2.6), (-w / 2 + 0.6, d / 2 - 2.0, 2.6), (-w / 2 + 0.6, d / 2 - 2.0, h)], r=0.04, mat="cable")


def polisher(w, d, h):
    fd = front_module(w, d, h, PORTS["polisher"])
    y0 = -d / 2 + fd
    box(-w / 2, y0, 0, w, d - fd, 0.9, "body", bevel=0.04)
    box(-w / 2, y0, 0.9, 0.04, d - fd, h - 0.9, "glass", bevel=0.005)
    box(w / 2 - 0.04, y0, 0.9, 0.04, d - fd, h - 0.9, "glass", bevel=0.005)
    box(-w / 2, y0 + d - fd - 0.04, 0.9, w, 0.04, h - 0.9, "glass", bevel=0.005)
    box(-w / 2, y0, h - 0.06, w, d - fd, 0.06, "panel", bevel=0.01)
    n = 3
    for k in range(n):
        cy = y0 + 0.9 + k * (d - fd - 1.4) / (n - 1)
        cyl(-0.3, cy, 0.9, 0.62, 0.08, "pad", verts=32)                         # a platen
        box(-0.3, cy - 0.04, 1.2, 1.1, 0.08, 0.06, "steel", bevel=0.01)           # its arm
        cyl(0.8, cy, 0.95, 0.08, 0.3, "steel", verts=12)
        cyl(0.15, cy + 0.25, 0.98, 0.14, 0.05, "panel", verts=16)                 # pad conditioner
        tube([(-1.0, cy - 0.3, 1.5), (-0.6, cy - 0.3, 1.3), (-0.4, cy - 0.1, 1.05)], r=0.012, mat="hose")  # slurry line
        cyl(-0.4, cy - 0.1, 1.0, 0.02, 0.06, "label_yellow", verts=8)
    stripe(w, d, 0.82)
    box(-w / 2 + 0.2, d / 2 - 0.8, 0.0, w - 0.4, 0.6, 0.85, "panel", bevel=0.02)   # slurry supply
    for k in range(3):
        valve(-w / 2 + 0.5 + k * 0.4, d / 2 - 0.5, 0.85)


def wet_bench(w, d, h):
    box(-w / 2, -d / 2, 0, w, d, 0.95, "body", bevel=0.04)
    n = 6
    for k in range(n):
        cy = -d / 2 + 0.6 + k * (d - 1.2) / n
        box(-w / 2 + 0.35, cy + 0.08, 0.7, w - 1.0, (d - 1.2) / n - 0.16, 0.25, "liquid", bevel=0.01)
    box(w / 2 - 0.55, -d / 2, 0, 0.55, d, h, "panel", bevel=0.03)              # exhaust and plumbing wall
    box(-w / 2, -d / 2, h - 0.25, w, d, 0.25, "body", bevel=0.03)               # hood
    for side in (-1, 1):
        box(-w / 2, side * (d / 2) - (0.04 if side > 0 else 0), 0.95, w - 0.55, 0.04, h - 1.2, "glass", bevel=0.005)
    box(-w / 2 + 0.2, -d / 2 + 0.1, h - 0.45, 0.12, d - 0.2, 0.08, "steel", bevel=0.01)  # robot rail
    box(-w / 2 + 0.15, -d / 2 + 2.0, h - 0.9, 0.3, 0.3, 0.45, "steel", bevel=0.02)       # robot
    box(-w / 2 + 0.2, -d / 2 + 2.1, h - 1.25, 0.2, 0.08, 0.35, "steel", bevel=0.01)       # its gripper
    for k in range(6):                                                                     # drain lines under the tanks
        cy = -d / 2 + 0.6 + (k + 0.5) * (d - 1.2) / 6
        tube([(-w / 2 + 0.8, cy, 0.7), (-w / 2 + 0.8, cy, 0.2), (w / 2 - 0.55, cy, 0.2)], r=0.03, mat="steel")
        label(-w / 2 - 0.004, cy - 0.06, 0.55, sx=0.004, sz=0.08) if False else None
    grille(-w / 2 + 0.6, -d / 2, 0.15, 0.8, 0.4)
    stripe(w, d, 0.85, front=0.0)
    box(-w / 2 + 0.3, -d / 2 - 0.015, 1.2, 0.4, 0.02, 0.28, "screen", bevel=0.005)
    lamp_tower(w / 2 - 0.25, -d / 2 + 0.2, h)


def metrology(w, d, h):
    front_module(w, d, h, PORTS["metrology"], depth=0.7)
    box(-w / 2, -d / 2 + 0.7, 0, w, d - 0.7, h * 0.8, "body", bevel=0.04)
    box(-w / 2 - 0.005, -d / 2 + 1.0, 1.0, 0.02, d - 1.4, 0.6, "glass", bevel=0.005)
    dome(0, d / 4, h * 0.8, min(w, d) * 0.22, "panel")
    box(w / 2 - 0.05, -d / 2 + 0.9, 1.1, 0.04, 0.5, 0.35, "screen", bevel=0.005)         # side monitor
    tube([(w / 2 - 0.03, -d / 2 + 1.15, 1.1), (w / 2 + 0.0, -d / 2 + 1.15, 0.9), (w / 2 - 0.05, -d / 2 + 1.3, 0.9)], r=0.015, mat="steel")
    hatch(-w / 2 + 0.15, -d / 2 + 0.34, 0.15, 0.5, 0.45)
    stripe(w, d, h * 0.7)


def inspection(w, d, h):
    front_module(w, d, h, PORTS["inspection"], depth=0.8)
    box(-w / 2, -d / 2 + 0.8, 0, w, d - 0.8, h * 0.75, "body", bevel=0.04)
    box(-w / 2 + 0.15, -d / 2 + 1.0, h * 0.75, w - 0.3, d - 1.2, 0.08, "steel", bevel=0.01)  # gantry rails
    box(-0.25, 0.0, h * 0.75, 0.5, 0.5, h * 0.25, "panel", bevel=0.03)                     # optics head
    cyl(0, 0.25, h * 0.75 - 0.25, 0.08, 0.25, "dark", verts=16)
    for x in (-w / 2 + 0.2, w / 2 - 0.2):                                                    # gantry posts
        box(x - 0.05, -d / 2 + 1.0, h * 0.75, 0.1, 0.1, 0.25, "steel", bevel=0.01)
    box(-w / 2 + 0.15, -d / 2 + 1.0, h * 0.75 + 0.2, w - 0.3, 0.12, 0.08, "steel", bevel=0.01)
    stripe(w, d, h * 0.6)


def stocker(w, d, h):
    box(-w / 2, -d / 2, 0, w, d, 0.3, "panel", bevel=0.02)
    box(-w / 2, -d / 2, h - 0.3, w, d, 0.3, "body", bevel=0.03)
    for side in (-1, 1):
        box(-w / 2, side * d / 2 - (0.12 if side > 0 else 0), 0, w, 0.12, h, "body", bevel=0.02)
    for k in range(6):
        y = -d / 2 + 0.12 + k * (d - 0.24) / 6
        box(-w / 2, y, 0.3, w, 0.06, h - 0.6, "steel", bevel=0.005)
    rows, cols = 8, 12
    for r in range(rows):
        z = 0.45 + r * (h - 0.9) / rows
        box(-w / 2 + 0.05, -d / 2 + 0.15, z - 0.04, w - 0.1, d - 0.3, 0.03, "steel", bevel=0.0)  # a shelf
        for c in range(cols):
            if (r * 7 + c * 3) % 5 == 0:
                continue
            y = -d / 2 + 0.3 + c * (d - 0.6) / cols
            box(-0.25, y, z, 0.43, 0.36, 0.34, "foup", bevel=0.02)
    for side in (-1, 1):
        box(side * w / 2 - 0.01, -d / 2 + 0.12, 0.3, 0.02, d - 0.24, h - 0.6, "glass", bevel=0.0)
    box(-w / 2 + 0.2, -d / 2 - 0.015, 1.3, 0.5, 0.02, 0.3, "screen", bevel=0.005)
    box(-0.15, -d / 2 + 0.6, 0.3, 0.3, 0.3, h - 0.6, "steel", bevel=0.02)                    # the crane's mast
    box(-0.4, -d / 2 + 0.55, 1.8, 0.8, 0.4, 0.25, "panel", bevel=0.02)                       # its carriage
    for k in range(3):                                                                       # ports in the roof for the rail
        box(-0.35, -d / 2 + 2.0 + k * 3.5, h - 0.02, 0.7, 0.6, 0.04, "dark", bevel=0.0)
    lamp_tower(w / 2 - 0.2, -d / 2 + 0.2, h)


def carrier(copper):
    # the overhead vehicle: body under the rail, gripper, a carrier box (FOUP) below
    box(-0.45, -0.3, 0.45, 0.9, 0.6, 0.35, "body", bevel=0.04)
    box(-0.46, -0.31, 0.62, 0.92, 0.62, 0.05, "foup_copper" if copper else "accent", bevel=0.01)
    box(-0.12, -0.1, 0.8, 0.24, 0.2, 0.1, "steel", bevel=0.01)               # the wheels' carriage
    box(-0.3, -0.25, 0.36, 0.6, 0.5, 0.06, "steel", bevel=0.01)              # gripper
    box(-0.213, -0.178, 0.0, 0.426, 0.355, 0.338, "foup_copper" if copper else "foup", bevel=0.03)
    box(-0.16, -0.18, 0.31, 0.32, 0.03, 0.04, "dark", bevel=0.005)


def details(w, d, h):
    """What makes a cabinet read as a machine: a dark kick plate, panel seams down both long sides, levelling feet,
    exhaust stubs at the back of the roof."""
    box(-w / 2 - 0.004, -d / 2 + 0.36, 0, w + 0.008, d - 0.36, 0.1, "dark", bevel=0.005)
    n = max(2, int((d - 0.4) / 1.1))
    for k in range(1, n):
        y = -d / 2 + 0.36 + k * (d - 0.36) / n
        for side in (-1, 1):
            box(side * (w / 2 + 0.002) - 0.006, y - 0.006, 0.1, 0.012, 0.012, h * 0.7, "dark", bevel=0.0)
    for x in (-w / 2 + 0.25, w / 2 - 0.25):
        cyl(x, d / 2 - 0.35, h * 0.86 - 0.01, 0.11, 0.28, "steel", verts=16)
        cyl(x, d / 2 - 0.35, h * 0.86 + 0.27, 0.13, 0.04, "dark", verts=16)
    cable_tray(w / 2 - 0.45, -d / 2 + 1.0, w / 2 - 0.45, d / 2 - 0.6, h * 0.86)
    for k in range(3):                                                          # gas lines with valves down the roof
        x = -w / 2 + 0.35 + k * 0.12
        tube([(x, -d / 2 + 1.1, h * 0.86 + 0.05), (x, d / 2 - 0.7, h * 0.86 + 0.05), (x, d / 2 - 0.5, h * 0.86 + 0.25)], r=0.018, mat="steel")
        valve(x, -d / 2 + 1.6 + k * 0.4, h * 0.86 + 0.06)
    for side in (-1, 1):                                                        # service hatches down the long sides
        n = max(1, int((d - 1.6) / 1.6))
        for k in range(n):
            y = -d / 2 + 1.1 + k * (d - 1.6) / n
            xface = side * (w / 2)
            hy = (d - 1.6) / n - 0.15
            box(xface + 0.001 * side - 0.002, y, 0.25, 0.004, hy, h * 0.55, "dark", bevel=0.0)              # the seam
            box(xface + 0.004 * side - 0.002, y + 0.012, 0.262, 0.004, hy - 0.024, h * 0.55 - 0.024, "body", bevel=0.0)  # the door
            box(xface + 0.012 * side - 0.006, y + hy * 0.4, 0.25 + h * 0.3, 0.012, 0.16, 0.025, "steel", bevel=0.004)  # its handle


KINDS = {"scanner": scanner, "track": track, "etch": etch, "deposition": deposition, "epitaxy": epitaxy,
         "furnace": furnace, "implanter": implanter, "polisher": polisher, "wet_bench": wet_bench,
         "metrology": metrology, "inspection": inspection, "stocker": stocker}


def build(name):
    clear()
    PARTS.clear()
    if name in KINDS:
        w, d, h = SIZES[name]
        KINDS[name](w, d, h)
        if name not in ("stocker", "furnace", "etch", "deposition", "epitaxy", "wet_bench", "polisher"):
            details(w, d, h)
    elif name in ("carrier_standard", "carrier_copper"):
        carrier(name == "carrier_copper")
    else:
        raise SystemExit(f"unknown model {name}")
    # apply every modifier and transform, then join: one mesh, its vertices where they stand
    bpy.ops.object.select_all(action="DESELECT")
    for i, ob in enumerate(list(PARTS)):
        if ob.type == "CURVE":
            bpy.ops.object.select_all(action="DESELECT")
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            bpy.ops.object.convert(target="MESH")
            PARTS[i] = bpy.context.active_object
    bpy.ops.object.select_all(action="DESELECT")
    for ob in PARTS:
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        for mod in list(ob.modifiers):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    for ob in PARTS:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = PARTS[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    ob.data.name = name
    bpy.ops.object.shade_auto_smooth() if hasattr(bpy.ops.object, "shade_auto_smooth") else None
    return ob


def export(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_yup=True, export_apply=True,
                              export_materials="EXPORT")


def main(name):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1] if "--out" in argv else f"data/fab3d/models/{name}.glb"
    ob = build(name)
    export(out)
    xs = [v.co.x for v in ob.data.vertices]
    ys = [v.co.y for v in ob.data.vertices]
    zs = [v.co.z for v in ob.data.vertices]
    print(f"{name}: {max(xs) - min(xs):.3f} x {max(ys) - min(ys):.3f} x {max(zs) - min(zs):.3f} m, "
          f"{len(ob.data.polygons)} faces, {len(ob.data.materials)} materials -> {out}")
