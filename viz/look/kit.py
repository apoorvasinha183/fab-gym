"""The model kit for the realistic fab (docs/FAB-LOOK.md): every tool kind, the carrier and the
hoist car as parts (boxes and cylinders) at the sizes of viz/look/sizes.json. Blender and Godot
both build their meshes from these parts, so the two views show the same models.

A gigafab-style layout of our own design from the SMT2020 testbed; the shapes are generic and of our
own design, after no maker's tool.

Frame of a tool: x along the bay wall (its width W), y into the bay from the aisle (its depth D;
the aisle face is y = 0), z up from the raised floor. The status light stands on top and is left
out of the tool's size.

    python3 viz/look/kit.py OUT.json     writes every model as parts, for the 3D builds
"""

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIZES = json.loads((HERE / "sizes.json").read_text())
KINDS = {k["kind"]: k for k in SIZES["kinds"]}

# materials: name -> (base colour as hex, metallic, roughness, emission strength, alpha)
MATERIALS = {
    "panel": ("e9edf1", 0.0, 0.45, 0.0, 1.0),        # painted steel skin, off-white
    "panel_grey": ("b9c0c8", 0.0, 0.5, 0.0, 1.0),
    "trim": ("5b6672", 0.3, 0.4, 0.0, 1.0),          # seams, kick plates, frames
    "steel": ("c7ccd1", 1.0, 0.25, 0.0, 1.0),        # brushed stainless
    "dark": ("2a2f36", 0.2, 0.5, 0.0, 1.0),
    "glass": ("a9c6d8", 0.0, 0.05, 0.0, 0.28),
    "screen": ("1d3b5a", 0.0, 0.2, 1.2, 1.0),
    "rubber": ("1b1d20", 0.0, 0.8, 0.0, 1.0),
    "warning": ("f2c230", 0.0, 0.5, 0.0, 1.0),
    "copper": ("b87333", 1.0, 0.35, 0.0, 1.0),
    "pipe": ("d7dbe0", 0.9, 0.3, 0.0, 1.0),
    "cable": ("3c4a5c", 0.0, 0.6, 0.0, 1.0),
    "quartz": ("f3efe4", 0.0, 0.1, 0.0, 0.6),
    "led_red": ("ff3b30", 0.0, 0.3, 4.0, 1.0),
    "led_amber": ("ffb020", 0.0, 0.3, 4.0, 1.0),
    "led_green": ("34c759", 0.0, 0.3, 4.0, 1.0),
    "led_blue": ("4aa3ff", 0.0, 0.3, 3.0, 1.0),
    "foup_shell": ("3a3f45", 0.0, 0.3, 0.0, 0.85),
    "foup_door": ("d9dde1", 0.0, 0.4, 0.0, 1.0),
    "rail": ("aeb7c2", 1.0, 0.3, 0.0, 1.0),
    "vehicle": ("f1f3f5", 0.1, 0.35, 0.0, 1.0),
}


def kind_of(group):
    """The kind of a tool group, by the first prefix its name starts with."""
    for k in SIZES["kinds"]:
        if any(group.startswith(p) for p in k["prefixes"]):
            return k["kind"]
    return None


# ---------------------------------------------------------------------------------- parts

class Parts(list):
    def box(self, name, x0, y0, z0, x1, y1, z1, mat, role="detail"):
        lo = [min(x0, x1), min(y0, y1), min(z0, z1)]
        hi = [max(x0, x1), max(y0, y1), max(z0, z1)]
        self.append({"name": name, "shape": "box", "min": [round(v, 5) for v in lo], "max": [round(v, 5) for v in hi], "mat": mat, "role": role})

    def cyl(self, name, cx, cy, cz, r, length, mat, axis="z", role="detail"):
        """A cylinder of radius r, `length` long along `axis`, starting at (cx, cy, cz) on that axis."""
        c = [cx, cy, cz]
        lo = [cx - r, cy - r, cz - r]
        hi = [cx + r, cy + r, cz + r]
        i = "xyz".index(axis)
        lo[i], hi[i] = c[i], c[i] + length
        self.append({"name": name, "shape": "cyl", "axis": axis, "min": [round(v, 5) for v in lo], "max": [round(v, 5) for v in hi], "mat": mat, "role": role})


