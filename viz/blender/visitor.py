"""The visitor film, "A Walk Through the Fab", in Blender: a person walks in from the car park,
badges in, rides the lift, crosses the bridge, gowns up, takes the air shower and walks the clean
floor to the sights the run chose. A gigafab-style layout of our own design on the SMT2020 model;
not a real fab. The visitor, the rooms of the way in and their props are drawn only; every number
on screen is the run's.

    Blender -b FAB.blend -P viz/blender/visitor.py -- PLAN SCENE PEOPLE PROPS OUT
        [--assets DIR] [--report OUT.json] [--still S1,S2 [--res 960x540]] [--frames A:B]
        [--samples 32] [--nosave]

FAB.blend is the film's saved scene (viz/blender/real.py); PLAN is data/layout-real/visitor-film.json
(viz/visitor/film_plan.py); SCENE is scene-optimised.json; PEOPLE and PROPS are people.blend and
props.blend (viz/blender/people.py, props.py). The plan decides where he is, what he does, where he
looks and where the camera is; this script only draws it:
  - the film's own things go (its hero lot, camera, workers, arriving cars, everything keyed to its
    shots), and tool lamps, lots and hoist cars are keyed again on this film's clock;
  - the office gets a lobby in its north face; the lobby, lift, bridge, corridor, gowning room and
    air shower are built as the plan draws them, with their props and doors that open as he comes;
  - he walks by distance (the walk clip's measured stride, so the planted foot stays put), stands,
    reaches, sits, and turns his head where the plan looks; street clothes, then the suit;
  - area signs become white with the area's colour as a stripe and its name; lithography keeps its
    yellow light.
With --report, writes what was built, frame by frame, for viz/tests/test_visitor_blender.py, and
renders nothing. Writes OUT/visitor.blend unless --nosave; stills to OUT/still-S.png; frames to
OUT/frames/v0001.jpg ...
"""

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bkit import Batch, action_curves, collection, fcurves, fill, principled, srgb  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1 :]
PLAN, SCENE, PEOPLE, PROPS, OUT = (Path(x) for x in argv[:5])


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


REPORT = Path(opt("--report")) if opt("--report") else None
STILLS = [float(v) for v in opt("--still").split(",")] if opt("--still") else None
FR = [int(v) for v in opt("--frames").split(":")] if opt("--frames") else None
RES = [int(v) for v in opt("--res", "1920x1080").split("x")]
SAMPLES = int(opt("--samples", "32"))
ASSETS = Path(opt("--assets")).expanduser() if opt("--assets") else None
OUT.mkdir(parents=True, exist_ok=True)

P = json.loads(PLAN.read_text())
S = json.loads(SCENE.read_text())
FPS = 24
DT = P["dt"]
END_S = P["path"][-1][0]
NF = int(round(END_S * FPS)) + 1  # frames 1..NF; frame f shows film second (f - 1) / FPS
CZ = S["clean_z"]
cr = [f for f in S["floors"] if f["name"] == "cleanroom"][0]
CEIL = CZ + cr["z1"] - cr["z0"]
SP = S["spine"]
scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, NF


def frame_of_s(s):
    return 1 + s * FPS


# ------------------------------------------------------------------------- this film's clock
KN = P["clock"]  # [film s, fab minute]


def s_of_t(t):
    """Film second at fab minute t, straight on past either end at the nearest stretch's rate."""
    for a, b in zip(KN, KN[1:]):
        if a[1] <= t <= b[1]:
            return a[0] + (b[0] - a[0]) * (t - a[1]) / (b[1] - a[1])
    a, b = (KN[0], KN[1]) if t < KN[0][1] else (KN[-2], KN[-1])
    return a[0] + (b[0] - a[0]) * (t - a[1]) / (b[1] - a[1])


def frame_of_t(t):
    return frame_of_s(s_of_t(t))


def increasing(frames):
    out, last = [], -1e18
    for f in frames:
        f = max(f, last + 0.02)  # Blender merges keys closer than 0.01 of a frame
        out.append(f)
        last = f
    return out


# ------------------------------------------------------------------------- the film's own things go
FILM_ONLY = ("hero", "worker", "arriving car", "camera", "look at")
for ob in list(bpy.data.objects):
    if ob.name.startswith(FILM_ONLY):
        bpy.data.objects.remove(ob, do_unlink=True)
for idb in (scene, scene.world, scene.camera.data if scene.camera else None):
    if idb is not None and idb.animation_data:
        idb.animation_data_clear()
REKEY = ("light ", "lot ", "car ")
for ob in bpy.data.objects:
    if ob.animation_data and not ob.name.startswith(REKEY):
        if ob.name.startswith("steam"):
            continue
        ob.animation_data_clear()
        ob.hide_render = ob.hide_viewport = False
        if ob.type == "MESH" and ob.parent is None and ob.name not in ("sun",):
            ob.location = (0, 0, 0)
    if ob.type == "CURVE" and ob.data.animation_data:
        ob.data.animation_data_clear()

# the morning sun, from the south-east, steady
sun = bpy.data.objects.get("sun")
if sun is not None:
    az, el = math.radians(-58), math.radians(38)
    d = Vector((-math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az), -math.sin(el)))
    sun.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sun.data.energy = 4.2
    if sun.data.animation_data:
        sun.data.animation_data_clear()
scene.view_settings.exposure = 0.0

# ------------------------------------------------------------------------- the run, on this clock
STATE_RGBA = {0: (0, 1, 0, 0), 1: (0, 0, 0, 1), 2: (0, 0, 1, 0), 3: (1, 0, 0, 0)}
by_tool = {}
for t, ti, code in S["states"]:
    by_tool.setdefault(ti, []).append((t, code))
for ti in range(len(S["tools"])):
    lo = bpy.data.objects.get(f"light {ti}")
    if lo is None:
        continue
    lo.animation_data_clear()
    seq = by_tool.get(ti, [(S["from"], 1)])
    lo.color = STATE_RGBA[seq[0][1]]
    if len(seq) > 1:
        frames = increasing([frame_of_t(seq[0][0]) - 1e6] + [frame_of_t(x[0]) for x in seq[1:]])
        fill(lo, "color", frames, [STATE_RGBA[seq[0][1]]] + [STATE_RGBA[x[1]] for x in seq[1:]], constant=True)
