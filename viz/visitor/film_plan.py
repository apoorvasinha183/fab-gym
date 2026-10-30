"""A Walk Through the Fab, the Blender film: where the visitor goes, how he moves, and the camera.

A gigafab-style layout of our own design from the SMT2020 testbed; not a real fab. The first cut
(plan.py, played in Godot) walked like a machine: instant starts and stops, turns on the spot
without a step, paths along the walls. This plan is made for the Blender film and moves like a
person:

- every walk follows a speed profile: he speeds up and slows down at 1.0 m/s2, never faster than
  1.3 m/s, slows into curves (sideways acceleration at most 0.55 m/s2) and rounds corners with
  1.4 m curves; a corner sharper than 100 degrees is a stop and a turn;
- a turn on the spot is made of steps: his gait distance (what the walk cycle is played by, so the
  feet never slide) grows 0.3 m for every radian he turns;
- indoors he walks down the middle, keeps clear of walls and furniture, and goes through doors
  square on; the rooms of the way in are ours, drawn only, with their doors and furniture;
- the way in is the one people take: from his car to the office door, a badge tap at the
  turnstile, the lift (the ride is a cut), the bridge, the gowning room (he sits on the bench over
  the line; a time-lapse puts him in the suit on the clean side; a mirror check), the air shower;
- on the clean floor the run decides where he goes, scored as in plan.py:
  severity x novelty / (1 + walk seconds / 15), where the walk seconds are the walk he will make
  (the turn and the profile);
- the camera glides (at most 2.8 m/s, eased), never sits inside a wall, a tool or furniture,
  keeps him within 18 degrees of the middle of the frame and the sight in frame while he watches.

The visitor, his car and the rooms of the way in are drawn only: they are not in the model and no
number comes from them. Every number on a card is the run's. Standard library and plan.py only;
the same seed gives the same plan.

    python3 viz/visitor/film_plan.py SCENE TRACE OUT [--seed N]
"""

import json
import copy
import math
import sys
from pathlib import Path

import plan as base
from plan import Floor, Line, Planner, ang3, inside, q, smooth, toward, wrap

base.FILLET = 1.4  # corners rounded with 1.4 m curves where the room allows

FPS = 24
DT = 0.125
V = 1.3  # m/s, walking
ACC = 1.0  # m/s2, speeding up and slowing down (about two steps to full pace)
LAT = 0.55  # m/s2, sideways in a curve
RATE_MAX = 2.5  # rad/s, the most his heading turns while walking
STEP = 0.3  # m of gait for each radian turned on the spot
V_EXIT = 1.0  # m/s as he steps out of the air shower onto the clean floor
TURN_RATE = 2.1  # rad/s, on average, a turn on the spot (at most 1.5 times that at its quickest)
HEAD_RATE = 4.0  # rad/s, quicker than his body: the eyes lead
EYE = 1.6
SHARP = math.radians(100)  # a corner sharper than this is a stop and a turn
DS = 0.02
RATE = {"walk": 60, "watch": 10}
WATCH, WATCH_BIG = 6.0, 8.0
BEFORE = 1.5
LOOK_AHEAD = 3.5  # s: the furthest out his eyes go to a sight
EASY_LOOK = math.radians(70)  # an easy turn of the head from where the body points
MAX_SIGHTS = 6
MAX_FILM = 134.0
MAX_WALK = 30.0
MIN_SIGHTS = 4  # the tour keeps time for at least this many
MIN_KINDS = 3  # and they show at least this many kinds of thing
BRANCH = 5  # next sights tried at each step when checking that the tour still fits
WALK_SCALE = 15.0
CLOSE = 5.0
IN_FRAME = 18.0
CAM_STEP = 2.8 * DT  # the most the camera moves in a sample
CAM_TAU = 0.5  # s, how quickly the camera follows
FOV_V = 42.0
BADGE = ("A gigafab-style layout of our own design from the SMT2020 testbed, not a real fab. "
         "The visitor is drawn only; he is not in the model. Every number is the run's.")
STILL = {"stand", "interact", "sit_enter", "sit_idle", "lift", "mirror", "shower", "watch", "close"}


def rect(name, kind, x0, x1, y0, y1, z0, z1, doors=(), furniture=()):
    return {"name": name, "kind": kind, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "z0": z0, "z1": z1,
            "doors": list(doors), "furniture": list(furniture)}


def door(wall, at, w, h=2.1, kind="single"):
    return {"wall": wall, "at": at, "w": w, "h": h, "kind": kind}


def thing(fid, kind, x0, x1, y0, y1, z0, z1):
    return {"id": fid, "kind": kind, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "z0": z0, "z1": z1}


def radius_at(line, s):
    for p, n in zip(line.prims, line.lens):
        if s <= n + 1e-12 or p is line.prims[-1]:
            return p[2] if p[0] == "a" else None
        s -= n
    return None


def profile(line, v0=0.0, v1=0.0):
    """Arc lengths and the times he reaches them, speeding up, slowing into curves and to a stop."""
    L = line.length
    n = max(2, int(math.ceil(L / DS)))
    ss = [L * i / n for i in range(n + 1)]
    v = []
    for s in ss:
        r = radius_at(line, s)
        v.append(V if r is None else min(V, math.sqrt(LAT * r), RATE_MAX * r))
    v[0] = min(v[0], v0)
    v[-1] = min(v[-1], v1)
    for i in range(n):
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2 * ACC * (ss[i + 1] - ss[i])))
    for i in range(n, 0, -1):
        v[i - 1] = min(v[i - 1], math.sqrt(v[i] ** 2 + 2 * ACC * (ss[i] - ss[i - 1])))
    t = [0.0]
    for i in range(n):
        t.append(t[-1] + (ss[i + 1] - ss[i]) / max((v[i] + v[i + 1]) / 2, 1e-3))
    return ss, t