def cabinet(p, name, x0, y0, x1, y1, h, mat="panel", doors=2, seams=True):
    """A skinned cabinet with a kick plate, a top cap and door seams on its aisle face."""
    p.box(name, x0, y0 + 0.02, 0.10, x1, y1, h - 0.04, mat, "body")
    p.box(name + " kick", x0 + 0.02, y0 + 0.05, 0.0, x1 - 0.02, y1 - 0.03, 0.10, "trim", "body")
    p.box(name + " cap", x0, y0 + 0.02, h - 0.04, x1, y1, h, "trim", "body")
    if seams and doors > 1:
        for i in range(1, doors):
            x = x0 + (x1 - x0) * i / doors
            p.box(f"{name} seam {i}", x - 0.006, y0, 0.12, x + 0.006, y0 + 0.022, h - 0.06, "trim")
    if seams:
        for i in range(doors):
            xa = x0 + (x1 - x0) * i / doors
            xb = x0 + (x1 - x0) * (i + 1) / doors
            p.box(f"{name} handle {i}", xb - 0.09, y0 - 0.01, h * 0.45, xb - 0.06, y0 + 0.02, h * 0.45 + 0.25, "steel")
            p.box(f"{name} vent {i}", xa + 0.08, y0 + 0.005, 0.2, xb - 0.12, y0 + 0.02, 0.32, "dark")


def ports(p, n, x0, x1, kind):
    """n load ports along the aisle face between x0 and x1, the carrier's seat at 0.9 m."""
    seat = SIZES["port_seat"]
    if n == 0:
        return
    pitch = (x1 - x0) / n
    for i in range(n):
        cx = x0 + pitch * (i + 0.5)
        w = min(0.5, pitch - 0.04)
        p.box(f"load port {i}", cx - w / 2, 0.0, 0.0, cx + w / 2, 0.45, seat, "panel_grey", "port")
        p.box(f"load port {i} stage", cx - 0.22, 0.02, seat - 0.03, cx + 0.22, 0.43, seat - 0.005, "dark")
        p.box(f"load port {i} kinematic pin", cx - 0.02, 0.2, seat - 0.005, cx + 0.02, 0.24, seat, "steel")
        p.box(f"load port {i} door plate", cx - 0.2, 0.44, seat, cx + 0.2, 0.47, seat + 0.36, "panel_grey")
        p.box(f"load port {i} badge", cx - 0.1, -0.005, seat - 0.2, cx + 0.1, 0.0, seat - 0.12, "led_blue")
        p.box(f"load port {i} kick", cx - w / 2 + 0.03, 0.03, 0.0, cx + w / 2 - 0.03, 0.42, 0.06, "trim")


def efem(p, x0, x1, depth, h, n_ports, kind):
    """The front end every tool has: ports, a window onto the robot, and a filter on top."""
    p.box("front end", x0, 0.45, 0.10, x1, 0.45 + depth, h - 0.35, "panel", "body")
    p.box("front end base", x0 + 0.02, 0.47, 0.0, x1 - 0.02, 0.45 + depth - 0.02, 0.10, "trim", "body")
    p.box("front end filter", x0, 0.45, h - 0.35, x1, 0.45 + depth, h - 0.05, "panel_grey", "body")
    p.box("front end window", x0 + 0.08, 0.44, 1.35, x1 - 0.08, 0.455, h - 0.55, "glass")
    p.box("front end robot track", x0 + 0.1, 0.55, 0.95, x1 - 0.1, 0.65, 1.0, "steel")
    p.cyl("front end robot", (x0 + x1) / 2, 0.75, 1.0, 0.12, 0.45, "steel")
    p.box("front end robot arm", (x0 + x1) / 2 - 0.03, 0.62, 1.4, (x0 + x1) / 2 + 0.03, 0.95, 1.45, "steel")
    ports(p, n_ports, x0 + 0.05, x1 - 0.05, kind)


def screen(p, x, h, y=0.45):
    """An operator screen on an arm at the aisle face, and a keyboard shelf."""
    p.box("screen arm", x - 0.02, y - 0.25, h - 0.95, x + 0.02, y, h - 0.9, "steel")
    p.box("screen", x - 0.24, y - 0.3, h - 1.15, x + 0.24, y - 0.26, h - 0.82, "dark")
    p.box("screen glass", x - 0.22, y - 0.305, h - 1.13, x + 0.22, y - 0.3, h - 0.84, "screen")
    p.box("keyboard shelf", x - 0.22, y - 0.42, h - 1.55, x + 0.22, y - 0.2, h - 1.53, "trim")
    p.box("keyboard", x - 0.19, y - 0.4, h - 1.53, x + 0.19, y - 0.26, h - 1.51, "dark")