PORT_Z, RAIL_Z = S["port_z"], S["rail_z"]
for L_ in S["lots"]:
    ob = bpy.data.objects.get("lot " + L_["id"])
    if ob is None:
        continue
    ob.animation_data_clear()
    keys = L_["k"]
    # a key wherever this film's clock changes pace, so between keys the lot moves as the run says
    extra = []
    for _, kt in KN:
        if keys[0][0] < kt < keys[-1][0]:
            for a, b in zip(keys, keys[1:]):
                if a[0] < kt < b[0]:
                    u = (kt - a[0]) / (b[0] - a[0])
                    extra.append([kt] + [a[i] + (b[i] - a[i]) * u for i in (1, 2, 3)])
                    break
    keys_all = sorted(keys + extra, key=lambda k: k[0])
    frames = increasing([frame_of_t(k[0]) for k in keys_all])
    fill(ob, "location", frames, [tuple(k[1:4]) for k in keys_all])
    frames = increasing([frame_of_t(k[0]) for k in keys])
    vis = [(frames[0] - 0.05, 0.0), (frames[0], 1.0), (frames[-1], 1.0), (frames[-1] + 0.05, 0.0)]
    fill(ob, "scale", [v[0] for v in vis], [(v[1],) * 3 for v in vis], constant=True)
    # waiting on a shelf: the red channel, which the carrier's glow reads
    wf, wv = [frames[0] - 0.05], [(0, 0, 0, 1)]
    for i, (a, b) in enumerate(zip(keys, keys[1:])):
        waiting = a[1:] == b[1:] and a[3] > PORT_Z + 0.01 and abs(a[2]) > SP / 2
        wf.append(frames[i])
        wv.append((1, 0, 0, 1) if waiting else (0, 0, 0, 1))
    fill(ob, "color", increasing(wf), wv, constant=True)
    car = bpy.data.objects.get("car " + L_["id"])
    if car is not None:
        car.animation_data_clear()
        cf, cv, sf, sv = [], [], [], []
        for m0, m1 in L_["m"]:
            for k in keys:
                if m0 - 1e-6 <= k[0] <= m1 + 1e-6:
                    cf.append(frame_of_t(k[0]))
                    cv.append((k[1], k[2], RAIL_Z))
            sf += [frame_of_t(m0) - 0.05, frame_of_t(m0), frame_of_t(m1), frame_of_t(m1) + 0.05]
            sv += [(0,) * 3, (1,) * 3, (1,) * 3, (0,) * 3]
        if cf:
            fill(car, "location", increasing(cf), cv)
            order = sorted(range(len(sf)), key=lambda i: sf[i])
            fill(car, "scale", increasing([sf[i] for i in order]), [sv[i] for i in order], constant=True)
        else:
            car.scale = (0, 0, 0)

# ------------------------------------------------------------------------- materials of the way in
M = {
    "lobby floor": principled("v lobby stone", "#cbc6bd", rough=0.22, coat=0.2),
    "lobby wall": principled("v plaster", "#ebe9e4", rough=0.85),
    "ceiling": principled("v ceiling", "#f2f2f0", rough=0.9),
    "glass": principled("v glazing", "#d4e4ea", rough=0.02, alpha=0.16, trans=0.9),
    "mullion": principled("v mullion", "#3b3e42", metal=0.7, rough=0.35),
    "steel": principled("v lift steel", "#b4b9bf", metal=0.9, rough=0.28),
    "granite": principled("v granite", "#3b3b3e", rough=0.3, coat=0.3),
    "vinyl": principled("v vinyl", "#9aa0a6", rough=0.5),
    "corridor wall": principled("v corridor wall", "#eceef0", rough=0.7),
    "clean wall": principled("v cleanroom panel", "#f0f2f4", rough=0.45),
    "clean floor": principled("v epoxy", "#d5dade", rough=0.3, coat=0.3),
    "grate": principled("v grate", "#6b727a", metal=0.7, rough=0.45),
    "panel light": principled("v panel light", "#f6f8ff", emit=6.0),
    "sticky": principled("v sticky mat", "#4a5c72", rough=0.6),
    "seam": principled("v panel seam", "#c3c8cd", rough=0.5),
}
LOOK = {
    "lobby": ("lobby floor", "lobby wall", "ceiling"),
    "lift": ("granite", "steel", "steel"),
    "bridge": ("vinyl", "glass", "ceiling"),
    "corridor": ("vinyl", "corridor wall", "ceiling"),
    "gowning": ("clean floor", "clean wall", "ceiling"),
    "air shower": ("grate", "steel", "steel"),
}
T = 0.15  # wall thickness
rooms_col = collection("way in")
light_col = collection("way in lights")


def rooms():
    return [r for r in P["rooms"] if r["kind"] != "walkway"]


def parent_of(r):
    for o in rooms():
        if o is not r and o["x0"] <= r["x0"] and r["x1"] <= o["x1"] and o["y0"] <= r["y0"] and r["y1"] <= o["y1"] and abs(o["z0"] - r["z0"]) < 0.01:
            return o
    return None


def wall_runs(r, side):
    """The wall's solid pieces along it (lo, hi, z0, z1), around its doors."""
    lo, hi = (r["x0"] - T, r["x1"] + T) if side in ("n", "s") else (r["y0"] - T, r["y1"] + T)
    z0, z1 = r["z0"], r["z1"]
    doors = sorted((d for d in r.get("doors", []) if d["wall"] == side), key=lambda d: d["at"])
    out, at = [], lo
    for d in doors:
        a, b = d["at"] - d["w"] / 2, d["at"] + d["w"] / 2
        out.append((at, a, z0, z1))
        out.append((a, b, z0 + d["h"], z1))
        at = b
    out.append((at, hi, z0, z1))
    return [x for x in out if x[1] - x[0] > 1e-3 and x[3] - x[2] > 1e-3]


BUILT = []