def turn_samples(delta):
    return max(4, int(math.ceil(abs(delta) / TURN_RATE / DT - 1e-9)))


def split_sharp(pts):
    """Pieces of a polyline, cut at corners sharper than SHARP."""
    clean = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, clean[-1]) > 1e-6:
            clean.append(p)
    out, cur = [], [clean[0]]
    for i in range(1, len(clean)):
        cur.append(clean[i])
        if i < len(clean) - 1:
            a, b, c = clean[i - 1], clean[i], clean[i + 1]
            th = wrap(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]))
            if abs(th) > SHARP:
                out.append(cur)
                cur = [clean[i]]
    out.append(cur)
    return [p for p in out if len(p) > 1]


def walk_time(pts, body, v0=0.0):
    """Film seconds to turn toward and walk a polyline to rest (from v0 if he is already walking),
    as go() will make it."""
    n = 0
    h = body
    for pi, piece in enumerate(split_sharp(pts)):
        line = Line(piece)
        first = line.at(0.0)[1]
        moving = v0 > 0 and pi == 0
        if not moving and first is not None and abs(wrap(first - h)) > math.radians(3):
            n += turn_samples(wrap(first - h))
        ss, t = profile(line, v0 if pi == 0 else 0.0, 0.0)
        n += int(math.ceil(t[-1] / DT - 1e-9))
        h = line.at(line.length)[1] if line.at(line.length)[1] is not None else h
    return n * DT