def light(p, x, y, h):
    """The status light tower, 0.6 m tall: a pole and four lamps, green (productive), amber
    (standby), blue (scheduled down) and red (unscheduled down)."""
    L = SIZES["status_light"]
    p.cyl("light pole", x, y, h, 0.018, L * 0.3, "steel", role="light")
    for i, c in enumerate(("green", "amber", "blue", "red")):
        p.cyl(f"light {c}", x, y, h + L * (0.3 + 0.175 * i), 0.035, L * 0.175, f"led_{c}", role="light")


def back_services(p, W, D, h, n=4):
    """Pipes and cables at the back of a tool, running down into the raised floor."""
    for i in range(n):
        x = W * (i + 1) / (n + 1)
        p.cyl(f"service pipe {i}", x, D - 0.12, 0.0, 0.035, h * 0.8, "pipe")
        p.cyl(f"service elbow {i}", x, D - 0.12, h * 0.8 - 0.035, 0.035, 0.1, "pipe", axis="y")
    p.box("cable tray", 0.15, D - 0.32, h * 0.86, W - 0.15, D - 0.04, h * 0.88, "trim")
    for i in range(3):
        p.cyl(f"cable {i}", 0.2, D - 0.28 + i * 0.08, h * 0.88, 0.02, W - 0.4, "cable", axis="x")
    p.box("rear nameplate", W * 0.4, D - 0.02, 1.5, W * 0.6, D, 1.62, "trim")


def warnings(p, W, z, y=-0.003):
    for i, x in enumerate((0.25, W - 0.45)):
        p.box(f"warning label {i}", x, y, z, x + 0.18, y + 0.004, z + 0.12, "warning")


def frame(p, name, x0, y0, z0, x1, y1, z1, t=0.05, mat="trim"):
    """An open frame of twelve edges."""
    for zz in (z0, z1 - t):
        p.box(f"{name} rail a {zz:.2f}", x0, y0, zz, x1, y0 + t, zz + t, mat)
        p.box(f"{name} rail b {zz:.2f}", x0, y1 - t, zz, x1, y1, zz + t, mat)
        p.box(f"{name} rail c {zz:.2f}", x0, y0, zz, x0 + t, y1, zz + t, mat)
        p.box(f"{name} rail d {zz:.2f}", x1 - t, y0, zz, x1, y1, zz + t, mat)
    for x, y in ((x0, y0), (x1 - t, y0), (x0, y1 - t), (x1 - t, y1 - t)):
        p.box(f"{name} post {x:.2f} {y:.2f}", x, y, z0, x + t, y + t, z1, mat)


# ---------------------------------------------------------------------------------- tools

def scanner():
    k = KINDS["scanner"]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    efem(p, 0.0, W, 1.2, 2.4, k["ports"], "scanner")
    cabinet(p, "wafer handler", 0.0, 1.65, W, 3.6, 2.5, doors=3)
    cabinet(p, "wafer stage", 0.0, 3.6, W, 8.2, 2.6, doors=4)
    p.box("stage base frame", 0.1, 3.7, 0.0, W - 0.1, 8.1, 0.18, "dark", "body")
    # the projection lens column rises through the roof of the stage cabinet
    p.cyl("lens housing", W / 2, 5.9, 2.6, 0.7, H - 2.6 - 0.05, "panel_grey", role="body")
    p.cyl("lens housing cap", W / 2, 5.9, H - 0.05, 0.72, 0.05, "trim", role="body")
    for i in range(6):
        a = i * math.pi / 3
        p.cyl(f"lens stud {i}", W / 2 + 0.62 * math.cos(a), 5.9 + 0.62 * math.sin(a), 2.6, 0.05, 0.25, "steel")
    p.box("reticle stage housing", W / 2 - 1.0, 4.9, 2.6, W / 2 + 1.0, 5.3, 2.85, "panel_grey", "body")
    cabinet(p, "illuminator", 0.0, 8.2, W, D, 2.4, mat="panel_grey", doors=3)
    p.box("beam delivery duct", W - 0.8, 8.4, 2.4, W - 0.3, D - 0.3, 2.75, "steel", "body")
    p.box("side window", -0.003, 4.2, 1.1, 0.0, 7.6, 2.1, "glass")
    p.box("side window frame top", -0.006, 4.15, 2.1, 0.0, 7.65, 2.15, "trim")
    p.box("side window frame bottom", -0.006, 4.15, 1.05, 0.0, 7.65, 1.1, "trim")
    p.box("vibration isolation plinth", 0.3, 3.8, -0.0, W - 0.3, 8.0, 0.08, "steel")
    screen(p, 0.6, 2.4)
    warnings(p, W, 1.9, y=1.645)
    back_services(p, W, D, 2.4, n=5)
    for i in range(4):
        p.box(f"exhaust grille {i}", 0.4 + i * 1.0, 9.0, 2.4, 0.9 + i * 1.0, 10.4, 2.43, "dark")
    light(p, W - 0.3, 0.7, 2.4)
    return p