def build_room(r):
    floor_m, wall_m, ceil_m = (M[k] for k in LOOK[r["name"]])
    b = Batch()
    x0, x1, y0, y1, z0, z1 = r["x0"], r["x1"], r["y0"], r["y1"], r["z0"], r["z1"]
    par = parent_of(r)
    lift_ = 0.003 + 0.002 * len(BUILT)  # no two floors in one plane
    b.box(floor_m, x0 - T, y0 - T, z0 - 0.12, x1 + T, y1 + T, z0 + lift_)
    b.box(ceil_m, x0 - T, y0 - T, z1, x1 + T, y1 + T, z1 + 0.15)
    for side in ("n", "s", "e", "w"):
        c = {"n": y1, "s": y0, "e": x1, "w": x0}[side]
        on_parent = par is not None and abs(c - {"n": par["y1"], "s": par["y0"], "e": par["x1"], "w": par["x0"]}[side]) < 1e-6
        # a wall on its parent's wall is a lining inside it (the air shower's steel against the gowning wall)
        t0, t1 = (c - 0.012, c) if side in ("n", "e") else (c, c + 0.012)
        if not on_parent:
            t0, t1 = (c, c + T) if side in ("n", "e") else (c - T, c)
        glazed = r["name"] == "bridge" and side in ("e", "w") or (r["name"] == "lobby" and side == "n")
        for lo, hi, za, zb in wall_runs(r, side):
            if on_parent:
                lo, hi = max(lo, (x0 if side in ("n", "s") else y0)), min(hi, (x1 if side in ("n", "s") else y1))
                if hi <= lo:
                    continue
            m = M["glass"] if glazed else wall_m
            if side in ("n", "s"):
                b.box(m, lo, t0, za, hi, t1, zb)
            else:
                b.box(m, t0, lo, za, t1, hi, zb)
            if glazed:  # mullions every 1.5 m and a transom at door height
                n = max(1, int((hi - lo) // 1.5))
                for i in range(n + 1):
                    u = lo + (hi - lo) * i / n
                    if side in ("n", "s"):
                        b.box(M["mullion"], u - 0.03, t0 - 0.02, za, u + 0.03, t1 + 0.02, zb)
                    else:
                        b.box(M["mullion"], t0 - 0.02, u - 0.03, za, t1 + 0.02, u + 0.03, zb)
        if r["name"] == "gowning" and not on_parent:  # cleanroom wall panels: seams every 1.2 m
            span = (x0, x1) if side in ("n", "s") else (y0, y1)
            for i in range(1, int((span[1] - span[0]) // 1.2) + 1):
                u = span[0] + i * 1.2
                if any(abs(u - d["at"]) < d["w"] / 2 + 0.05 for d in r.get("doors", []) if d["wall"] == side):
                    continue
                inner = t0 - 0.002 if side in ("n", "e") else t1
                if side in ("n", "s"):
                    b.box(M["seam"], u - 0.004, inner, z0, u + 0.004, inner + 0.002, z1)
                else:
                    b.box(M["seam"], inner, u - 0.004, z0, inner + 0.002, u + 0.004, z1)
    # lights in the ceiling: panels you can see, and the light they give
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, d = x1 - x0, y1 - y0
    nx, ny = max(1, round(w / 3.0)), max(1, round(d / 3.0))
    for i in range(nx):
        for j in range(ny):
            px, py = x0 + (i + 0.5) * w / nx, y0 + (j + 0.5) * d / ny
            pw, pd = min(0.6, w / nx * 0.6), min(1.2, d / ny * 0.6)
            b.box(M["panel light"], px - pw / 2, py - pd / 2, z1 - 0.01, px + pw / 2, py + pd / 2, z1)
            lt = bpy.data.lights.new(f"{r['name']} light {i} {j}", "AREA")
            lt.shape, lt.size, lt.size_y = "RECTANGLE", pw, pd
            lt.energy = {"lobby": 260, "lift": 120, "bridge": 140, "corridor": 120, "gowning": 320, "air shower": 140}[r["name"]]
            lt.color = (1.0, 0.96, 0.9) if r["name"] == "lobby" else (0.96, 0.98, 1.0)
            lo_ = bpy.data.objects.new(lt.name, lt)
            lo_.location = (px, py, z1 - 0.02)
            light_col.objects.link(lo_)
    if r["name"] == "gowning":
        for f in r.get("furniture", []):
            if f["kind"] == "mark":
                b.box(M["sticky"], f["x0"], f["y0"], z0 + lift_, f["x1"], f["y1"], z0 + lift_ + 0.003)
    ob = b.make("room " + r["name"], rooms_col)
    BUILT.append({"name": r["name"], "inside": {k: r[k] for k in ("x0", "x1", "y0", "y1", "z0", "z1")},
                  "openings": [{"wall": d["wall"], "at": d["at"], "w": d["w"], "h": d["h"]} for d in r.get("doors", [])],
                  "object": ob.name})


for r in rooms():
    build_room(r)

# the office: its north face opens on the lobby (the lobby's own glass wall closes it)
lob = [r for r in P["rooms"] if r["name"] == "lobby"][0]
off = bpy.data.objects.get("OFFICE")
oc = [c for c in S["campus"] if c["kind"] == "office"][0]
if off is not None:
    mats = {m.name.split(".")[0]: m for m in off.data.materials}

    def mat(*keys):
        for k, m in mats.items():
            if all(x in k for x in keys):
                return m
        return off.data.materials[0]

    cx_, cy_, ro_, co_ = mat("curtain", "x"), mat("curtain", "y"), mat("roof"), mat("concrete")
    X0, X1, Y0, Y1, H = oc["x0"], oc["x1"], oc["y0"], oc["y1"], oc["h"]
    b = Batch()
    b.box(cx_, X0, Y0, 0.0, X1, Y0 + 0.3, H)
    b.box(cx_, X0, Y1 - 0.3, 0.0, lob["x0"] - T, Y1, H)
    b.box(cx_, lob["x1"] + T, Y1 - 0.3, 0.0, X1, Y1, H)
    b.box(cx_, lob["x0"] - T, Y1 - 0.3, lob["z1"] + 0.15, lob["x1"] + T, Y1, H)
    b.box(cy_, X0, Y0, 0.0, X0 + 0.3, Y1, H)
    b.box(cy_, X1 - 0.3, Y0, 0.0, X1, Y1, H)
    b.box(ro_, X0, Y0, H - 0.5, X1, Y1, H + 0.6)
    b.box(co_, X0 + 20, Y0 - 6, 4.0, X0 + 50, Y0, 4.5)
    old = off.data
    off.data = b.mesh("OFFICE with lobby")
    bpy.data.meshes.remove(old)
    # a canopy over the entrance, and a path from the car park
    cb = Batch()
    cb.box(M["mullion"], lob["x0"] + 2.5, Y1, 3.1, lob["x1"] - 4.5, Y1 + 2.6, 3.3)
    pave = principled("v paving", "#b7b3ab", rough=0.8)
    park = [c for c in S["campus"] if c["kind"] == "parking"][0]
    cb.box(pave, lob["x0"] + 3.4, Y1, 0.0, lob["x1"] - 5.6, park["y0"], 0.06)
    cb.make("entrance canopy and path", rooms_col)

# ------------------------------------------------------------------------- props and doors
with bpy.data.libraries.load(str(PROPS), link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith("prop ")]
PROP = {o.name: o for o in dst.objects}
props_col = collection("way in props")
PLACED = []
for r in P["rooms"]:
    for f in r.get("furniture", []):
        if f["kind"] == "mark":
            continue
        src_ob = PROP["prop " + f["kind"]]
        ob = bpy.data.objects.new(f["id"], src_ob.data)  # shares the asset's mesh
        size = src_ob["size"]
        ob.location = (f["x0"], f["y0"], f["z0"])
        ob.scale = ((f["x1"] - f["x0"]) / size[0], (f["y1"] - f["y0"]) / size[1], (f["z1"] - f["z0"]) / size[2])
        props_col.objects.link(ob)
        PLACED.append((f, ob))


def path_at(s):
    rows = P["path"]
    i = min(max(int(s / DT), 0), len(rows) - 2)
    a, b = rows[i], rows[i + 1]
    u = min(max((s - a[0]) / DT, 0.0), 1.0)
    return a, b, u


def crossings(plane_axis, c, lo, hi):
    """Film seconds he crosses the plane (x or y = c) between lo and hi, walking (not at a cut)."""
    out = []
    rows = P["path"]
    for a, b in zip(rows, rows[1:]):
        if any(a[0] < cc <= b[0] + 1e-9 for cc in P["cuts"]):
            continue
        pa, pb = (a[1], b[1]) if plane_axis == "x" else (a[2], b[2])
        if (pa - c) * (pb - c) < 0:
            u = (c - pa) / (pb - pa)
            along = (a[2] + (b[2] - a[2]) * u) if plane_axis == "x" else (a[1] + (b[1] - a[1]) * u)
            if lo <= along <= hi:
                out.append(a[0] + (b[0] - a[0]) * u)
    return out


doors_col = collection("way in doors")
DOORS = []
seen = set()
OPEN_S, LEAD_S, STAY_S = 0.9, 1.2, 1.4  # takes 0.9 s to open, fully open 1.2 s before he reaches it, closes 1.4 s after
for r in rooms():
    for d in r.get("doors", []):
        c = {"n": r["y1"], "s": r["y0"], "e": r["x1"], "w": r["x0"]}[d["wall"]]
        axis = "y" if d["wall"] in ("n", "s") else "x"
        key = (axis, round(c, 3), round(d["at"], 3))
        if key in seen:
            continue
        seen.add(key)
        src_ob = PROP[f"prop door {d['kind']} {d['w']:g}x{d['h']:g}"]
        lo, hi = d["at"] - d["w"] / 2, d["at"] + d["w"] / 2
        passes = crossings("y" if axis == "y" else "x", c, lo, hi)
        sliding = d["kind"] in ("glass sliding", "lift")
        leaves = []
        for k in ((0, 1) if sliding else (0,)):
            ob = bpy.data.objects.new(f"door {r['name']} {d['wall']} {k}", src_ob.data)
            doors_col.objects.link(ob)
            leaves.append(ob)
        z0 = r["z0"]

        def place(ob, k, amount):
            """amount 0 closed .. 1 open."""
            lw = d["w"] / 2
            if sliding:
                sgn = -1 if k == 0 else 1
                start = lo if k == 0 else hi
                off_ = sgn * lw * 0.98 * amount
                if axis == "y":
                    ob.location = (start + off_, c, z0)
                    ob.rotation_euler = (0, 0, 0 if k == 0 else math.pi)
                else:
                    ob.location = (c, start + off_, z0)
                    ob.rotation_euler = (0, 0, math.pi / 2 if k == 0 else -math.pi / 2)
            else:
                # hinged at its low end, swinging away from the way he comes
                base = 0.0 if axis == "y" else math.pi / 2
                swing = math.radians(95) * amount * (sw_dir[0])
                if axis == "y":
                    ob.location = (lo, c, z0)
                else:
                    ob.location = (c, lo, z0)
                ob.rotation_euler = (0, 0, base + swing)

        sw_dir = [1.0]
        if passes and not sliding:
            a, b, u = path_at(passes[0])
            v = (b[1] - a[1], b[2] - a[2])
            # walking +y through a wall along x: the leaf (along +x from its hinge) turns +90 degrees to open ahead of him
            sw_dir[0] = (1.0 if v[1] > 0 else -1.0) if axis == "y" else (-1.0 if v[0] > 0 else 1.0)
        keys = [(-10.0, 0.0)]
        for sp in passes:
            keys += [(sp - LEAD_S - OPEN_S, 0.0), (sp - LEAD_S, 1.0), (sp + STAY_S, 1.0), (sp + STAY_S + OPEN_S, 0.0)]
        keys.sort()
        for k, ob in enumerate(leaves):
            place(ob, k, 0.0)
            for s_, amt in keys:
                place(ob, k, amt)
                ob.keyframe_insert("location", frame=frame_of_s(s_))
                ob.keyframe_insert("rotation_euler", frame=frame_of_s(s_))
            for fc in fcurves(ob):
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
                    kp.easing = "EASE_IN_OUT"
        DOORS.append({"id": f"{r['name']} {d['wall']}", "kind": d["kind"], "passes": [[round(sp, 4), round(sp - LEAD_S, 4)] for sp in passes]})

# the turnstile lane he walks through: its glass wings retract after his badge, and close behind him
ts = sorted((f for f, ob in PLACED if f["kind"] == "turnstile"), key=lambda f: f["x0"])
wing_src = PROP["prop turnstile wing"]
badge = [a for a in P["acts"] if a["act"] == "interact" and a.get("at") == "badge reader"]
for a_, b_ in zip(ts, ts[1:]):
    lane = (a_["x1"], b_["x0"])
    yc = (a_["y0"] + a_["y1"]) / 2
    through = crossings("y", yc, lane[0], lane[1])
    for k, (x, rot) in enumerate(((lane[0], 0.0), (lane[1], math.pi))):
        ob = bpy.data.objects.new(f"turnstile wing {lane[0]:.2f} {k}", wing_src.data)
        doors_col.objects.link(ob)
        ob.rotation_euler = (0, 0, rot)
        ob.location = (x, yc, 0.0)
        if through and badge:
            sgn = -1 if k == 0 else 1
            for s_, amt in ((badge[0]["s1"] - 0.6, 0.0), (badge[0]["s1"] - 0.1, 1.0), (through[0] + 1.2, 1.0), (through[0] + 1.8, 0.0)):
                ob.location = (x + sgn * 0.42 * amt, yc, 0.0)
                ob.keyframe_insert("location", frame=frame_of_s(s_))

# his car, parked where the plan says he left it
car_info = P["car"]
if ASSETS and (ASSETS / "cars" / "sedan.glb").exists():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ASSETS / "cars" / "sedan.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("his car", None)
    rooms_col.objects.link(root)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        rooms_col.objects.link(o)
        if o.parent is None:
            o.parent = root
    root.scale = (1.2, 1.75, 1.15)
    root.location = (car_info["x"], car_info["y"], 0.0)
    root.rotation_euler = (0, 0, car_info["yaw"] + math.pi / 2)
    # no parked car of the film under his
    pk = bpy.data.objects.get("parked")
    if pk is not None and pk.type == "MESH":
        bm = bmesh.new()
        bm.from_mesh(pk.data)
        hit = {v for v in bm.verts if abs(v.co.x - car_info["x"]) < 2.4 and abs(v.co.y - car_info["y"]) < 3.4}
        todo, seen_v = list(hit), set(hit)
        while todo:
            v = todo.pop()
            for e in v.link_edges:
                o2 = e.other_vert(v)
                if o2 not in seen_v:
                    seen_v.add(o2)
                    todo.append(o2)
        bmesh.ops.delete(bm, geom=list(seen_v), context="VERTS")
        bm.to_mesh(pk.data)
        bm.free()

# ------------------------------------------------------------------------- the visitor
with bpy.data.libraries.load(str(PEOPLE), link=False) as (src, dst):
    dst.collections = ["visitor"]
    dst.actions = [n for n in src.actions]
vis = bpy.data.collections["visitor"]
scene.collection.children.link(vis)
rig = bpy.data.objects["visitor rig"]
WALK_M = rig["walk_m_per_cycle"]

rows = P["path"]
speed = [0.0] * len(rows)
for i in range(1, len(rows)):
    a, b = rows[i - 1], rows[i]
    if not any(a[0] < c <= b[0] + 1e-9 for c in P["cuts"]):
        speed[i] = math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0])
cut_after = [any(rows[i][0] < c <= rows[i + 1][0] + 1e-9 for c in P["cuts"]) for i in range(len(rows) - 1)] + [False]


def unwrap(vals):
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] + (v - out[-1] + math.pi) % (2 * math.pi) - math.pi)
    return out