class FilmPlanner(Planner):
    def __init__(self, s, tr, seed):
        super().__init__(s, tr, seed)
        self.samples = []  # [s, x, y, z, body, head, pitch, gait]
        self.acts = []
        self.gait = 0.0
        self.speed_now = 0.0
        self.marks = []  # (stage name, film s)
        self.captions = []
        self.room_cam = []  # (s0, s1, cam, mode)
        self.lapse = None
        self.v_carry = 0.0  # speed he carries into the next walk
        self.after_cut = False

    # emitting samples

    def act(self, name, at=None):
        if self.acts and self.acts[-1]["act"] == name and self.acts[-1].get("at") == at:
            return
        if self.acts:
            self.acts[-1]["s1"] = self.now
        a = {"act": name, "s0": self.now, "s1": None}
        if at:
            a["at"] = at
        self.acts.append(a)

    def put(self, x, y, z, body, head_t=None, pitch_t=0.0):
        """One sample. His gait grows with the ground covered and 0.3 m for each radian turned."""
        prev = self.samples[-1] if self.samples else None
        d = 0.0 if (prev is None or self.after_cut) else math.hypot(x - prev[1], y - prev[2])
        turned = 0.0 if (prev is None or self.after_cut) else abs(wrap(body - prev[4]))
        self.after_cut = False
        self.body = wrap(body)
        self.head = toward(self.head, head_t if head_t is not None else self.body, HEAD_RATE * DT)
        rel = wrap(self.head - self.body)
        if abs(rel) > math.radians(100):
            self.head = wrap(self.body + math.copysign(math.radians(100), rel))
        self.pitch += max(-2.0 * DT, min(2.0 * DT, (pitch_t or 0.0) - self.pitch))
        self.gait += d + STEP * turned
        self.pos = (x, y, z)
        self.samples.append([self.now, x, y, z, self.body, self.head, self.pitch, self.gait])
        self.meta.append({"stage": self.stage})
        self.idx += 1

    def head_for(self, head, head_at):
        return head if head is not None and head_at is not None and self.now >= head_at - 1e-9 else None

    def walk(self, pts, v0=0.0, v1=0.0, rate="walk", head=None, head_at=None, pitch=0.0):
        """Walk a polyline: turn toward each piece by stepping, then follow its speed profile."""
        z = self.pos[2]
        pieces = split_sharp(pts)
        for pi, piece in enumerate(pieces):
            line = Line(piece)
            first = line.at(0.0)[1]
            moving = v0 > 0 and pi == 0
            if not moving and first is not None and abs(wrap(first - self.body)) > math.radians(3):
                self.turn(first, rate=rate, head=head, head_at=head_at, pitch=pitch)
            a0 = v0 if pi == 0 else 0.0
            a1 = v1 if pi == len(pieces) - 1 else 0.0
            ss, t = profile(line, a0, a1)
            T = t[-1]
            n = max(1, int(math.ceil(T / DT - 1e-9)))
            scale = n * DT / T if T > 0 else 1.0
            self.knot(rate, n * DT)
            self.act("walk")
            j = 0
            for k in range(n):
                tt = k * DT / scale
                while j < len(t) - 2 and t[j + 1] < tt:
                    j += 1
                u = 0.0 if t[j + 1] == t[j] else (tt - t[j]) / (t[j + 1] - t[j])
                sl = ss[j] + (ss[j + 1] - ss[j]) * max(0.0, min(1.0, u))
                (x, y), h = line.at(sl)
                ht = self.head_for(head, head_at)
                self.put(x, y, z, h if h is not None else self.body, ht, pitch if ht is not None else 0.0)
            end = line.at(line.length)
            self.pos = (end[0][0], end[0][1], z)

    def turn(self, to, rate="walk", head=None, head_at=None, act="turn", pitch=0.0):
        """A turn on the spot, made of steps; the last sample faces the new way."""
        delta = wrap(to - self.body)
        n = turn_samples(delta)
        self.knot(rate, n * DT)
        self.act(act)
        b0 = self.body
        x, y, z = self.pos
        for k in range(1, n + 1):
            ht = self.head_for(head, head_at) if head_at is not None else (head if head is not None else to)
            self.put(x, y, z, wrap(b0 + delta * smooth(k / n)), ht, pitch)

    def hold(self, dur, act, at=None, head=None, pitch=0.0, rate="walk"):
        """Stand still for an act."""
        n = max(1, round(dur / DT))
        self.knot(rate, n * DT)
        self.act(act, at)
        x, y, z = self.pos
        for k in range(n):
            self.put(x, y, z, self.body, head, pitch)

    def jump(self, x, y, z, body):
        """A cut: he is somewhere else (the time between is not shown)."""
        self.cuts.append(self.now)
        self.after_cut = True
        self.pos = (x, y, z)
        self.body = self.head = body
        self.pitch = 0.0

    def mark(self, name, pred, from_idx):
        """The stage starts at the first sample from from_idx that meets pred."""
        for i in range(from_idx, len(self.samples)):
            p = self.samples[i]
            if pred(p[1], p[2]):
                self.marks.append((name, p[0]))
                return p[0]
        raise SystemExit(f"stage {name} never starts")

    # the way in

    def rooms_of_the_way_in(self):
        cz = self.cz
        office = [c for c in self.s["campus"] if c["kind"] == "office"][0]
        park = [c for c in self.s["campus"] if c["kind"] == "parking"][0]
        dx = 7.9  # the door's centre, on the office's north wall
        oy = office["y1"]
        self.dx, self.oy = dx, oy
        lob = rect("lobby", "room", office["x0"] + 2.0, office["x0"] + 16.0, oy - 6.5, oy, 0.0, 4.5,
                   doors=[door("n", dx, 2.4, 2.6, "glass sliding"), door("s", dx, 1.1, 2.2, "lift")])
        ty = oy - 3.0  # the turnstile line
        self.ty = ty
        cab = []
        for k in range(6):
            c = dx - 2.75 + 1.1 * k
            cab.append(thing(f"turnstile {k}", "turnstile", c - 0.1, c + 0.1, ty - 0.6, ty + 0.6, 0.0, 1.0))
        lob["furniture"] = cab + [
            thing("badge reader", "reader", dx + 0.5, dx + 0.6, ty + 0.35, ty + 0.55, 1.0, 1.1),
            thing("turnstile line", "mark", dx - 2.85, dx + 2.85, ty - 0.6, ty + 0.6, 0.0, 0.0),
            thing("barrier west", "glass barrier", lob["x0"], dx - 2.85, ty - 0.05, ty + 0.05, 0.0, 1.1),
            thing("barrier east", "glass barrier", dx + 2.85, lob["x1"], ty - 0.05, ty + 0.05, 0.0, 1.1),
            thing("reception", "desk", lob["x1"] - 4.0, lob["x1"] - 1.0, oy - 2.4, oy - 1.0, 0.0, 1.1),
            thing("lift panel", "panel", dx + 0.65, dx + 0.8, lob["y0"], lob["y0"] + 0.08, 1.0, 1.3),
            thing("planter", "planter", lob["x0"], lob["x0"] + 1.2, oy - 2.2, oy - 1.0, 0.0, 0.9),
            thing("bench lobby", "sofa", lob["x0"] + 0.2, lob["x0"] + 2.2, lob["y0"] + 0.4, lob["y0"] + 1.3, 0.0, 0.8),
        ]
        lift = rect("lift", "lift", dx - 1.2, dx + 1.2, lob["y0"] - 2.6, lob["y0"], 0.0, 3.0,
                    doors=[door("n", dx, 1.1, 2.2, "lift")])
        bx = -3.0  # the bridge and the corridor run down the fab's west strip
        bridge = rect("bridge", "bridge", bx - 1.5, bx + 1.5, 70.0, office["y0"], cz, cz + 3.5,
                      doors=[door("s", bx, 1.6, 2.4, "glass sliding")])
        corridor = rect("corridor", "corridor", bx - 1.5, bx + 1.5, 9.0, 70.0, cz, cz + 3.0,
                        doors=[door("n", bx, 1.6, 2.4, "glass sliding"), door("s", bx, 1.2, 2.2, "single")])
        gown = rect("gowning", "room", -6.0, 0.0, -2.0, 9.0, cz, cz + 3.0,
                    doors=[door("n", bx, 1.2, 2.2, "single"), door("e", 0.0, 0.9, 2.1, "interlock")])
        gown["furniture"] = [
            thing("bench", "bench", -5.6, -0.4, 4.8, 5.2, cz, cz + 0.45),
            thing("lockers", "lockers", -5.95, -5.5, 5.8, 8.6, cz, cz + 2.0),
            thing("shoe rack", "rack", -0.75, -0.25, 6.0, 8.4, cz, cz + 1.2),
            thing("gown rack", "gown rack", -5.95, -5.45, 0.5, 3.5, cz, cz + 1.8),
            thing("mirror", "mirror", -3.6, -2.6, -1.98, -1.95, cz + 0.5, cz + 2.1),
            thing("glove box", "dispenser", -0.3, -0.05, 2.0, 2.6, cz + 1.0, cz + 1.4),
            thing("sticky mat", "mark", -2.9, -2.0, -0.45, 0.45, cz, cz),
        ]
        shower = rect("air shower", "cabinet", -2.0, 0.0, -0.6, 0.6, cz, cz + 2.5,
                      doors=[door("w", 0.0, 0.9, 2.0, "interlock"), door("e", 0.0, 0.9, 2.0, "interlock")])
        car = {"x": dx + 1.7, "y": park["y0"] + 2.4, "yaw": -math.pi / 2}
        self.car = car
        self.rooms_in = [lob, lift, bridge, corridor, gown, shower]
        self.R = {r["name"]: r for r in self.rooms_in}
        return self.rooms_in

    def way_in(self):
        s, cz = self.s, self.cz
        self.rooms_of_the_way_in()
        R, dx, oy = self.R, self.dx, self.oy
        lob, lift = R["lobby"], R["lift"]
        self.t = s["from"] + 15 + self.rng.randrange(90)
        south = -math.pi / 2
        # outside: he has just shut his car door and walks to the office
        self.begin_stage("outside")
        car = self.car
        self.pos = (dx, car["y"] - 2.2, 0.0)
        self.body = self.head = south
        self.outfit = [{"s": 0.0, "wear": "street"}]
        i0 = len(self.samples)
        ty = self.ty
        tap = (dx, ty + 1.25)
        self.walk([self.pos[:2], tap], v0=0.6)
        self.mark("lobby", lambda x, y: y < oy, i0)
        reader = [f for f in lob["furniture"] if f["id"] == "badge reader"][0]
        rc = ((reader["x0"] + reader["x1"]) / 2, (reader["y0"] + reader["y1"]) / 2)
        self.hold(1.25, "interact", at="badge reader", head=math.atan2(rc[1] - tap[1], rc[0] - tap[0]), pitch=-0.5)
        self.captions.append({"s0": self.now - 1.25, "s1": self.now + 1.0, "text": "Badge in at the turnstile"})
        call = (dx, lob["y0"] + 1.1)
        self.walk([tap, call])
        panel = [f for f in lob["furniture"] if f["id"] == "lift panel"][0]
        pc = ((panel["x0"] + panel["x1"]) / 2, (panel["y0"] + panel["y1"]) / 2)
        self.hold(1.0, "interact", at="lift panel", head=math.atan2(pc[1] - call[1], pc[0] - call[0]), pitch=-0.2)
        self.hold(0.5, "stand", head=south)  # the doors open
        i1 = len(self.samples)
        ride = (dx, lift["y0"] + 1.3)
        self.walk([call, ride])
        self.mark("lift", lambda x, y: y < lob["y0"], i1)
        self.turn(math.pi / 2)  # he turns to face the doors
        self.hold(1.5, "lift", head=math.pi / 2)
        # the bridge: a cut takes him up and across
        self.begin_stage("bridge")
        br = R["bridge"]
        bx = (br["x0"] + br["x1"]) / 2
        self.jump(bx, 77.0, cz, south)
        self.walk([(bx, 77.0), (bx, 71.8)], v0=V, v1=V)
        # the gowning room: a cut, he has just come through its door
        self.begin_stage("gowning")
        g = R["gowning"]
        bench = [f for f in g["furniture"] if f["id"] == "bench"][0]
        self.jump(bx, g["y1"] - 0.6, cz, south)
        sit = (bx, bench["y1"] + 0.4)
        self.walk([self.pos[:2], sit], v0=0.9)
        self.turn(math.pi / 2)  # his back to the bench, to sit
        self.hold(1.0, "sit_enter", at="bench", head=math.pi / 2)
        self.hold(1.75, "sit_idle", at="bench", head=math.pi / 2 - 0.3, pitch=-0.6)
        # the time-lapse: booties over the line, coverall, hood, mask, gloves, glasses; he ends at the mirror
        mirror = [f for f in g["furniture"] if f["id"] == "mirror"][0]
        mc = ((mirror["x0"] + mirror["x1"]) / 2, (mirror["y0"] + mirror["y1"]) / 2)
        at_mirror = (mc[0], mirror["y1"] + 0.95)
        self.jump(at_mirror[0], at_mirror[1], cz, -math.pi / 2)
        self.lapse = self.now
        self.outfit.append({"s": self.now, "wear": "suit"})
        self.captions.append({"s0": self.now, "s1": self.now + 4.0,
                              "text": "Gowning: booties, coverall, hood, mask, gloves and glasses. Several minutes, shortened here."})
        self.hold(1.5, "mirror", at="mirror", head=-math.pi / 2, pitch=-0.1)
        sh = R["air shower"]
        inside_sh = (sh["x1"] - 0.7, 0.0)
        i2 = len(self.samples)
        self.walk([at_mirror, (sh["x0"] - 0.9, 0.0), inside_sh])
        self.mark("air shower", lambda x, y: x > sh["x0"], i2)
        self.hold(2.75, "shower", head=0.0, pitch=0.25)
        self.captions.append({"s0": self.now - 2.75, "s1": self.now, "text": "Air shower, shortened"})
        # the far door opens: he walks out onto the clean floor without stopping, on to where the run sends him
        i3 = len(self.samples)
        out_door = (sh["x1"] + 0.6, 0.0)
        self.walk([inside_sh, out_door], v1=V_EXIT)
        self.v_carry = V_EXIT
        self.mark("clean floor", lambda x, y: x > sh["x1"], i3)
        self.entry = (2.4, 0.0)
        self.start_floor = out_door
        self.reveal = (self.floor_mark(), self.floor_mark() + 3.5)
        self.captions.append({"s0": self.floor_mark(), "s1": self.floor_mark() + 4.0,
                              "text": "The clean floor: a gigafab-style layout of our own design from the SMT2020 testbed"})

    # the clean floor

    def wide_cam(self, view, look, fallback_x=None):
        fl, cz = self.fl, self.cz
        z = cz + 3.6
        cands = []
        for bi, (ax, hw, sg) in fl.aisle.items():
            if abs(ax - view[0]) < 1e-6:
                b = self.s["bays"][bi]
                if b["x0"] <= view[0] <= b["x1"] and min(b["y0"], b["y1"]) <= view[1] <= max(b["y0"], b["y1"]):
                    lo, hi = sg * (fl.sp / 2 + 0.6), sg * (fl.sp / 2 + fl.depth - 1.0)
                    lo, hi = min(lo, hi), max(lo, hi)
                    for d in (10, -10, 12, -12, 8, -8, 13.5, -13.5):
                        y = view[1] + d
                        if lo <= y <= hi:
                            cands.append((ax, y, z))
        if not cands:
            for dx in (-11, 11, -13, 13, -9, 9):
                x = view[0] + dx
                if fl.clear_of_stockers(x, 1.5):
                    cands.append((x, -base.LANE - 0.4, z))
        return cands

    def candidates(self, src, dist, prev, cap=None):
        s, run, fl = self.s, self.run, self.fl
        t0 = self.t
        used = {x["key"] for x in self.sights}
        kinds = [x["kind"] for x in self.sights]
        groups = {x["group"] for x in self.sights if x["group"] is not None}
        places = {x["place"] for x in self.sights}
        out = []
        routes = {}

        cap = MAX_WALK if cap is None else cap

        def walk_of(view):
            k = (round(view[0], 4), round(view[1], 4))
            if k not in dist or dist[k] / V > cap:
                return None
            if k not in routes:
                pts = fl.route(prev, src, k) if k != src else [src, src]
                routes[k] = (pts, self.walk_offset + walk_time(pts, self.body, self.v_carry) if k != src else 0.0)
            w = routes[k][1]
            return w if w <= cap else None

        def add(kind, key, group, tool, view, look, sev, numbers, walk, t_arr):
            if key in used:
                return
            watch = WATCH_BIG if kind == "breakdown" else WATCH
            if self.now + walk + watch + CLOSE > MAX_FILM:
                return
            if t_arr + watch * RATE["watch"] / 60 + CLOSE * RATE["watch"] / 60 > s["to"]:
                return
            want = math.atan2(look[1] - view[1], look[0] - view[0])
            k = (round(view[0], 4), round(view[1], 4))
            if k == src:
                return
            arrive_heading = Line(routes[k][0]).last_heading()
            if abs(wrap(arrive_heading - want)) < math.radians(35):
                return
            cam = self.watch_cam(view, look, hoist=kind == "hoist")
            if cam is None:
                return
            place = f"bay:{fl.tools[tool]['bay']}" if tool is not None else f"spine:{numbers['phase']}:{round(view[0] / 20)}"
            nov = (1.0 / (1 + kinds.count(kind))) * (0.3 if group is not None and group in groups else 1.0) \
                * (0.5 if place in places else 1.0)
            out.append({"kind": kind, "key": key, "group": group, "tool": tool, "place": place,
                        "view": list(view), "look": list(look), "walk_s": walk, "t_arrive": t_arr,
                        "severity": sev, "novelty": nov, "score": sev * nov / (1 + walk / WALK_SCALE),
                        "numbers": numbers, "cam": cam, "route": routes[k][0]})

        def per_tool(i, t_arr):
            g = fl.tools[i]["g"]
            mine = fl.by_group[g]
            up = sum(1 for j in mine if run.state(j, t_arr) in (0, 1))
            return g, len(mine), up

        for i in range(len(fl.tools)):
            view, look = fl.tool_view(i)
            w = walk_of(view)
            if w is None:
                continue
            t_arr = t0 + (w - self.walk_offset) * RATE["walk"] / 60
            st = run.state(i, t_arr)
            if st not in (2, 3):
                continue
            g, n, up = per_tool(i, t_arr)
            wt = run.waiting(g, t_arr)
            since, until = run.interval(i, t_arr)
            nums = {"waiting": wt, "since": since, "until": until, "tools": n, "up": up}
            if st == 3:
                add("breakdown", f"breakdown:{i}:{since}", g, i, view, look, 3 + wt / 10, nums, w, t_arr)
            else:
                add("maintenance", f"maintenance:{i}:{since}", g, i, view, look, 1.5 + wt / 10, nums, w, t_arr)
        best = {}
        for i, t in enumerate(fl.tools):
            view, look = fl.tool_view(i)
            w = walk_of(view)
            if w is None:
                continue
            if t["g"] not in best or (w, i) < best[t["g"]][:2]:
                best[t["g"]] = (w, i, view, look)
        for g, (w, i, view, look) in sorted(best.items()):
            t_arr = t0 + (w - self.walk_offset) * RATE["walk"] / 60
            wt = run.waiting(g, t_arr)
            _, n, up = per_tool(i, t_arr)
            if wt >= 10:
                add("queue", f"queue:{g}", g, i, view, look, wt / 10,
                    {"waiting": wt, "tools": n, "up": up, "bottleneck": g == self.bottleneck}, w, t_arr)
            hot = run.hot_waiting(g, t_arr)
            if hot:
                add("hot", f"hot:{hot[0]}:{g}", g, i, view, look, 2 + wt / 20,
                    {"waiting": wt, "lot": hot[0], "tools": n, "up": up}, w, t_arr)
        rail_y = max(r[0][1] for r in s["rails"] if r[0][1] == r[1][1] and r[0][0] != r[1][0] and abs(r[0][1]) < fl.sp / 2)
        for ph, x in self.hoist:
            view = (x, -base.LANE)
            w = walk_of(view)
            if w is None:
                continue
            t_arr = t0 + (w - self.walk_offset) * RATE["walk"] / 60
            look = (x + 2.5, rail_y, s["ride_z"])
            r = run.riding(look[0], t_arr)
            if r >= 3:
                add("hoist", f"hoist:{ph}:{round(x)}", None, None, view, look, r / 5, {"riding": r, "phase": ph}, w, t_arr)
        out.sort(key=lambda c: (-c["score"], c["key"]))
        return out

    def go(self, c):
        """Turn, walk to the sight (eyes first), stop, turn to it and watch."""
        want = math.atan2(c["look"][1] - c["view"][1], c["look"][0] - c["view"][0])
        eye = (c["view"][0], c["view"][1], self.cz + EYE)
        pitch = math.atan2(c["look"][2] - eye[2], math.dist(eye[:2], c["look"][:2]))
        start = self.now - self.walk_offset
        walk = c["walk_s"]
        self.walk(c["route"], v0=self.v_carry, head=want, head_at=self.look_from(c, want, start + walk), pitch=pitch)
        self.walk_offset = 0.0
        self.v_carry = 0.0
        arrive = self.now
        if abs(arrive - start - walk) > 1e-6:
            raise SystemExit(f"walk timing {arrive - start:.3f} != {walk:.3f} for {c['key']}")
        self.pos = (c["view"][0], c["view"][1], self.cz)
        watch = WATCH_BIG if c["kind"] == "breakdown" else WATCH
        n0 = len(self.samples)
        self.turn(want, rate="watch", head=want, pitch=pitch)
        used = (len(self.samples) - n0) * DT
        self.hold(watch - used, "watch", head=want, pitch=pitch, rate="watch")
        c["arrive_s"], c["leave_s"] = arrive, self.now
        return c

    def look_from(self, c, want, arrive):
        """When his eyes go to the sight: BEFORE seconds out, or up to LOOK_AHEAD out if from then on
        the sight stays within an easy head turn of where his body points."""
        trial = self.clone()
        n0 = len(trial.samples)
        trial.walk(c["route"], v0=self.v_carry)
        bodies = [(p[0], p[4]) for p in trial.samples[n0:]]
        at = arrive - BEFORE
        for s_, b in reversed(bodies):
            if s_ < arrive - LOOK_AHEAD or s_ >= at:
                if s_ < arrive - LOOK_AHEAD:
                    break
                continue
            if abs(wrap(want - b)) > EASY_LOOK:
                break
            at = s_
        return at

    def plan(self):
        s, run, fl = self.s, self.run, self.fl
        ts = [s["from"] + (s["to"] - s["from"]) * i / 12 for i in range(13)]
        groups = sorted({t["g"] for t in fl.tools})
        self.bottleneck = max(groups, key=lambda g: (sum(run.waiting(g, t) for t in ts), -g))
        self.way_in()
        self.hoist = self.hoist_xs()
        fl.build(self.entry, self.hoist)
        fl.edge(fl.key(*self.start_floor), fl.key(*self.entry))
        fl.rooms_in = self.rooms_in
        self.walk_offset = self.now - self.floor_mark()
        self._reach = {}
        while len(self.sights) < MAX_SIGHTS:
            src = (round(self.pos[0], 4), round(self.pos[1], 4))
            dist, prev = fl.dijkstra(src)
            every = self.candidates(src, dist, prev)
            need = MIN_SIGHTS - len(self.sights) - 1
            if need >= 0:
                ok = [c for c in every[:BRANCH] if self.can_reach(c, need)]
                # the options he weighs: those that still leave room for the tour, and any weaker ones
                cands = ok + [c for c in every if c not in ok and ok and c["score"] <= ok[0]["score"]] if ok else every
                if len(cands) < 2:
                    cands = every
            else:
                cands = every
            if not cands:
                break
            c = cands[0]
            c["candidates"] = [{k: o[k] for k in ("key", "kind", "severity", "novelty", "walk_s", "score")} for o in cands[:12]]
            self.go(c)
            self.sights.append(c)
        self.close_s = self.now
        self.hold(CLOSE, "close", rate="watch")
        self.acts[-1]["s1"] = self.now
        last = self.samples[-1]
        self.samples.append([self.now] + last[1:])
        self.meta.append(dict(self.meta[-1]))
        self.knots.append([self.now, self.t])
        self.stages_from_marks()
        self.camera()
        self.check()
        return self.out()

    def clone(self):
        """A copy to try a sight on; the plant, the run and the floor are shared."""
        keep = (self.s, self.run, self.fl, self._wc)
        return copy.deepcopy(self, {id(o): o for o in keep})

    def nexts(self):
        src = (round(self.pos[0], 4), round(self.pos[1], 4))
        dist, prev = self.fl.dijkstra(src)
        return self.candidates(src, dist, prev)

    def can_reach(self, c, need):
        """Going to c, can the tour still show `need` more sights after it? Tried on a copy, the walks
        timed exactly, the best few next sights at each step."""
        if need <= 0:
            return len({x["kind"] for x in self.sights + [c]}) >= MIN_KINDS
        key = (len(self.sights), c["key"], need)
        if key in self._reach:
            return self._reach[key]
        trial = self.clone()
        trial._reach = {}
        trial.go(dict(c))
        trial.sights.append(c)
        ok = any(trial.can_reach(o, need - 1) for o in trial.nexts()[:BRANCH])
        self._reach[key] = ok
        return ok

    def floor_mark(self):
        return [s0 for name, s0 in self.marks if name == "clean floor"][0]

    def stages_from_marks(self):
        names = ["outside", "lobby", "lift", "bridge", "gowning", "air shower", "clean floor"]
        starts = {"outside": 0.0}
        for st in self.stages:
            starts.setdefault(st["name"], st["s0"])
        for name, s0 in self.marks:
            starts[name] = s0
        end = self.samples[-1][0]
        self.stages = []
        for a, b in zip(names, names[1:] + [None]):
            self.stages.append({"name": a, "s0": starts[a], "s1": starts[b] if b else end})
        self.floor_start = starts["clean floor"]

    # the camera

    def stage_at(self, s):
        for st in self.stages:
            if st["s0"] <= s < st["s1"]:
                return st["name"]
        return self.stages[-1]["name"]

    def me(self, i):
        p = self.samples[i]
        return (p[1], p[2], p[3] + 1.2)

    def frame(self, cam, look, me, limit=IN_FRAME):
        """Pull the look toward him until he is within the limit of the middle of the frame."""
        for k in range(11):
            u = 1.0 - k / 10
            lk = tuple(me[j] + (look[j] - me[j]) * u for j in range(3))
            v = [lk[j] - cam[j] for j in range(3)]
            if sum(c * c for c in v) < 1e-9:
                continue
            if ang3(v, [me[j] - cam[j] for j in range(3)]) <= limit:
                return lk
        return tuple(me)

    def cam_valid(self, i, cam):
        fl, cz = self.fl, self.cz
        p = self.samples[i]
        me = self.me(i)
        d = math.dist(cam, me)
        if not 1.45 <= d <= 15.5:
            return False
        st = self.stage_at(p[0])
        if st == "clean floor":
            if fl.hits_tool(cam[0], cam[1], cam[2], 0.3):
                return False
            if not (cz + 0.5 <= cam[2] <= fl.ceil - 0.3) or not fl.in_hall(*cam):
                return False
        return True

    def follow_target(self, i, back=2.6):
        """Behind him along the way he has walked, a little to his right, at his shoulder."""
        p = self.samples[i]
        acc, pos, hb = 0.0, None, None
        j = i
        lo = i
        while lo > 0 and self.samples[lo][0] not in self.cuts and self.samples[lo - 1][3] == p[3]:
            lo -= 1
        while j > lo:
            a, b = self.samples[j - 1], self.samples[j]
            dd = math.hypot(b[1] - a[1], b[2] - a[2])
            if dd > 1e-9:
                if acc + dd >= back:
                    u = (back - acc) / dd
                    pos = (b[1] + (a[1] - b[1]) * u, b[2] + (a[2] - b[2]) * u)
                    hb = math.atan2(b[2] - a[2], b[1] - a[1])
                    break
                acc += dd
            j -= 1
        if pos is None:
            h0 = self.samples[lo][4]
            rest = back - acc
            f = self.samples[lo]
            pos = (f[1] - rest * math.cos(h0), f[2] - rest * math.sin(h0))
        dx, dy = p[1] - pos[0], p[2] - pos[1]
        dd = math.hypot(dx, dy)
        f = (dx / dd, dy / dd) if dd > 1e-6 else (math.cos(p[4]), math.sin(p[4]))
        right = (f[1], -f[0])
        cam = (pos[0] + 0.5 * right[0], pos[1] + 0.5 * right[1], p[3] + 1.7)
        look = (p[1] + 6 * f[0], p[2] + 6 * f[1], p[3] + 1.25)
        return cam, look

    def camera(self):
        """Pick a target for every sample, then glide within a shoulder run and cut between shots."""
        cz = self.cz
        R = self.R
        dx, oy = self.dx, self.oy
        lob, lift, g = R["lobby"], R["lift"], R["gowning"]
        fixed = {
            "outside": ((dx + 2.9, oy + 2.0, 1.65), "wide"),
            "lobby": ((lob["x1"] - 4.0, lob["y0"] + 3.0, 1.75), "fixed"),
            "lift": ((dx + 0.95, lift["y1"] - 0.25, 2.75), "fixed"),
            "gowning a": ((g["x1"] - 0.6, g["y1"] - 1.1, cz + 1.9), "fixed"),
            "gowning b": ((g["x1"] - 0.5, 3.4, cz + 1.9), "fixed"),
            "reveal": ((1.2, 2.2, cz + 2.2), "shoulder"),
        }
        sights = self.sights
        by_key = {c["key"]: c for c in sights}
        wides = [(c["arrive_s"] - 0.5, c["arrive_s"] + 3.0, c) for c in sights if c["kind"] == "breakdown"]
        want = []  # (cam, look, mode, source)
        wide_pick = {}
        for i, p in enumerate(self.samples):
            s = p[0]
            st = self.stage_at(s)
            me = self.me(i)
            here = (p[1], p[2], p[3] + 1.0)
            if st in ("outside", "lobby", "lift"):
                cam, mode = fixed[st]
                want.append((cam, here, mode, st))
                continue
            if st == "bridge":
                cam, look = self.follow_target(i)
                want.append((cam, look, "shoulder", "bridge"))
                continue
            if st in ("gowning", "air shower"):
                key = "gowning a" if s < self.lapse else "gowning b"
                cam, mode = fixed[key]
                want.append((cam, here, mode, key))
                continue
            if self.reveal[0] <= s < self.reveal[1]:
                cam, mode = fixed["reveal"]
                want.append((cam, (p[1] + 8.0, p[2], p[3] + 1.5), mode, "reveal"))
                continue
            w = [x for x in wides if x[0] <= s < x[1]]
            if w:
                c = w[0][2]
                look = tuple(me[k] + (c["look"][k] - me[k]) * 0.5 for k in range(3))
                cam = wide_pick.get(c["key"])
                if cam is None or not self.cam_valid(i, cam):
                    cam = None
                    for cc in self.wide_cam(c["view"], c["look"]):
                        if not self.cam_valid(i, cc):
                            continue
                        lk = self.frame(cc, look, me)
                        v = [lk[k] - cc[k] for k in range(3)]
                        if ang3(v, [c["look"][k] - cc[k] for k in range(3)]) <= IN_FRAME:
                            cam = cc
                            break
                    wide_pick[c["key"]] = cam
                if cam is not None:
                    want.append((cam, look, "wide", ("wide", c["key"])))
                    continue
            if s >= self.close_s and sights:
                c = sights[-1]
                cam = wide_pick.get("close")
                if cam is None or not self.cam_valid(i, cam):
                    cam = next((cc for cc in self.wide_cam(c["view"], c["look"]) if self.cam_valid(i, cc)), None)
                    wide_pick["close"] = cam
                if cam is not None:
                    want.append((cam, me, "wide", ("close",)))
                    continue
            held = [c for c in sights if c["arrive_s"] - 1.0 <= s <= c["leave_s"]]
            if held:
                cam, look = held[-1]["cam"]
                want.append((cam, look, "shoulder", ("watch", held[-1]["key"])))
            else:
                cam, look = self.follow_target(i)
                want.append((cam, look, "shoulder", "follow"))
        alpha = 1 - math.exp(-DT / CAM_TAU)
        out = []
        cuts = set(self.cuts)
        for i, (cam, look, mode, src) in enumerate(want):
            s = self.samples[i][0]
            me = self.me(i)
            prev = out[-1] if out else None
            psrc = want[i - 1][3] if i else None
            glide = (prev is not None and mode == "shoulder" and prev[6] == "shoulder" and s not in cuts
                     and src != "reveal" and not (isinstance(src, tuple) and src[0] in ("wide", "close")))
            if glide:
                pc = prev[:3]
                step = [(cam[k] - pc[k]) * alpha for k in range(3)]
                n = math.sqrt(sum(c * c for c in step))
                if n > CAM_STEP:
                    step = [c * CAM_STEP / n for c in step]
                moved = tuple(pc[k] + step[k] for k in range(3))
                if isinstance(src, tuple) and src[0] == "watch" and s >= by_key[src[1]]["arrive_s"] + 1.2 \
                        and math.dist(moved, cam) <= CAM_STEP:
                    moved = tuple(cam)  # settled on the watching camera
                plk = prev[3:6]
                lk = tuple(plk[k] + (look[k] - plk[k]) * min(1.0, 2 * alpha) for k in range(3))
                if self.cam_valid(i, moved):
                    cam, look = moved, lk
                elif self.cam_valid(i, cam):
                    cuts.add(s)
                else:
                    alt = self.rescue(i)
                    if alt is not None:
                        cam, look = alt
                        cuts.add(s)
                    else:
                        cam, look = tuple(prev[:3]), lk
            elif prev is not None and src != psrc:
                cuts.add(s)
            out.append(list(cam) + list(self.frame(cam, look, me)) + [mode])
        self.camera_cuts = sorted(round(c, 6) for c in cuts)
        self.cam = [[self.samples[i][0]] + [round(v, 4) for v in c[:6]] + [c[6]] for i, c in enumerate(out)]

    def rescue(self, i):
        """Another shoulder camera when the planned one cannot be used."""
        for back in (3.2, 2.0, 3.8, 1.6, 4.5):
            cam, look = self.follow_target(i, back)
            if self.cam_valid(i, cam):
                return cam, look
        return None

    def check(self):
        for i, c in enumerate(self.cam):
            p = self.samples[i]
            me = self.me(i)
            v = [c[4] - c[1], c[5] - c[2], c[6] - c[3]]
            if ang3(v, [me[k] - c[1 + k] for k in range(3)]) > 22:
                raise SystemExit(f"he is out of frame at {c[0]:.3f} s")

    def out(self):
        r4 = lambda v: round(v, 4)
        sights = []
        for c in self.sights:
            sights.append({k: c[k] for k in ("kind", "key", "group", "tool", "place", "view", "look", "walk_s", "t_arrive",
                                             "severity", "novelty", "score", "numbers", "arrive_s", "leave_s", "candidates")})
        rooms = self.rooms_in + self.fl.rooms
        return {
            "what": "A Walk Through the Fab, the Blender film: the visitor's route, gait, gaze, acts and camera, chosen by the run",
            "badge": BADGE,
            "model": self.s.get("model"),
            "seed": self.seed,
            "fps": FPS,
            "dt": DT,
            "speed": V,
            "eye": EYE,
            "fov_v": FOV_V,
            "clock_rate": RATE,
            "gait_per_radian": STEP,
            "score": "severity x novelty / (1 + walk_s / 15); novelty 1/(1 + same kind seen) x 0.3 if the group "
                     "was seen x 0.5 if the place was seen; walk_s is the walk he makes",
            "entry": list(self.entry),
            "car": {k: r4(v) for k, v in self.car.items()},
            "outfit": self.outfit,
            "rooms": [{k: (r4(v) if isinstance(v, float) else v) for k, v in r.items()} for r in rooms],
            "stages": self.stages,
            "cuts": sorted(round(c, 6) for c in self.cuts),
            "camera_cuts": self.camera_cuts,
            "clock": self.knots,
            "path": [[p[0]] + [round(v, 6) for v in p[1:]] for p in self.samples],
            "acts": self.acts,
            "camera": self.cam,
            "sights": sights,
            "cards": [self.card(c) for c in self.sights],
            "captions": self.captions,
        }


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    seed = 7
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])
        args = [a for a in args if a != str(seed)]
    scene, trace, out = (Path(a) for a in args[:3])
    s = json.loads(scene.read_text())
    tr = json.loads(trace.read_text())
    plan = FilmPlanner(s, tr, seed).plan()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, separators=(",", ":")))
    print(f"{len(plan['sights'])} sights, {plan['path'][-1][0]:.1f} s, way in {plan['stages'][-1]['s0']:.1f} s:",
          ", ".join(x["key"] for x in plan["sights"]))


if __name__ == "__main__":
    main(sys.argv[1:])