def track():
    k = KINDS["track"]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    efem(p, 0.0, W, 1.0, 2.2, k["ports"], "track")
    cabinet(p, "process stack", 0.0, 1.45, W, D - 1.2, H, doors=4)
    # stacked coat and develop modules seen as bands on the aisle side of the stack
    for i in range(5):
        z = 0.35 + i * 0.4
        p.box(f"module band {i}", -0.004, 1.6, z, 0.0, D - 1.4, z + 0.3, "panel_grey")
        p.box(f"module window {i}", -0.006, 2.0, z + 0.08, -0.002, 2.9, z + 0.22, "glass")
        p.box(f"module lamp {i}", -0.006, 3.1, z + 0.12, -0.002, 3.16, z + 0.18, "led_green")
    cabinet(p, "chemical cabinet", 0.0, D - 1.2, W, D, 2.0, mat="panel_grey", doors=2)
    for i in range(3):
        p.cyl(f"exhaust duct {i}", 0.7 + i * 1.05, D - 2.0, H - 0.25, 0.14, 0.25, "steel")
    for i in range(6):
        p.cyl(f"chemical bottle {i}", 0.35 + i * 0.5, D - 0.6, 2.0, 0.1, 0.25, "quartz")
    screen(p, 0.6, 2.2)
    warnings(p, W, 1.7, y=1.445)
    back_services(p, W, D, 2.0, n=3)
    light(p, W - 0.3, 0.7, 2.2)
    return p


def metrology(kind="metrology"):
    k = KINDS[kind]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    efem(p, 0.0, W, 0.8, 2.0, k["ports"], kind)
    p.box("isolation base", 0.05, 1.25, 0.0, W - 0.05, D - 0.05, 0.25, "dark", "body")
    for i, (x, y) in enumerate(((0.15, 1.35), (W - 0.35, 1.35), (0.15, D - 0.35), (W - 0.35, D - 0.35))):
        p.cyl(f"isolator {i}", x + 0.1, y + 0.1, 0.25, 0.09, 0.12, "rubber")
    cabinet(p, "measuring chamber", 0.0, 1.25, W, D, H, doors=2)
    p.box("chamber window", -0.004, 1.5, 1.0, 0.0, D - 0.3, 1.7, "glass")
    p.box("optics head", W * 0.3, 1.6, H, W * 0.7, 2.2, H + 0.0001, "trim", "body")
    p.box("chamber window frame", -0.007, 1.45, 0.95, -0.003, D - 0.25, 1.0, "trim")
    p.box("electronics rack", 0.1, D - 0.6, 0.3, W - 0.1, D - 0.05, 1.6, "dark")
    for i in range(4):
        p.box(f"rack unit {i}", 0.15, D - 0.62, 0.4 + i * 0.3, W - 0.15, D - 0.6, 0.6 + i * 0.3, "panel_grey")
    screen(p, 0.35, 2.0)
    warnings(p, W, 1.5, y=1.245)
    back_services(p, W, D, 1.9, n=2)
    light(p, W - 0.2, 0.6, 2.0)
    return p


def inspection():
    return metrology("inspection")