yaws = unwrap([r[4] + math.pi / 2 for r in rows])
fr = [frame_of_s(r[0]) for r in rows]
# where he is and which way he faces ride on an empty; the rig under it carries the clips and his look
walker = bpy.data.objects.new("visitor walker", None)
vis.objects.link(walker)
rig.parent = walker
rig.matrix_parent_inverse = Matrix.Identity(4)
rig.location, rig.rotation_euler = (0, 0, 0), (0, 0, 0)
walker.location = rows[0][1:4]
fill(walker, "location", fr, [tuple(r[1:4]) for r in rows])
fill(walker, "rotation_euler", fr, [(0.0, 0.0, y) for y in yaws])
for fc in fcurves(walker):
    for i, kp in enumerate(fc.keyframe_points):
        if i < len(cut_after) and cut_after[i]:
            kp.interpolation = "CONSTANT"


def act_at(s):
    for a in P["acts"]:
        if a["s0"] <= s < a["s1"]:
            return a
    return P["acts"][-1]


def plan_at(s):
    a, b, u = path_at(s)
    if any(a[0] < c <= b[0] + 1e-9 for c in P["cuts"]):
        u = 0.0  # across a cut he stays as he was until the jump
    da = (b[4] - a[4] + math.pi) % (2 * math.pi) - math.pi
    dh = (b[5] - a[5] + math.pi) % (2 * math.pi) - math.pi
    i = min(max(int(s / DT), 0), len(rows) - 2)
    return {"body": a[4] + da * u, "head": a[5] + dh * u, "pitch": a[6] + (b[6] - a[6]) * u,
            "gait": a[7] + (b[7] - a[7]) * u, "speed": speed[i + 1], "turn": abs(da) / DT}


CLIPS = ["Idle_Loop", "Walk_Loop", "Interact", "Sitting_Enter", "Sitting_Idle_Loop"]


def align_quaternions():
    """Every clip's bone rotations on the same side as standing still's, so blending two clips never
    passes through a zero quaternion (q and -q are one pose, but their average is no pose at all)."""
    ref = {}
    for fc in action_curves(bpy.data.actions["Idle_Loop"]):
        if fc.data_path.endswith("rotation_quaternion") and fc.keyframe_points:
            ref.setdefault(fc.data_path, [1.0, 0.0, 0.0, 0.0])[fc.array_index] = fc.keyframe_points[0].co[1]
    flipped = 0
    for clip in CLIPS:
        curves = {}
        for fc in action_curves(bpy.data.actions[clip]):
            if fc.data_path.endswith("rotation_quaternion"):
                curves.setdefault(fc.data_path, {})[fc.array_index] = fc
        for path, cs in curves.items():
            r = ref.get(path, [1.0, 0.0, 0.0, 0.0])
            if len(cs) != 4 or len({len(c.keyframe_points) for c in cs.values()}) != 1:
                print("cannot align", clip, path)
                continue
            for k in range(len(cs[0].keyframe_points)):
                q = [cs[i].keyframe_points[k].co[1] for i in range(4)]
                if sum(a * b for a, b in zip(q, r)) < 0:
                    flipped += 1
                    for i in range(4):
                        kp = cs[i].keyframe_points[k]
                        kp.co[1], kp.handle_left[1], kp.handle_right[1] = -kp.co[1], -kp.handle_left[1], -kp.handle_right[1]
            for c in cs.values():
                c.update()
    print("quaternion keys flipped to one side:", flipped)


align_quaternions()
ACT_CLIP = {"interact": "Interact", "sit_enter": "Sitting_Enter", "sit_idle": "Sitting_Idle_Loop"}
BLEND = 0.25  # s to fade from one act's clip to the next


def clip_weights(s):
    """Each clip's share of the pose at film second s (they add to 1), and where in it he is."""
    a = act_at(s)
    pa = plan_at(s)
    w = {c: 0.0 for c in CLIPS}
    if a["act"] in ("walk", "turn"):
        # walking, the clip runs by distance, so the stride keeps pace with him at any speed;
        # turning on the spot he stands, and his feet step round with him (the foot lock below)
        moving = 1.0 if a["act"] == "walk" else 0.0
        w["Walk_Loop"] = moving
        w["Idle_Loop"] = 1.0 - moving
    elif a["act"] in ACT_CLIP:
        w[ACT_CLIP[a["act"]]] = 1.0
    else:
        w["Idle_Loop"] = 1.0
    # fade in from the act before
    k = P["acts"].index(a)
    if k > 0 and s - a["s0"] < BLEND and not any(abs(c - a["s0"]) < 1e-6 for c in P["cuts"]):
        u = (s - a["s0"]) / BLEND
        prev = clip_weights(a["s0"] - 1e-4)[0]
        w = {c: prev[c] * (1 - u) + w[c] * u for c in CLIPS}
    return w, a


def clip_frame(clip, s, a):
    act = bpy.data.actions[clip]
    f0, f1 = act.frame_range
    n = f1 - f0
    if clip == "Walk_Loop":
        return f0 + (walk_phase(s) % 1.0) * n
    if clip in ("Idle_Loop", "Sitting_Idle_Loop"):
        return f0 + ((s * FPS) % n)
    # a one-shot plays from the start of its own act, sped up if that act is shorter than the clip;
    # fading out under the next act, it holds where it got to
    k = P["acts"].index(a)
    own = a if ACT_CLIP.get(a["act"]) == clip else None
    if own is None and k > 0 and ACT_CLIP.get(P["acts"][k - 1]["act"]) == clip:
        own = P["acts"][k - 1]
    if own is None:
        return f0
    rate = max(1.0, (n / FPS) / max(own["s1"] - own["s0"], 1e-3))
    return f0 + min(n, (s - own["s0"]) * FPS * rate)


ad = rig.animation_data or rig.animation_data_create()
for t in list(ad.nla_tracks):
    ad.nla_tracks.remove(t)


def first_step_phase():
    """A walk starts mid-swing: one foot flat under him and the other passing it, which is how a standing
    person's first step looks (both feet beside each other), so the blend from standing moves only the lifted foot."""
    act = bpy.data.actions["Walk_Loop"]
    ad.action = act
    if hasattr(ad, "action_slot") and act.slots:
        ad.action_slot = act.slots[0]
    f0, f1 = act.frame_range
    best = (1e9, 0.0)
    for j in range(48):
        u = j / 48
        scene.frame_set(int(f0 + u * (f1 - f0)), subframe=(f0 + u * (f1 - f0)) % 1.0)
        z = [(rig.matrix_world @ rig.pose.bones["ball_" + x].head).z - rig.matrix_world.translation.z for x in "lr"]
        best = min(best, (-max(z), u))
    ad.action = None
    print("walk starts at phase", round(best[1], 3), "swing foot up", round(-best[0], 3))
    return best[1]


PHI0 = first_step_phase()
VMIN = 0.6  # m/s: starting and stopping, his steps keep at least this pace's rhythm (shorter, never slow-motion)
_WP = []


def walk_phase(s):
    """Where in the walk cycle he is: each walk starts on its first step, then runs by distance,
    never slower than VMIN's cadence; the foot lock keeps the shorter steps from sliding."""
    if not _WP:
        ph = PHI0
        last = None
        for j in range(NF + 2):
            t = j / FPS
            a = act_at(t)
            if a["act"] == "walk":
                if a is not last:
                    ph = PHI0
                ph += max(plan_at(t)["speed"], VMIN) / FPS / WALK_M
                last = a
            _WP.append(ph)
    return _WP[min(len(_WP) - 1, max(0, int(round(s * FPS))))]
STRIPS = {}
for clip in CLIPS:
    act = bpy.data.actions[clip]
    tr = ad.nla_tracks.new()
    tr.name = clip
    st = tr.strips.new(clip, 1, act)
    if hasattr(st, "action_slot") and act.slots:
        st.action_slot = act.slots[0]
    try:  # one strip over the whole film; the time in it is keyed
        st.frame_end_ui = NF + 1
    except AttributeError:
        st.frame_end = NF + 1
    st.blend_type = "REPLACE"
    st.use_animated_influence = True
    st.use_animated_time = True
    STRIPS[clip] = st

# per frame: influences (bottom to top, each over what is below it) and times in each clip
frames = list(range(1, NF + 1))
inf = {c: [] for c in CLIPS}
tim = {c: [] for c in CLIPS}
TOP = {}
for f in frames:
    s = (f - 1) / FPS
    w, a = clip_weights(s)
    # effective shares -> replace-stack influences, top first
    rest = 1.0
    stack = {}
    for c in reversed(CLIPS):
        share = w[c]
        stack[c] = 0.0 if rest <= 1e-9 else min(1.0, share / rest)
        rest -= share
    stack["Idle_Loop"] = 1.0
    for c in CLIPS:
        inf[c].append(stack[c])
        tim[c].append(clip_frame(c, s, a))
    TOP[f] = max(CLIPS, key=lambda c: w[c])