def cluster(kind, chambers, chamber_r, lid, lid_mat):
    """A cluster tool: front end, load locks, a transfer chamber and process chambers round it."""
    k = KINDS[kind]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    efem(p, 0.0, W, 1.0, 2.2, k["ports"], kind)
    p.box("load lock a", W / 2 - 0.75, 1.45, 0.0, W / 2 - 0.05, 2.15, 1.25, "panel_grey", "body")
    p.box("load lock b", W / 2 + 0.05, 1.45, 0.0, W / 2 + 0.75, 2.15, 1.25, "panel_grey", "body")
    cx, cy = W / 2, 2.15 + 1.0
    p.cyl("transfer chamber", cx, cy, 0.0, 0.85, 1.15, "steel", role="body")
    p.cyl("transfer chamber lid", cx, cy, 1.15, 0.88, 0.08, "trim", role="body")
    p.cyl("transfer robot hub", cx, cy, 1.23, 0.18, 0.12, "dark")
    for i in range(chambers):
        a = -math.pi * 0.85 + i * (math.pi * 1.7) / max(1, chambers - 1)
        x = cx + (0.85 + chamber_r) * math.sin(a) * 0.98
        y = cy + (0.85 + chamber_r) * math.cos(a) * 0.98
        x = min(max(x, chamber_r + 0.02), W - chamber_r - 0.02)
        p.cyl(f"chamber {i}", x, y, 0.0, chamber_r, 1.05, "steel", role="body")
        p.cyl(f"chamber {i} lid", x, y, 1.05, chamber_r * 1.02, 0.1, lid_mat, role="body")
        p.cyl(f"chamber {i} {lid}", x, y, 1.15, chamber_r * 0.55, 0.3, "panel_grey", role="body")
        p.box(f"chamber {i} slit valve", x - 0.15, y - 0.06, 0.55, x + 0.15, y + 0.06, 0.75, "dark")
        p.cyl(f"chamber {i} gas line", x + chamber_r * 0.5, y, 1.45, 0.02, 0.5, "pipe")
    # the power, gas and pump cabinets behind the chambers reach the tool's full height
    cabinet(p, "generator rack", 0.0, D - 1.1, W * 0.5, D, H, mat="panel_grey", doors=2)
    cabinet(p, "gas box", W * 0.5, D - 1.1, W, D, H - 0.3, doors=2)
    for i in range(6):
        p.box(f"generator unit {i}", 0.12, D - 1.12, 0.3 + i * 0.36, W * 0.5 - 0.12, D - 1.1, 0.55 + i * 0.36, "dark")
    for i in range(4):
        p.cyl(f"gas stick {i}", W * 0.55 + i * 0.35, D - 0.9, 0.2, 0.025, H - 0.8, "pipe")
    p.box("frame skirt", 0.0, 2.15, 0.0, 0.05, D - 1.1, 0.25, "trim", "body")
    p.box("frame skirt far", W - 0.05, 2.15, 0.0, W, D - 1.1, 0.25, "trim", "body")
    screen(p, 0.5, 2.2)
    warnings(p, W, 1.6, y=0.445)
    back_services(p, W, D, H - 0.3, n=4)
    light(p, W - 0.3, 0.7, 2.2)
    return p


def etch():
    return cluster("etch", 4, 0.5, "coil housing", "copper")


def deposition():
    return cluster("deposition", 5, 0.45, "showerhead", "trim")


def epitaxy():
    p = cluster("epitaxy", 3, 0.6, "lamp house", "panel_grey")
    k = KINDS["epitaxy"]
    for i in range(3):
        p.box(f"lamp cooling fin {i}", 0.3 + i * 1.2, 4.3, 1.75, 0.9 + i * 1.2, 4.6, 1.85, "steel")
    return p


def furnace():
    k = KINDS["furnace"]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    ports(p, k["ports"], 0.02, W - 0.02, "furnace")
    p.box("loading area", 0.0, 0.45, 0.1, W, D, 1.6, "panel", "body")
    p.box("loading area base", 0.02, 0.47, 0.0, W - 0.02, D - 0.02, 0.1, "trim", "body")
    p.box("loading window", 0.1, 0.44, 0.95, W - 0.1, 0.455, 1.5, "glass")
    p.cyl("boat elevator", W / 2, 1.2, 0.1, 0.06, 1.4, "steel")
    p.cyl("quartz boat", W / 2, 1.2, 0.55, 0.17, 0.95, "quartz")
    p.box("tube housing", 0.0, 0.45, 1.6, W, D, H - 0.3, "panel_grey", "body")
    for i in range(5):
        z = 1.75 + i * 0.25
        p.box(f"heater band {i}", -0.004, 0.6, z, 0.0, D - 0.15, z + 0.12, "trim")
    p.box("scavenger", 0.1, 0.5, H - 0.3, W - 0.1, D - 0.1, H, "panel", "body")
    p.cyl("exhaust stack", W / 2, D - 0.5, H - 0.3, 0.12, 0.3, "steel")
    for i in range(6):
        p.box(f"tube housing vent {i}", 0.15 + i * 0.2, 0.445, 2.3, 0.28 + i * 0.2, 0.455, 2.6, "dark")
    p.box("temperature panel", 0.2, 0.43, 1.65, 0.7, 0.45, 1.95, "screen")
    warnings(p, W, 2.0, y=0.443)
    back_services(p, W, D, 2.6, n=2)
    p.box("door seam", W / 2 - 0.005, 0.44, 0.15, W / 2 + 0.005, 0.455, 0.9, "trim")
    p.box("door handle", W / 2 + 0.05, 0.43, 0.5, W / 2 + 0.08, 0.45, 0.75, "steel")
    light(p, W - 0.15, 0.6, H)
    return p