for c, st in STRIPS.items():
    for prop, vals in (("influence", inf[c]), ("strip_time", tim[c])):
        fc = st.fcurves.find(prop)
        if fc is None:
            st.keyframe_insert(prop, frame=1)
            fc = st.fcurves.find(prop)
        fc.keyframe_points.clear()
        fc.keyframe_points.add(len(frames))
        fc.keyframe_points.foreach_set("co", [x for f, v in zip(frames, vals) for x in (f, v)])
        fc.keyframe_points.foreach_set("interpolation", [1] * len(frames))
        fc.update()

# ------------------------------------------------------------------------- his feet and his eyes
# First the clips alone are played through and measured: where each foot's ball and ankle are, and where
# his face points. Only his collection is evaluated, his clothes off, so this is quick.
layer_children = scene.view_layers[0].layer_collection.children
saved_exclude = {lc.name: lc.exclude for lc in layer_children}
for lc in layer_children:
    lc.exclude = lc.name != "visitor"
garment_obs = [o for o in vis.objects if "garment" in o]
for o in garment_obs:
    o.hide_viewport = True
ad.action = None
FWD_HEAD = rig.data.bones["Head"].matrix_local.to_3x3().inverted() @ Vector((0, -1, 0))
BALL = {"l": [], "r": []}
ANKLE = {"l": [], "r": []}
TILT = {"l": [], "r": []}  # each foot's own turn in the world, which the lock keeps
FACE_AT = []
FLOOR = []
for f in frames:
    scene.frame_set(f)
    mw = rig.matrix_world
    FLOOR.append(mw.translation.z)
    for side in "lr":
        BALL[side].append((mw @ rig.pose.bones["ball_" + side].head).copy())
        ANKLE[side].append((mw @ rig.pose.bones["foot_" + side].head).copy())
        q = (mw.to_3x3() @ rig.pose.bones["foot_" + side].matrix.to_3x3()).to_quaternion()
        if TILT[side] and TILT[side][-1].dot(q) < 0:
            q = -q
        TILT[side].append(q)
    hd = (mw.to_3x3() @ rig.pose.bones["Head"].matrix.to_3x3() @ FWD_HEAD).normalized()
    FACE_AT.append((math.atan2(hd.y, hd.x), math.asin(max(-1.0, min(1.0, hd.z)))))

# The foot lock. A foot that the clip puts on the floor stays where it landed: its leg reaches it by IK.
# When the body has moved too far from a planted foot (starting, stopping, turning on the spot) the foot
# takes a short lifted step to where the clip wants it; the two feet never step at once.
DOWN, UP_AT, STEP_AT, STEP_N, LIFT, REACH = 0.035, 0.055, 0.10, 6, 0.07, 0.12
state = {side: {"mode": "free", "d": Vector((0, 0, 0))} for side in "lr"}
SHIFT = {"l": [], "r": []}
LOCK = {"l": [], "r": []}
for i, f in enumerate(frames):
    jumped = i > 0 and any((f - 2) / FPS < c <= (f - 1) / FPS + 1e-9 for c in P["cuts"])
    for side in "lr":
        m, other = state[side], state["r" if side == "l" else "l"]
        b = BALL[side][i]
        down = b.z <= FLOOR[i] + DOWN
        if jumped:
            m.clear()
            m.update(mode="free", d=Vector((0, 0, 0)))
        if m["mode"] == "step":
            u = (i - m["i0"]) / STEP_N
            if u >= 1.0:
                m["mode"], m["P"] = "planted", m["dest"].copy()
            else:
                e = u * u * (3 - 2 * u)
                to = m["Q"].lerp(m["dest"], e)
                m["d"] = Vector((to.x - b.x, to.y - b.y, LIFT * math.sin(math.pi * u)))
        if m["mode"] == "planted" and m.get("held"):
            # held to the floor while the clip has both feet up at a slow pace; let go once the other lands
            if other["mode"] == "planted" and not other.get("held"):
                m["mode"], m["held"] = "free", False
            else:
                m["d"] = Vector((m["P"].x - b.x, m["P"].y - b.y, min(0.0, m["P"].z - b.z)))
        elif m["mode"] == "planted":
            if b.z > FLOOR[i] + UP_AT:  # let go only once the clip has clearly lifted it
                m["mode"] = "free"
            else:
                d = Vector((m["P"].x - b.x, m["P"].y - b.y, 0.0))
                oside = "r" if side == "l" else "l"
                other_stays = all(BALL[oside][j].z <= FLOOR[j] + UP_AT for j in range(i, min(i + STEP_N + 1, len(frames))))
                if d.length > STEP_AT and other["mode"] == "planted" and other_stays:
                    j = min(i + STEP_N, len(frames) - 1)
                    m.update(mode="step", i0=i, Q=m["P"].copy(), dest=BALL[side][j].copy())
                elif d.length > REACH and act_at((f - 1) / FPS)["act"] == "walk" and plan_at((f - 1) / FPS)["speed"] < 0.6:
                    # setting off, it cannot step yet (the other foot is up): rather than stretch the leg, it gives
                    d = d * (REACH / d.length)
                    m["P"] = Vector((b.x + d.x, b.y + d.y, m["P"].z))
                m["d"] = d
        if m["mode"] == "free":
            m["d"] = m["d"] * 0.55 if m["d"].length > 0.003 else Vector((0, 0, 0))
            if down:
                m.update(mode="planted", held=False, P=Vector((b.x + m["d"].x, b.y + m["d"].y, b.z)))
    # one foot is always on the floor unless he is walking at pace: at a slow start or stop, when the clip
    # has both feet in the air, the lower one is held down where it is
    if all(state[x]["mode"] == "free" for x in "lr") and plan_at((f - 1) / FPS)["speed"] < 0.8:
        low = min("lr", key=lambda x: BALL[x][i].z)
        m, b = state[low], BALL[low][i]
        m.update(mode="planted", held=True, P=Vector((b.x + m["d"].x, b.y + m["d"].y, FLOOR[i] + 0.015)))
        m["d"] = Vector((m["P"].x - b.x, m["P"].y - b.y, min(0.0, m["P"].z - b.z)))
    for side in "lr":
        m = state[side]
        SHIFT[side].append(m["d"].copy())
        LOCK[side].append(0.0 if m["mode"] == "free" and m["d"].length < 1e-4 else 1.0)
for side in "lr":
    tgt = bpy.data.objects.new("visitor foot target " + side, None)
    vis.objects.link(tgt)
    fill(tgt, "location", frames, [tuple(ANKLE[side][i] + SHIFT[side][i]) for i in range(len(frames))])
    tgt.rotation_mode = "QUATERNION"
    fill(tgt, "rotation_quaternion", frames, [tuple(q) for q in TILT[side]])
    tgt["lock"] = 0.0
    fill(tgt, '["lock"]', frames, LOCK[side])
    # the foot keeps the clip's angle to the floor, whatever the IK does to the shin above it
    keep = rig.pose.bones["foot_" + side].constraints.new("COPY_ROTATION")
    keep.name = "foot angle"
    keep.target = tgt
    keep.target_space = keep.owner_space = "WORLD"
    kd = keep.driver_add("influence").driver
    kd.type = "AVERAGE"
    kv = kd.variables.new()
    kv.type = "SINGLE_PROP"
    kv.targets[0].id = tgt
    kv.targets[0].data_path = '["lock"]'
    ik = rig.pose.bones["calf_" + side].constraints.new("IK")
    ik.name = "foot lock"
    ik.target = tgt
    ik.chain_count = 2
    ik.use_tail = True
    ik.use_stretch = False
    drv = ik.driver_add("influence").driver
    drv.type = "AVERAGE"
    var = drv.variables.new()
    var.type = "SINGLE_PROP"
    var.targets[0].id = tgt
    var.targets[0].data_path = '["lock"]'
if REPORT:  # what the lock did, frame by frame, beside the report
    (REPORT.parent / "footlock.json").write_text(json.dumps({side: [[round(BALL[side][i].x, 4), round(BALL[side][i].y, 4), round(BALL[side][i].z - FLOOR[i], 4), round(SHIFT[side][i].x, 4), round(SHIFT[side][i].y, 4), round(SHIFT[side][i].z, 4), LOCK[side][i]] for i in range(len(frames))] for side in "lr"}))
print("foot lock: steps", sum(1 for side in "lr" for a, b in zip(LOCK[side], LOCK[side][1:]) if a < b))

# His head and neck turn by what the clip leaves to do: from where the clip has his face to where the
# plan looks (never past his shoulder), combined over the clip so its breathing stays.
look = bpy.data.actions.new("visitor look")
ad.action = look
if hasattr(ad, "action_slot") and look.slots:
    ad.action_slot = look.slots[0]
ad.action_blend_type = "COMBINE"
UP = Vector((0, 0, 1))
RIGHT = Vector((1, 0, 0))  # his left-right axis in the rig: a turn about it is a nod


def local_q(bone, q_arm):
    r = bone.matrix_local.to_quaternion()
    return r.inverted() @ q_arm @ r


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


SHARE = {"neck_01": 0.35, "Head": 0.65}
qs = {b: [] for b in SHARE}
for i, f in enumerate(frames):
    s = (f - 1) / FPS
    pa = plan_at(s)
    body = pa["body"]
    want = body + max(-math.radians(100), min(math.radians(100), wrap(pa["head"] - body)))
    yaw = wrap(want - FACE_AT[i][0])
    nod = pa["pitch"] - FACE_AT[i][1]
    for bname, k in SHARE.items():
        q = Quaternion(UP, yaw * k) @ Quaternion(RIGHT, -nod * k)
        qs[bname].append(local_q(rig.data.bones[bname], q))
for bname, vals in qs.items():
    pb = rig.pose.bones[bname]
    pb.rotation_mode = "QUATERNION"
    path = f'pose.bones["{bname}"].rotation_quaternion'
    out = []
    prev = None
    for q in vals:
        if prev is not None and prev.dot(q) < 0:
            q = -q
        prev = q
        out.append(q)
    for i in range(4):
        fc = look.fcurve_ensure_for_datablock(rig, path, index=i) if hasattr(look, "fcurve_ensure_for_datablock") else look.fcurves.new(path, index=i)
        fc.keyframe_points.add(len(frames))
        fc.keyframe_points.foreach_set("co", [x for f, q in zip(frames, out) for x in (f, q[i])])
        fc.update()
for lc in layer_children:
    lc.exclude = saved_exclude.get(lc.name, False)
for o in garment_obs:
    o.hide_viewport = False

# his clothes: street, then the suit from the lapse on
lapse_f = frame_of_s([o["s"] for o in P["outfit"] if o["wear"] == "suit"][0])
GARMENTS = {}
for ob in vis.objects:
    if "garment" in ob:
        GARMENTS[ob["garment"]] = ob
        street = ob["outfit"] == "street"
        for f, shown in ((1, street), (lapse_f, not street)):
            ob.hide_render = not shown
            ob.keyframe_insert("hide_render", frame=f)
        for fc in fcurves(ob):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
body = bpy.data.objects["visitor body"]
for k in ("street", "suit"):
    md = body.modifiers["skin under " + k]
    for f, on in ((1, k == "street"), (lapse_f, k == "suit")):
        md.show_render = md.show_viewport = on
        md.keyframe_insert("show_render", frame=f)
        md.keyframe_insert("show_viewport", frame=f)
brows = bpy.data.objects["visitor brows"]
for f, hidden in ((1, False), (lapse_f, True)):
    brows.hide_render = hidden
    brows.keyframe_insert("hide_render", frame=f)
for o in (body, brows):
    for fc in fcurves(o):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"