def implanter():
    k = KINDS["implanter"]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    efem(p, 0.0, W, 1.0, 2.3, k["ports"], "implanter")
    cabinet(p, "end station", 0.0, 1.45, W, 3.6, 2.5, doors=3)
    p.box("beamline", W / 2 - 0.45, 3.6, 0.9, W / 2 + 0.45, 6.0, 1.6, "steel", "body")
    p.box("beamline support", W / 2 - 0.5, 3.7, 0.0, W / 2 + 0.5, 5.9, 0.9, "trim", "body")
    for i in range(3):
        y = 3.9 + i * 0.7
        p.box(f"beamline flange {i}", W / 2 - 0.5, y, 0.85, W / 2 + 0.5, y + 0.06, 1.65, "dark")
    p.box("analyzer magnet", W / 2 - 1.1, 5.0, 0.6, W / 2 + 0.2, 6.2, 2.0, "copper", "body")
    p.box("magnet yoke", W / 2 - 1.15, 5.2, 0.55, W / 2 + 0.25, 6.0, 2.05, "dark")
    # the ion source sits in a fenced high-voltage enclosure at the far end
    frame(p, "source enclosure", 0.0, 6.0, 0.0, W, D, H)
    p.box("source enclosure panel", 0.0, 6.02, 0.1, W, D, H - 0.06, "glass", "body")
    p.box("source enclosure base", 0.0, 6.0, 0.0, W, D, 0.1, "trim", "body")
    p.box("ion source", W / 2 - 0.5, 6.6, 0.4, W / 2 + 0.5, 7.4, 1.6, "steel")
    p.box("high-voltage terminal", W / 2 - 0.9, 6.3, 0.2, W / 2 + 0.9, 7.8, 0.4, "dark")
    for i in range(4):
        p.box(f"high-voltage sign {i}", 0.3 + i * 0.8, 5.995, 2.2, 0.55 + i * 0.8, 6.0, 2.45, "warning")
    p.cyl("gas cabinet", W - 0.4, D - 0.4, 0.1, 0.25, 1.8, "panel_grey")
    screen(p, 0.6, 2.3)
    warnings(p, W, 1.7, y=1.445)
    back_services(p, W, D, 2.6, n=3)
    light(p, W - 0.3, 0.7, 2.3)
    return p


def polisher():
    k = KINDS["polisher"]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    efem(p, 0.0, W, 1.0, 2.2, k["ports"], "polisher")
    cabinet(p, "cleaner", 0.0, 1.45, W, 2.8, H, doors=3)
    for i in range(4):
        p.box(f"cleaner brush box {i}", 0.2 + i * 0.68, 1.44, 1.1, 0.7 + i * 0.68, 1.455, 1.7, "glass")
    p.box("polish module", 0.0, 2.8, 0.1, W, D, 0.95, "panel", "body")
    p.box("polish module base", 0.02, 2.82, 0.0, W - 0.02, D - 0.02, 0.1, "trim", "body")
    for i in range(3):
        p.cyl(f"platen {i}", 0.55 + i * 0.95, 4.2, 0.95, 0.4, 0.06, "dark")
        p.cyl(f"pad conditioner {i}", 0.55 + i * 0.95 + 0.3, 4.75, 1.01, 0.05, 0.12, "steel")
        p.cyl(f"slurry arm {i}", 0.55 + i * 0.95 - 0.35, 3.7, 1.15, 0.02, 0.5, "pipe", axis="y")
    p.cyl("carousel spindle", W / 2, 4.6, 0.95, 0.15, 1.1, "steel")
    p.box("carousel cross a", 0.2, 4.55, 1.95, W - 0.2, 4.65, 2.05, "steel")
    p.box("carousel cross b", W / 2 - 0.05, 3.6, 1.95, W / 2 + 0.05, 5.6, 2.05, "steel")
    for i, (x, y) in enumerate(((0.35, 4.6), (W - 0.35, 4.6), (W / 2, 3.75), (W / 2, 5.45))):
        p.cyl(f"polish head {i}", x, y, 1.2, 0.17, 0.75, "panel_grey")
    p.box("polish enclosure", 0.0, 2.8, 0.95, 0.03, D, H, "glass", "body")
    p.box("polish enclosure far", W - 0.03, 2.8, 0.95, W, D, H, "glass", "body")
    p.box("polish enclosure roof", 0.0, 2.8, H - 0.05, W, D, H, "panel_grey", "body")
    p.box("polish enclosure back", 0.0, D - 0.05, 0.95, W, D, H, "panel_grey", "body")
    for i in range(3):
        p.cyl(f"slurry tote {i}", 0.5 + i * 1.0, D - 0.4, 0.1, 0.15, 0.6, "quartz")
    screen(p, 0.5, 2.2)
    warnings(p, W, 1.5, y=1.445)
    back_services(p, W, D, 2.4, n=3)
    light(p, W - 0.3, 0.7, 2.2)
    return p


def wet_bench():
    k = KINDS["wet_bench"]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    efem(p, 0.0, W, 1.0, 2.3, k["ports"], "wet_bench")
    p.box("plumbing cabinet", 0.0, 1.45, 0.1, W, D, 0.95, "panel", "body")
    p.box("plumbing kick", 0.02, 1.47, 0.0, W - 0.02, D - 0.02, 0.1, "trim", "body")
    for i in range(7):
        y = 1.8 + i * 1.15
        p.box(f"tank {i}", 0.35, y, 0.95, W - 0.35, y + 0.95, 1.35, "quartz")
        p.box(f"tank {i} rim", 0.3, y - 0.03, 1.33, W - 0.3, y + 0.98, 1.36, "steel")
        p.box(f"tank {i} door", 0.05, y + 0.1, 0.15, 0.06, y + 0.85, 0.85, "panel_grey")
    p.box("deck", 0.0, 1.45, 0.95, W, D, 1.0, "panel_grey", "body")
    p.box("sash", -0.005, 1.5, 1.0, 0.03, D - 0.05, 2.1, "glass", "body")
    p.box("sash far", W - 0.03, 1.5, 1.0, W, D - 0.05, 2.1, "glass", "body")
    p.box("exhaust plenum", 0.0, 1.45, 2.1, W, D, H, "panel", "body")
    p.box("gantry rail", 0.25, 1.6, 1.95, 0.35, D - 0.2, 2.05, "steel")
    p.box("gantry rail far", W - 0.35, 1.6, 1.95, W - 0.25, D - 0.2, 2.05, "steel")
    p.box("gantry robot", 0.25, 4.2, 1.6, W - 0.25, 4.6, 1.95, "panel_grey")
    p.box("gantry gripper", W / 2 - 0.2, 4.25, 1.3, W / 2 + 0.2, 4.55, 1.6, "steel")
    for i in range(4):
        p.cyl(f"exhaust duct {i}", W / 2, 2.2 + i * 2.2, H - 0.001, 0.15, 0.001, "steel")
    p.box("chemical warning band", -0.006, 1.6, 0.85, -0.002, D - 0.2, 0.9, "warning")
    screen(p, 0.5, 2.3)
    back_services(p, W, D, 2.4, n=3)
    light(p, W - 0.3, 0.7, 2.3)
    return p


def stocker():
    k = KINDS["stocker"]
    W, D, H = k["w"], k["d"], k["h"]
    p = Parts()
    frame(p, "stocker frame", 0.0, 0.0, 0.0, W, D, H, t=0.08)
    p.box("stocker skin", 0.0, 0.0, 0.0, W, D, 0.15, "trim", "body")
    p.box("stocker window", 0.01, 0.0, 0.3, W - 0.01, 0.02, H - 0.3, "glass", "body")
    p.box("stocker back", 0.0, D - 0.05, 0.15, W, D, H, "panel", "body")
    p.box("stocker roof", 0.0, 0.0, H - 0.08, W, D, H, "panel_grey", "body")
    c = SIZES["carrier"]
    for row in range(6):
        z = 0.5 + row * 0.75
        p.box(f"shelf {row}", 0.1, 0.4, z - 0.03, W - 0.1, D - 0.4, z, "steel")
        for j in range(5):
            x = 0.25 + j * 0.55
            p.box(f"stored carrier {row} {j}", x, 0.6, z, x + c["w"], 0.6 + c["d"], z + c["h"], "foup_shell")
    p.box("crane mast", W / 2 - 0.1, D / 2 - 0.1, 0.15, W / 2 + 0.1, D / 2 + 0.1, H - 0.1, "steel")
    p.box("crane carriage", W / 2 - 0.4, D / 2 - 0.3, 2.2, W / 2 + 0.4, D / 2 + 0.3, 2.5, "panel_grey")
    p.box("crane floor rail", W / 2 - 0.08, 0.2, 0.15, W / 2 + 0.08, D - 0.2, 0.22, "rail")
    for i in range(2):
        p.box(f"input port {i}", 0.4 + i * 1.4, -0.0, H - 0.6, 1.0 + i * 1.4, 0.4, H - 0.4, "panel_grey")
    return p