# ------------------------------------------------------------------------- signs: white, a stripe, a name
STRIPE_FROM = CEIL - 0.68
FACE = "#f4f5f6"
font_col = collection("sign names")
TEXT = principled("v sign text", "#2c3136", rough=0.6)
for area, info in S["areas"].items():
    m = bpy.data.materials.get("sign " + area)
    if m is None:
        continue
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    cmp_ = nt.nodes.new("ShaderNodeMath")
    cmp_.operation = "GREATER_THAN"
    cmp_.inputs[1].default_value = STRIPE_FROM
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = srgb(FACE) + [1]
    mix.inputs["B"].default_value = srgb(info["colour"]) + [1]
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], cmp_.inputs[0])
    nt.links.new(cmp_.outputs[0], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Emission Color"].default_value = (1, 1, 1, 1)
    bsdf.inputs["Emission Strength"].default_value = 0.25
    bsdf.inputs["Roughness"].default_value = 0.5
    m["face"], m["stripe"], m["emit"] = FACE, info["colour"], 0.25
for b in S["bays"]:
    cx = (b["x0"] + b["x1"]) / 2
    north = b["side"] == 0
    ys = SP / 2 + 0.2 if north else -SP / 2 - 0.2
    cu = bpy.data.curves.new("name " + b["area"], "FONT")
    cu.body = S["areas"][b["area"]]["name"]
    cu.size = 0.2
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.materials.append(TEXT)
    t = bpy.data.objects.new(f"sign name {b['phase']} {b['side']} {cx:.1f}", cu)
    t.location = (cx, ys - 0.035 if north else ys + 0.035, CEIL - 0.88)
    t.rotation_euler = (math.pi / 2, 0, 0 if north else math.pi)
    font_col.objects.link(t)

# ------------------------------------------------------------------------- the camera
cam = bpy.data.objects.new("visitor camera", bpy.data.cameras.new("visitor camera"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.sensor_fit = "VERTICAL"
cam.data.angle_y = math.radians(P["fov_v"])
cam.data.clip_start, cam.data.clip_end = 0.05, 5000
cam.data.dof.use_dof = True
cam.data.dof.aperture_fstop = 5.6
cam.rotation_mode = "QUATERNION"
crow = P["camera"]
cfr = [frame_of_s(c[0]) for c in crow]
quats, prev = [], None
for c in crow:
    q = (Vector(c[4:7]) - Vector(c[1:4])).to_track_quat("-Z", "Y")
    if prev is not None and prev.dot(q) < 0:
        q = -q
    prev = q
    quats.append(tuple(q))
fill(cam, "location", cfr, [tuple(c[1:4]) for c in crow])
fill(cam, "rotation_quaternion", cfr, quats)
ccut = [any(crow[i][0] < cc <= crow[i + 1][0] + 1e-9 for cc in P["camera_cuts"]) for i in range(len(crow) - 1)] + [False]
for fc in fcurves(cam):
    for i, kp in enumerate(fc.keyframe_points):
        if ccut[i]:
            kp.interpolation = "CONSTANT"
focus = [math.dist(c[1:4], (r[1], r[2], r[3] + 1.3)) for c, r in zip(crow, rows)]
for f, d_ in zip(cfr, focus):
    cam.data.dof.focus_distance = d_
    cam.data.dof.keyframe_insert("focus_distance", frame=f)

# ------------------------------------------------------------------------- render settings
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = RES
scene.render.resolution_percentage = 100
try:
    scene.eevee.taa_render_samples = SAMPLES
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.35
except AttributeError:
    pass

# ------------------------------------------------------------------------- the report
VISITOR_COLS = {"visitor", "way in", "way in lights", "way in props", "way in doors", "sign names"}


def report():
    rep = {"what": "What viz/blender/visitor.py built, read back from Blender, for viz/tests/test_visitor_blender.py.",
           "badge": P["badge"], "fps": FPS, "frames": [1, NF], "fov_v": round(math.degrees(cam.data.angle_y), 4)}
    # film-only things, and anything of the fab that hides on a key
    left = sorted(o.name for o in bpy.data.objects if o.name.startswith(FILM_ONLY) and o.name != "visitor camera")
    hidden = []
    mine = {o.name for c in VISITOR_COLS if c in bpy.data.collections for o in bpy.data.collections[c].all_objects}
    for o in bpy.data.objects:
        if o.name in mine or o.name == "visitor camera":
            continue
        for fc in fcurves(o):
            if fc.data_path in ("hide_render", "hide_viewport") and any(k.co[1] > 0.5 for k in fc.keyframe_points):
                hidden.append(o.name)
                break
    rep["removed"] = {"left": left, "hidden_ever": sorted(set(hidden))}
    # the run on this clock: sampled lamps and lots, read from their curves
    import random

    rnd = random.Random(11)
    lamp_obs = [o for o in bpy.data.objects if o.name.startswith("light ") and o.name[6:].isdigit()]
    rep["lamps"] = []
    for o in rnd.sample(lamp_obs, min(160, len(lamp_obs))):
        cs = {fc.array_index: fc for fc in fcurves(o) if fc.data_path == "color"}
        for f in rnd.sample(range(1, NF + 1), 10):
            rgba = [cs[i].evaluate(f) if i in cs else o.color[i] for i in range(4)]
            rep["lamps"].append([int(o.name[6:]), f, [round(v, 4) for v in rgba]])
    lot_obs = [o for o in bpy.data.objects if o.name.startswith("lot ")]
    rep["lots"] = []
    for o in rnd.sample(lot_obs, min(400, len(lot_obs))):
        loc = {fc.array_index: fc for fc in fcurves(o) if fc.data_path == "location"}
        sc = [fc for fc in fcurves(o) if fc.data_path == "scale"]
        for f in rnd.sample(range(1, NF + 1), 4):
            p = [loc[i].evaluate(f) for i in range(3)]
            shown = sc[0].evaluate(f) > 0.5 if sc else True
            rep["lots"].append([o.name[4:], f, *[round(v, 4) for v in p], shown])
    rep["rooms"] = [{k: b[k] for k in ("name", "inside", "openings")} for b in BUILT]
    rep["props"] = []
    for f_, ob in PLACED:
        ws = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        rep["props"].append({"id": f_["id"], "kind": f_["kind"], "min": [round(min(w[i] for w in ws), 4) for i in range(3)],
                             "max": [round(max(w[i] for w in ws), 4) for i in range(3)],
                             "asset": ob.data is PROP["prop " + f_["kind"]].data})
    rep["doors"] = DOORS
    rep["signs"] = {a: {"face": FACE, "stripe": i["colour"], "emit": bpy.data.materials["sign " + a]["emit"]}
                    for a, i in S["areas"].items() if bpy.data.materials.get("sign " + a)}
    # lithography's ceiling: yellow over its bays, white elsewhere
    yel = {"litho": {"yellow": False}, "other": {"yellow": False}}
    for ob in bpy.data.objects:
        if not ob.name.endswith(" ceiling") or ob.type != "MESH":
            continue
        for p in ob.data.polygons:
            c = ob.matrix_world @ p.center
            bay = [b for b in S["bays"] if b["x0"] < c.x < b["x1"] and b["y0"] < c.y < b["y1"]]
            if not bay or abs(c.z - CEIL) > 0.2:
                continue
            m = ob.data.materials[p.material_index].name
            key = "litho" if bay[0]["area"] == "Litho" else "other"
            if "yellow" in m:
                yel[key]["yellow"] = True
    rep["light"] = yel
    rep["garments"] = {n: {"colour": o.data.materials[0]["colour"] if "colour" in o.data.materials[0] else "#000000", "shown": []}
                       for n, o in GARMENTS.items()}
    # frame by frame: the fab's heavy collections out of the way, then his pose, the camera, his clothes
    for lc in scene.view_layers[0].layer_collection.children:
        if lc.name not in VISITOR_COLS:
            lc.exclude = True
    fwd_head = rig.data.bones["Head"].matrix_local.to_3x3().inverted() @ Vector((0, -1, 0))
    rows_out, cams, clips = [], [], []
    for f in frames:
        scene.frame_set(f)
        mw = rig.matrix_world
        fwd = mw.to_3x3() @ Vector((0, -1, 0))
        bl = mw @ rig.pose.bones["ball_l"].head
        br = mw @ rig.pose.bones["ball_r"].head
        hd = (mw.to_3x3() @ rig.pose.bones["Head"].matrix.to_3x3() @ fwd_head).normalized()
        rows_out.append([f, *[round(v, 5) for v in mw.translation], round(math.atan2(fwd.y, fwd.x), 5),
                         *[round(v, 5) for v in bl], *[round(v, 5) for v in br],
                         round(math.atan2(hd.y, hd.x), 5), round(math.asin(max(-1, min(1, hd.z))), 5)])
        cm = cam.matrix_world
        cf = cm.to_quaternion() @ Vector((0, 0, -1))
        cams.append([f, *[round(v, 5) for v in cm.translation], *[round(v, 6) for v in cf]])
        clips.append([f, TOP[f]])
        if f % 6 == 1 or abs(f - lapse_f) < 2:
            for n, o in GARMENTS.items():
                rep["garments"][n]["shown"].append([f, not o.hide_render])
    rep["person"] = {"frames": rows_out, "clips": clips, "height": rig["height"], "eye": rig["eye"],
                     "walk_m_per_cycle": WALK_M, "walk_speed": rig["walk_speed"]}
    rep["camera"] = cams
    REPORT.write_text(json.dumps(rep))
    print("report", REPORT, len(rows_out), "frames")


if REPORT:
    report()
    sys.exit(0)

if "--nosave" not in argv:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "visitor.blend"), compress=True)
scene.render.image_settings.file_format = "JPEG"
scene.render.image_settings.quality = 92
if STILLS is not None:
    scene.render.image_settings.file_format = "PNG"
    for s_ in STILLS:
        scene.frame_set(int(round(frame_of_s(s_))))
        scene.render.filepath = str(OUT / f"still-{s_:07.3f}.png")
        bpy.ops.render.render(write_still=True)
elif FR:
    scene.frame_start, scene.frame_end = FR
    scene.render.filepath = str(OUT / "frames" / "v")
    bpy.ops.render.render(animation=True)
print("done", OUT)