BUILDERS = {"scanner": scanner, "track": track, "metrology": metrology, "inspection": inspection,
            "etch": etch, "deposition": deposition, "epitaxy": epitaxy, "furnace": furnace,
            "implanter": implanter, "polisher": polisher, "wet_bench": wet_bench, "stocker": stocker}


def model(kind):
    return list(BUILDERS[kind]())


# ---------------------------------------------------------------------------------- carrier and hoist

def carrier():
    """The wafer carrier, centred on x and y, standing on z = 0: W across, D from door to back."""
    c = SIZES["carrier"]
    w, d, h = c["w"], c["d"], c["h"]
    p = Parts()
    p.box("carrier base plate", -w / 2 + 0.03, -d / 2 + 0.02, 0.0, w / 2 - 0.03, d / 2 - 0.02, 0.015, "dark", "body")
    p.box("carrier shell", -w / 2 + 0.02, -d / 2 + 0.03, 0.015, w / 2 - 0.02, d / 2, h - 0.04, "foup_shell", "body")
    p.box("carrier door", -w / 2 + 0.015, -d / 2, 0.02, w / 2 - 0.015, -d / 2 + 0.03, h - 0.045, "foup_door", "body")
    p.box("carrier handle left", -w / 2, -0.06, 0.12, -w / 2 + 0.02, 0.1, 0.22, "dark", "body")
    p.box("carrier handle right", w / 2 - 0.02, -0.06, 0.12, w / 2, 0.1, 0.22, "dark", "body")
    p.box("carrier top flange", -0.08, -0.07, h - 0.04, 0.08, 0.09, h, "dark", "body")
    p.box("carrier door latch", -0.05, -d / 2 - 0.0, 0.14, 0.05, -d / 2 + 0.005, 0.2, "steel")
    return list(p)


def vehicle():
    """The hoist car, centred on x and y, its top at z = 0 against the rail: L along the rail."""
    v = SIZES["vehicle"]
    L, Wd, H = v["l"], v["w"], v["h"]
    p = Parts()
    p.box("car drive", -L / 2 + 0.1, -0.08, -0.12, L / 2 - 0.1, 0.08, 0.0, "dark", "body")
    p.box("car body", -L / 2, -Wd / 2, -H + 0.1, L / 2, Wd / 2, -0.12, "vehicle", "body")
    p.box("car hoist unit", -L / 2 + 0.15, -Wd / 2 + 0.06, -H, L / 2 - 0.15, Wd / 2 - 0.06, -H + 0.1, "trim", "body")
    p.box("car front bumper", L / 2 - 0.01, -Wd / 2 + 0.05, -H + 0.2, L / 2, Wd / 2 - 0.05, -0.2, "warning")
    p.box("car back bumper", -L / 2, -Wd / 2 + 0.05, -H + 0.2, -L / 2 + 0.01, Wd / 2 - 0.05, -0.2, "warning")
    p.box("car lamp", L / 2 - 0.02, -0.05, -0.3, L / 2 + 0.0, 0.05, -0.25, "led_blue")
    return list(p)


# ---------------------------------------------------------------------------------- the building

def floors():
    b = SIZES["building"]
    out, z = [], 0.0
    for name, h in (("support floor", b["support_floor"]), ("waffle slab", b["waffle_slab"]),
                    ("raised floor", b["raised_floor"]), ("cleanroom", b["cleanroom"]),
                    ("air space", b["air_space"]), ("roof", b["roof_slab"])):
        out.append({"name": name, "z0": round(z, 6), "z1": round(z + h, 6)})
        z += h
    return out


def clean_floor_z():
    b = SIZES["building"]
    return b["support_floor"] + b["waffle_slab"] + b["raised_floor"]


def export():
    return {
        "what": "Parts for every model of the realistic fab: a gigafab-style layout of our own design from the SMT2020 testbed. Generic shapes of our own; no maker's tool.",
        "frame": "x along the wall (W), y into the bay from the aisle (D), z up from the raised floor",
        "materials": MATERIALS,
        "kinds": {k: model(k) for k in BUILDERS},
        "carrier": carrier(),
        "vehicle": vehicle(),
        "floors": floors(),
        "sizes": SIZES,
    }


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/layout-real/models.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(export(), separators=(",", ":")))
    print(f"wrote {out}: {sum(len(v) for v in export()['kinds'].values())} parts in {len(BUILDERS)} kinds")
