"""A Walk Through the Fab: where the visitor goes, where he looks, and how the camera sees him.

A gigafab-style layout of our own design on the SMT2020 model; not a real fab. A visitor parks,
walks to the office door, takes the lift, crosses the link bridge, gowns up, goes through the air
shower and steps onto the clean floor. From there the run decides where he goes. At each choice
every sight he could reach is scored:

    score = severity x novelty / (1 + walk seconds / 15)

    severity   a tool down 3, in maintenance 1.5, a queue 0, a hot lot waiting 2, each plus the
               lots waiting for that group (/10, or /20 for a hot lot); the hoist: lots moving
               on the rail overhead within 15 m, /5
    novelty    1 / (1 + sights of the same kind already seen), times 0.3 if he has seen the group
               and 0.5 if he has already stood in that bay (or that stretch of the spine)

He walks to the best one at 1.3 m/s along the spine and the bay aisles (never through a tool),
turns his head before his body, and watches for 6 seconds (8 for a tool down). The fab clock
runs at 60 fab seconds a second while he walks and 10 while he watches. The camera looks over
his shoulder and cuts wide when he steps onto the floor, when a tool is down and at the end.

The visitor, the rooms of the way in and the walkway between the phases are drawn only: they are
not in the model and no number comes from them. Every number on a card is the run's. Standard
library only; the same seed gives the same plan.

    python3 viz/visitor/plan.py SCENE TRACE OUT [--seed N]
"""

import heapq
import json
import math
import random
import sys
from bisect import bisect_right
from pathlib import Path

FPS = 24
DT = 0.125  # film seconds between samples
SPEED = 1.3  # m/s
EYE = 1.6  # eye above the feet
RATE = {"walk": 60, "watch": 10}  # fab seconds per film second
TURN = 0.625  # standing turn before each walk
WATCH, WATCH_BIG = 6.0, 8.0
LANE = 2.6  # walking lanes either side of the stockers on the spine
FILLET = 0.8  # corner radius
BEFORE = 1.5  # the head goes to the sight this long before he arrives
MAX_SIGHTS = 7
MAX_FILM = 236.0
MAX_WALK = 45.0
WALK_SCALE = 15.0  # seconds of walking that halve a sight's score
CLOSE = 6.0
WIDE_Z = 4.5
FOV_V = 42.0
IN_FRAME = 18.0  # degrees from the view's centre, kept under the tests' 20
BADGE = ("A gigafab-style layout of our own design on the SMT2020 model, not a real fab. "
         "The visitor is drawn only; he is not in the model. Every number is the run's.")


def q(x):
    """Round film seconds up to the sample grid."""
    return math.ceil(x / DT - 1e-9) * DT


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def toward(a, b, step):
    d = wrap(b - a)
    return wrap(a + max(-step, min(step, d)))


def smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def ang3(u, v):
    nu = math.sqrt(sum(c * c for c in u))
    nv = math.sqrt(sum(c * c for c in v))
    c = sum(p * r for p, r in zip(u, v)) / (nu * nv)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def inside(box, x, y, pad=0.0):
    return box["x0"] - pad < x < box["x1"] + pad and box["y0"] - pad < y < box["y1"] + pad


def fmt(t):
    d, m = divmod(t, 1440)
    return f"day {int(d)}, {int(m // 60):02d}:{int(m % 60):02d}"


# ---------------------------------------------------------------- the run


class Run:
    def __init__(self, s, tr):
        self.s = s
        self.states = {}
        for t, i, code in s["states"]:
            self.states.setdefault(i, []).append((t, code))
        self.times = {i: [c[0] for c in ch] for i, ch in self.states.items()}
        self.steps = {}
        for L in tr["lots"]:
            for a, st, e, tool, g in L["steps"]:
                self.steps.setdefault(g, []).append((a, st, L["id"], L["hot"]))
        self.ride_z = s["ride_z"]

    def state(self, tool, t):
        k = bisect_right(self.times.get(tool, []), t)
        return self.states[tool][k - 1][1] if k else 1

    def interval(self, tool, t):
        """The start of the state the tool is in at t, and when it next changes."""
        ts = self.times.get(tool, [])
        k = bisect_right(ts, t)
        since = ts[k - 1] if k else None
        until = ts[k] if k < len(ts) else None
        return since, until

    def waiting(self, g, t):
        return sum(1 for a, st, _, _ in self.steps.get(g, []) if a <= t < st)

    def hot_waiting(self, g, t):
        return sorted(lid for a, st, lid, hot in self.steps.get(g, []) if hot and a <= t < st)

    def riding(self, x, t):
        n = 0
        for L in self.s["lots"]:
            k = L["k"]
            if not (k[0][0] <= t <= k[-1][0]):
                continue
            for a, b in zip(k, k[1:]):
                if a[0] <= t <= b[0]:
                    u = 0.0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
                    p = [a[i] + (b[i] - a[i]) * u for i in (1, 2, 3)]
                    if a[1:4] != b[1:4] and p[2] >= self.ride_z - 0.01 and abs(p[0] - x) <= 15.0:
                        n += 1
                    break
        return n


# ---------------------------------------------------------------- the floor


class Floor:
    def __init__(self, s):
        self.s = s
        self.cz = s["clean_z"]
        cr = [f for f in s["floors"] if f["name"] == "cleanroom"][0]
        self.ceil = self.cz + cr["z1"] - cr["z0"]
        self.sp, self.depth = s["spine"], s["depth"]
        self.tools, self.stockers = s["tools"], s["stockers"]
        self.adj = {}
        self.pt = {}
        self.rooms, self.rooms_in = [], []
        self.grid = {}
        for box in list(self.tools) + list(self.stockers):
            for gx in range(int((box["x0"] - 1) // 8), int((box["x1"] + 1) // 8) + 1):
                for gy in range(int((box["y0"] - 1) // 8), int((box["y1"] + 1) // 8) + 1):
                    self.grid.setdefault((gx, gy), []).append(box)
        self.by_group = {}
        for i, t in enumerate(self.tools):
            self.by_group.setdefault(t["g"], []).append(i)
        self.aisle = {}  # bay -> (x, half width, sign)
        for bi, b in enumerate(s["bays"]):
            ts = [t for t in self.tools if t["bay"] == bi]
            mid = sum(b["rails_x"]) / 2
            west = [t["x1"] for t in ts if (t["x0"] + t["x1"]) / 2 < mid]
            east = [t["x0"] for t in ts if (t["x0"] + t["x1"]) / 2 >= mid]
            w = max(west) if west else mid - 1.75
            e = min(east) if east else mid + 1.75
            sg = 1 if b["side"] == 0 else -1
            self.aisle[bi] = ((w + e) / 2, (e - w) / 2, sg)

    def key(self, x, y):
        k = (round(x, 4), round(y, 4))
        self.pt[k] = (x, y)
        self.adj.setdefault(k, [])
        return k

    def edge(self, a, b):
        if a == b:
            return
        d = math.dist(self.pt[a], self.pt[b])
        self.adj[a].append((b, d))
        self.adj[b].append((a, d))

    def chain(self, keys, axis):
        keys = sorted(set(keys), key=lambda k: self.pt[k][axis])
        for a, b in zip(keys, keys[1:]):
            self.edge(a, b)

    def clear_of_stockers(self, x, pad):
        return all(not (st["x0"] - pad < x < st["x1"] + pad) for st in self.stockers)

    def build(self, entry, hoist_xs):
        s = self.s
        lanes = {}  # (phase, sign) -> keys
        for bi, b in enumerate(s["bays"]):
            ax, hw, sg = self.aisle[bi]
            ks = [self.key(ax, sg * LANE)]
            for ti, t in enumerate(self.tools):
                if t["bay"] == bi:
                    ks.append(self.key(ax, (t["y0"] + t["y1"]) / 2))
            self.chain(ks, 1)
            lanes.setdefault((b["phase"], sg), []).append(ks[0])
            if self.clear_of_stockers(ax, 1.2):
                lanes.setdefault((b["phase"], -sg), []).append(self.key(ax, -sg * LANE))
                self.edge(self.key(ax, LANE), self.key(ax, -LANE))
        for ph, x in hoist_xs:
            lanes.setdefault((ph, -1), []).append(self.key(x, -LANE))
        e = self.key(*entry)
        for sg in (1, -1):
            k = self.key(entry[0] + 1.2, sg * LANE)
            lanes.setdefault((0, sg), []).append(k)
            self.edge(e, k)
        # the walkway between the phases, beside the hoist bridge (drawn only)
        fabs = [c for c in s["campus"] if c["kind"] == "fab"]
        bridge = [c for c in s["campus"] if c["kind"] == "bridge"]
        self.rooms = []
        for ph in range(len(s["offsets"]) - 1):
            ox, L = s["offsets"][ph], s["lengths"][ph]
            nx = s["offsets"][ph + 1]
            f1, f2 = fabs[ph], fabs[ph + 1]
            wy = (bridge[0]["y1"] if bridge else 6.0) + 2.0
            e1, e2 = (ox + L + f1["x1"]) / 2, (f2["x0"] + nx) / 2
            a = self.key(e1, LANE)
            b_ = self.key(e1, wy)
            c = self.key(e2, wy)
            d = self.key(e2, LANE)
            lanes.setdefault((ph, 1), []).append(a)
            lanes.setdefault((ph + 1, 1), []).append(d)
            for u, v in ((a, b_), (b_, c), (c, d)):
                self.edge(u, v)
            top = self.cz + 3.2
            self.rooms += [
                {"name": f"phase {ph + 1} east end", "kind": "walkway", "x0": ox + L, "x1": f1["x1"],
                 "y0": LANE - 0.8, "y1": wy + 1.5, "z0": self.cz, "z1": self.ceil},
                {"name": "personnel bridge", "kind": "walkway", "x0": f1["x1"], "x1": f2["x0"],
                 "y0": wy - 1.5, "y1": wy + 1.5, "z0": self.cz, "z1": top},
                {"name": f"phase {ph + 2} west end", "kind": "walkway", "x0": f2["x0"], "x1": nx,
                 "y0": LANE - 0.8, "y1": wy + 1.5, "z0": self.cz, "z1": self.ceil},
            ]
        for ks in lanes.values():
            self.chain(ks, 0)

    def dijkstra(self, src):
        dist, prev = {src: 0.0}, {}
        h = [(0.0, src)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist[u]:
                continue
            for v, w in self.adj[u]:
                nd = d + w
                if nd < dist.get(v, 1e18) - 1e-9:
                    dist[v], prev[v] = nd, u
                    heapq.heappush(h, (nd, v))
        return dist, prev

    def route(self, prev, src, dst):
        out = [dst]
        while out[-1] != src:
            out.append(prev[out[-1]])
        return [self.pt[k] for k in reversed(out)]

    def tool_view(self, ti):
        t = self.tools[ti]
        ax, hw, sg = self.aisle[t["bay"]]
        cy = (t["y0"] + t["y1"]) / 2
        fx = t["x1"] if (t["x0"] + t["x1"]) / 2 < ax else t["x0"]
        return (ax, cy), (fx, cy, self.cz + 1.2)

    def hits_tool(self, x, y, z, pad):
        for box in self.grid.get((int(x // 8), int(y // 8)), ()):
            if "h" in box and "kind" in box:  # a tool: only below its top
                if z < self.cz + box["h"] + 0.3 and inside(box, x, y, pad):
                    return True
            elif inside(box, x, y, pad):
                return True
        return False

    def in_hall(self, x, y, z):
        s = self.s
        if not (self.cz + 0.5 <= z <= self.ceil - 0.3):
            return False
        if any(ox < x < ox + L and abs(y) < self.sp / 2 + self.depth for ox, L in zip(s["offsets"], s["lengths"])):
            return True
        return any(r["x0"] <= x <= r["x1"] and r["y0"] <= y <= r["y1"] and r["z0"] <= z <= r["z1"]
                   for r in self.rooms + self.rooms_in)


# ---------------------------------------------------------------- a walked path


class Line:
    """A polyline with rounded corners, walked at a constant speed."""

    def __init__(self, pts):
        clean = [pts[0]]
        for p in pts[1:]:
            if math.dist(p, clean[-1]) > 1e-6:
                clean.append(p)
        pts = clean
        # drop points on a straight line
        keep = [pts[0]]
        for i in range(1, len(pts) - 1):
            a, b, c = keep[-1], pts[i], pts[i + 1]
            cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cr) > 1e-9:
                keep.append(b)
        if len(pts) > 1:
            keep.append(pts[-1])
        self.pts = keep
        self.prims = []  # ("l", p, q) or ("a", centre, r, a0, sweep)
        cur = keep[0]
        for i in range(1, len(keep) - 1):
            a, b, c = keep[i - 1], keep[i], keep[i + 1]
            h1 = math.atan2(b[1] - a[1], b[0] - a[0])
            h2 = math.atan2(c[1] - b[1], c[0] - b[0])
            th = wrap(h2 - h1)
            if abs(th) > math.radians(170):
                self.prims.append(("l", cur, b))
                cur = b
                continue
            l1, l2 = math.dist(a, b), math.dist(b, c)
            d = min(FILLET * math.tan(abs(th) / 2), 0.45 * l1, 0.45 * l2)
            r = d / math.tan(abs(th) / 2)
            p1 = (b[0] - d * math.cos(h1), b[1] - d * math.sin(h1))
            p2 = (b[0] + d * math.cos(h2), b[1] + d * math.sin(h2))
            sgn = 1 if th > 0 else -1
            cen = (p1[0] - sgn * r * math.sin(h1), p1[1] + sgn * r * math.cos(h1))
            a0 = math.atan2(p1[1] - cen[1], p1[0] - cen[0])
            self.prims.append(("l", cur, p1))
            self.prims.append(("a", cen, r, a0, th))
            cur = p2
        if len(keep) > 1:
            self.prims.append(("l", cur, keep[-1]))
        self.lens = []
        for p in self.prims:
            self.lens.append(math.dist(p[1], p[2]) if p[0] == "l" else abs(p[2] * p[4]))
        self.length = sum(self.lens)

    def at(self, l):
        """Position and heading at arc length l."""
        if not self.prims:
            return self.pts[0], None
        for p, n in zip(self.prims, self.lens):
            if l <= n + 1e-12 or p is self.prims[-1]:
                u = 0.0 if n == 0 else min(1.0, max(0.0, l / n))
                if p[0] == "l":
                    a, b = p[1], p[2]
                    h = math.atan2(b[1] - a[1], b[0] - a[0]) if n > 0 else None
                    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u), h
                cen, r, a0, sw = p[1], p[2], p[3], p[4]
                a = a0 + sw * u
                h = a + (math.pi / 2 if sw > 0 else -math.pi / 2)
                return (cen[0] + r * math.cos(a), cen[1] + r * math.sin(a)), wrap(h)
            l -= n
        return self.pts[-1], None

    def last_heading(self):
        a, b = self.pts[-2], self.pts[-1]
        return math.atan2(b[1] - a[1], b[0] - a[0])


# ---------------------------------------------------------------- the planner


class Planner:
    def __init__(self, s, tr, seed):
        self.s, self.run, self.seed = s, Run(s, tr), seed
        self.rng = random.Random(seed)
        self.fl = Floor(s)
        self.cz = self.fl.cz
        self.samples = []  # [s, x, y, z, body, head, pitch]
        self.meta = []  # per sample: dict(kind, stage, sight, look)
        self.knots = []
        self.stages = []
        self.cuts = []
        self.sights = []
        self.cards = []
        self.idx = 0  # samples emitted
        self.t = None
        self.body = self.head = -math.pi / 2
        self.pitch = 0.0
        self.pos = (0.0, 0.0, 0.0)
        self.stage = None
        self.outfit = []
        self._wc = {}

    # time and state

    @property
    def now(self):
        return self.idx * DT

    def knot(self, rate, dur):
        if not self.knots or self.knots[-1][0] < self.now:
            self.knots.append([self.now, self.t])
        self.t += dur * RATE[rate] / 60.0

    def begin_stage(self, name):
        if self.stages:
            self.stages[-1]["s1"] = self.now
        self.stages.append({"name": name, "s0": self.now, "s1": None})
        self.stage = name

    def emit(self, n, f, rate, kind, sight=None, look=None):
        """n samples; f(k) -> (x, y, z, body_target, head_target, pitch_target, body_rate, head_rate)."""
        self.knot(rate, n * DT)
        for k in range(n):
            x, y, z, bt, ht, pt, br, hr = f(k)
            if bt is not None:
                self.body = toward(self.body, bt, br * DT) if br else wrap(bt)
            if ht is not None:
                self.head = toward(self.head, ht, hr * DT)
            # the neck turns at most 100 degrees from the body
            rel = wrap(self.head - self.body)
            if abs(rel) > math.radians(100):
                self.head = wrap(self.body + math.copysign(math.radians(100), rel))
            if pt is not None:
                self.pitch += max(-2.0 * DT, min(2.0 * DT, pt - self.pitch))
            self.pos = (x, y, z)
            self.samples.append([self.now + k * DT, x, y, z, self.body, self.head, self.pitch])
            self.meta.append({"kind": kind, "stage": self.stage, "sight": sight, "look": look})
        self.idx += n

    def walk_line(self, line, dur, rate="walk", kind="walk", head_to=None, head_from=None, pitch_to=0.0):
        n = round(dur / DT)
        z = self.pos[2]

        def f(k):
            l = line.length * (k * DT) / dur if dur > 0 else 0
            (x, y), h = line.at(l)
            ht = h
            pt = 0.0
            if head_to is not None and k * DT >= head_from:
                ht, pt = head_to, pitch_to
            return x, y, z, h, ht, pt, 6.0, 3.5

        self.emit(n, f, rate, kind)
        end = line.at(line.length)[0]
        self.pos = (end[0], end[1], z)

    def stand(self, dur, body=None, head=None, pitch=0.0, rate="walk", kind="stand", sight=None, look=None, br=3.0):
        n = round(dur / DT)
        x, y, z = self.pos

        def f(k):
            if body is not None and k == 0:
                return x, y, z, None, head, pitch, br, 3.5
            return x, y, z, body, head, pitch, br, 3.5

        self.emit(n, f, rate, kind, sight, look)

    def straight(self, a, b, dur, kind="walk"):
        self.walk_line(Line([a, b]), dur, kind=kind)

    # the way in

    def way_in(self):
        """Car park, office door, lift, link bridge, gowning room, air shower, then the spine's west end."""
        s, fl = self.s, self.fl
        cz = self.cz
        office = [c for c in s["campus"] if c["kind"] == "office"][0]
        park = [c for c in s["campus"] if c["kind"] == "parking"][0]
        fab = [c for c in s["campus"] if c["kind"] == "fab"][0]
        ox = s["offsets"][0]
        bx = (fab["x0"] + ox) / 2  # the strip between the fab's west wall and the clean floor
        dx = office["x0"] + 6 + self.rng.choice((0.0, 2.6, 5.2))
        self.ax = bx
        lift_y0, lift_y1 = office["y0"] + 0.3, office["y0"] + 2.3
        gown_y1 = 8.0
        shower_x0 = ox - 1.6
        self.entry = (ox, 0.0)
        self.rooms_in = [
            {"name": "lobby", "kind": "room", "x0": bx - 1, "x1": office["x0"] + 14, "y0": lift_y1,
             "y1": office["y0"] + 16, "z0": 0.0, "z1": 4.5},
            {"name": "lift", "kind": "lift", "x0": bx - 1, "x1": bx + 1, "y0": lift_y0, "y1": lift_y1,
             "z0": 0.0, "z1": cz + 3.0},
            {"name": "link", "kind": "bridge", "x0": bx - 1.5, "x1": bx + 1.5, "y0": gown_y1, "y1": lift_y0,
             "z0": cz, "z1": cz + 3.5},
            {"name": "gowning", "kind": "room", "x0": fab["x0"], "x1": shower_x0, "y0": -3.0, "y1": gown_y1,
             "z0": cz, "z1": cz + 3.0},
            {"name": "air shower", "kind": "room", "x0": shower_x0, "x1": ox, "y0": -0.8, "y1": 0.8,
             "z0": cz, "z1": cz + 2.4},
        ]
        self.car = {"x": dx + 2.3, "y": park["y0"] + 3.2, "yaw": -math.pi / 2}
        self.t = s["from"] + 15 + self.rng.randrange(0, 90)
        south, east = -math.pi / 2, 0.0

        self.begin_stage("outside")
        self.outfit.append([self.now, "street"])
        self.pos = (dx, park["y0"] + 2.5, 0.0)
        self.stand(1.5, body=south, head=south)
        self.straight((dx, self.pos[1]), (dx, office["y1"]), q((self.pos[1] - office["y1"]) / SPEED))

        self.begin_stage("lobby")
        self.cuts.append(self.now)
        a = (dx, office["y0"] + 11.0)
        self.pos = (a[0], a[1], 0.0)
        line = Line([a, (bx, a[1] - 4.0), (bx, lift_y1)])
        self.body = self.head = math.atan2(-4.0, bx - dx)
        self.walk_line(line, q(line.length / SPEED))

        self.begin_stage("lift")
        mid = (lift_y0 + lift_y1) / 2
        self.straight((bx, lift_y1), (bx, mid), q((lift_y1 - mid) / SPEED))
        self.stand(0.5, body=south, head=south)
        n = round(4.0 / DT)
        x, y, _ = self.pos
        self.emit(n, lambda k: (x, y, cz * smooth(k / n), south, south, 0.0, 3.0, 3.5), "walk", "lift")
        self.pos = (x, y, cz)
        self.stand(0.5, body=south, head=south)

        self.begin_stage("link")
        self.cuts.append(self.now)
        self.pos = (bx, gown_y1 + 12.0, cz)
        self.straight((bx, self.pos[1]), (bx, gown_y1), q(12.0 / SPEED))

        self.begin_stage("gowning")
        bench = gown_y1 - 3.0
        self.straight((bx, gown_y1), (bx, bench), q(3.0 / SPEED))
        self.stand(2.0, body=south, head=wrap(south + 0.6), pitch=-0.4)
        self.outfit.append([self.now, "suit"])
        self.stand(2.0, body=south, head=south, pitch=0.0)
        line = Line([(bx, bench), (bx, 0.0), (shower_x0, 0.0)])
        self.walk_line(line, q(line.length / SPEED))

        self.begin_stage("air shower")
        mid = (shower_x0 + ox) / 2
        self.straight((shower_x0, 0.0), (mid, 0.0), q((mid - shower_x0) / SPEED))
        self.stand(2.5, body=east, head=east, pitch=0.2)
        self.straight((mid, 0.0), (ox, 0.0), q((ox - mid) / SPEED))

        self.begin_stage("clean floor")
        self.floor_start = self.now

    # the sights

    def hoist_xs(self):
        s, fl = self.s, self.fl
        out = []
        for ph, (ox, L) in enumerate(zip(s["offsets"], s["lengths"])):
            x = ox + 10
            while x < ox + L - 10:
                if all(not (st["x0"] < x + 6 and st["x1"] > x - 3) for st in fl.stockers):
                    out.append((ph, round(x, 3)))
                x += 20
        return out

    def watch_cam(self, view, look, hoist=False):
        """A fixed camera over his shoulder that frames him and the sight, or None."""
        key = (tuple(view), tuple(look), hoist)
        if key not in self._wc:
            self._wc[key] = self._watch_cam(view, look, hoist)
        return self._wc[key]

    def _watch_cam(self, view, look, hoist):
        fl, cz = self.fl, self.cz
        head = (view[0], view[1], cz + EYE)
        tries = []
        if hoist:
            for a in (2.4, 2.8, 2.0, 3.2):
                for b in (0.6, 0.9, 0.3, -0.4, -0.7):
                    for c in (1.0, 1.3, 0.8, 1.6, EYE + 0.35):
                        tries.append((view[0] - a, view[1] - b, cz + c))
        else:
            bay = None
            for bi, (ax, hw, sg) in fl.aisle.items():
                b = self.s["bays"][bi]
                if abs(ax - view[0]) < 1e-6 and b["x0"] <= view[0] <= b["x1"] and b["y0"] <= view[1] <= b["y1"]:
                    bay = bi
            ax, hw, sg = fl.aisle[bay]
            away = 1 if look[0] < ax else -1
            for a in (2.4, -2.4, 2.8, -2.8, 2.0, -2.0, 3.2, -3.2):
                for b in (0.9, 1.1, 0.6, 1.3):
                    for c in (0.35, 0.1, 0.6, -0.2):
                        x = view[0] + away * b
                        if abs(x - ax) > hw - 0.35:
                            continue
                        tries.append((x, view[1] + a, cz + EYE + c))
        for cam in tries:
            if fl.hits_tool(cam[0], cam[1], cam[2], 0.3) or not fl.in_hall(*cam):
                continue
            if not inside({"x0": -1e9, "x1": 1e9, "y0": -fl.sp / 2 - fl.depth + 0.3, "y1": fl.sp / 2 + fl.depth - 0.3}, cam[0], cam[1]):
                continue
            d = math.dist(cam, head)
            if not 1.6 <= d <= 3.9:
                continue
            for w in (0.5, 0.4, 0.6, 0.3, 0.7):
                lk = tuple(head[i] + (look[i] - head[i]) * w for i in range(3))
                v = [lk[i] - cam[i] for i in range(3)]
                if ang3(v, [head[i] - cam[i] for i in range(3)]) <= IN_FRAME and \
                        ang3(v, [look[i] - cam[i] for i in range(3)]) <= IN_FRAME:
                    return cam, lk
        return None

    def wide_cam(self, view, look, fallback_x=None):
        """A high camera down the aisle (or the spine), at least 15 m away."""
        fl, cz = self.fl, self.cz
        z = cz + WIDE_Z
        cands = []
        for bi, (ax, hw, sg) in fl.aisle.items():
            if abs(ax - view[0]) < 1e-6:
                b = self.s["bays"][bi]
                if b["x0"] <= view[0] <= b["x1"] and min(b["y0"], b["y1"]) <= view[1] <= max(b["y0"], b["y1"]):
                    for y in (sg * (fl.sp / 2 + 0.6), sg * (fl.sp / 2 + fl.depth - 1.0)):
                        if abs(y - view[1]) >= 15:
                            cands.append((ax, y, z))
        if not cands:  # on the spine
            for dx in (-22, 22, -30, 30, -16, 16):
                x = view[0] + dx
                if fl.clear_of_stockers(x, 1.5):
                    cands.append((x, -LANE - 0.4, z))
        return cands

    def candidates(self, src, dist, prev):
        s, run, fl = self.s, self.run, self.fl
        t0 = self.t
        used = {x["key"] for x in self.sights}
        kinds = [x["kind"] for x in self.sights]
        groups = {x["group"] for x in self.sights if x["group"] is not None}
        places = {x["place"] for x in self.sights}
        out = []

        def walk_of(view):
            k = (round(view[0], 4), round(view[1], 4))
            if k not in dist:
                return None
            w = q(dist[k] / SPEED)
            return w if w <= MAX_WALK else None

        def add(kind, key, group, tool, view, look, sev, numbers, walk, t_arr):
            if key in used:
                return
            watch = WATCH_BIG if kind == "breakdown" else WATCH
            if self.now + TURN + walk + watch + CLOSE > MAX_FILM:
                return
            if t_arr + watch * RATE["watch"] / 60 + CLOSE * RATE["watch"] / 60 > s["to"]:
                return
            want = math.atan2(look[1] - view[1], look[0] - view[0])
            k = (round(view[0], 4), round(view[1], 4))
            if k == src:
                arrive_heading = self.body
            else:
                arrive_heading = Line(fl.route(prev, src, k)).last_heading()
            if abs(wrap(arrive_heading - want)) < math.radians(35):
                return
            cam = self.watch_cam(view, look, hoist=kind == "hoist")
            if cam is None:
                return
            place = f"bay:{fl.tools[tool]['bay']}" if tool is not None else f"spine:{numbers['phase']}:{round(view[0] / 20)}"
            nov = (1.0 / (1 + kinds.count(kind))) * (0.3 if group is not None and group in groups else 1.0) \
                * (0.5 if place in places else 1.0)
            out.append({"kind": kind, "key": key, "group": group, "tool": tool, "place": place,
                        "view": list(view), "look": list(look),
                        "walk_s": walk, "t_arrive": t_arr, "severity": sev, "novelty": nov,
                        "score": sev * nov / (1 + walk / WALK_SCALE), "numbers": numbers, "cam": cam})

        def per_tool(i, t_arr):
            g = fl.tools[i]["g"]
            mine = fl.by_group[g]
            up = sum(1 for j in mine if run.state(j, t_arr) in (0, 1))
            return g, len(mine), up

        # tools down or in maintenance
        for i in range(len(fl.tools)):
            view, look = fl.tool_view(i)
            w = walk_of(view)
            if w is None:
                continue
            t_arr = t0 + (TURN + w) * RATE["walk"] / 60
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
        # queues and hot lots, at the nearest tool of the group
        best = {}
        for i, t in enumerate(fl.tools):
            view, look = fl.tool_view(i)
            w = walk_of(view)
            if w is None:
                continue
            if t["g"] not in best or (w, i) < best[t["g"]][:2]:
                best[t["g"]] = (w, i, view, look)
        for g, (w, i, view, look) in sorted(best.items()):
            t_arr = t0 + (TURN + w) * RATE["walk"] / 60
            wt = run.waiting(g, t_arr)
            _, n, up = per_tool(i, t_arr)
            if wt >= 10:
                add("queue", f"queue:{g}", g, i, view, look, wt / 10,
                    {"waiting": wt, "tools": n, "up": up, "bottleneck": g == self.bottleneck}, w, t_arr)
            hot = run.hot_waiting(g, t_arr)
            if hot:
                add("hot", f"hot:{hot[0]}:{g}", g, i, view, look, 2 + wt / 20,
                    {"waiting": wt, "lot": hot[0], "tools": n, "up": up}, w, t_arr)
        # the hoist overhead
        rail_y = max(r[0][1] for r in s["rails"] if r[0][1] == r[1][1] and r[0][0] != r[1][0] and abs(r[0][1]) < fl.sp / 2)  # the spine rail on the north side
        for ph, x in self.hoist:
            view = (x, -LANE)
            w = walk_of(view)
            if w is None:
                continue
            t_arr = t0 + (TURN + w) * RATE["walk"] / 60
            look = (x + 2.5, rail_y, s["ride_z"])
            r = run.riding(look[0], t_arr)
            if r >= 3:
                add("hoist", f"hoist:{ph}:{round(x)}", None, None, view, look, r / 5, {"riding": r, "phase": ph}, w, t_arr)
        out.sort(key=lambda c: (-c["score"], c["key"]))
        return out

    def go(self, c, dist, prev, src):
        """Turn, walk to the sight and watch it."""
        fl = self.fl
        k = (round(c["view"][0], 4), round(c["view"][1], 4))
        line = Line(fl.route(prev, src, k)) if k != src else None
        walk = c["walk_s"]
        want = math.atan2(c["look"][1] - c["view"][1], c["look"][0] - c["view"][0])
        eye = (c["view"][0], c["view"][1], self.cz + EYE)
        pitch = math.atan2(c["look"][2] - eye[2], math.dist(eye[:2], c["look"][:2]))
        first = line.at(0.0)[1] if line else None
        head_turn_at = walk - BEFORE  # in the walk's own seconds
        # turn on the spot toward the way out; if the walk is short, the head goes to the sight already
        x, y, z = self.pos
        n = round(TURN / DT)
        early = head_turn_at <= 0

        def turn(k):
            bt = first if (first is not None and k >= 1) else None
            ht = want if early else (first if first is not None else want)
            return x, y, z, bt, ht, (pitch if early else 0.0), 5.0, 3.5

        self.emit(n, turn, "walk", "turn")
        if line is not None:
            self.walk_line(line, walk, head_to=want, head_from=max(0.0, head_turn_at), pitch_to=pitch)
        arrive = self.now
        self.pos = (c["view"][0], c["view"][1], self.cz)
        watch = WATCH_BIG if c["kind"] == "breakdown" else WATCH
        self.stand(watch, body=want, head=want, pitch=pitch, rate="watch", kind="watch",
                   sight=len(self.sights), look=c["look"])
        c["arrive_s"], c["leave_s"] = arrive, self.now
        return c

    def card(self, c):
        s = self.s
        n = c["numbers"]
        g = s["groups"][c["group"]]["name"] if c["group"] is not None else None
        kind = s["tools"][c["tool"]]["kind"] if c["tool"] is not None else None
        tag = "On the SMT2020 model: the run's own numbers."
        if c["kind"] == "breakdown":
            title = f"A {kind} tool is down: group {g}"
            lines = [f"{n['up']} of {n['tools']} tools in the group are up",
                     f"{n['waiting']} lots wait for this group",
                     f"Down since {fmt(n['since'])}" + (f"; back at {fmt(n['until'])}" if n["until"] else "")]
        elif c["kind"] == "maintenance":
            title = f"Planned maintenance: group {g}"
            lines = [f"{n['up']} of {n['tools']} tools in the group are up",
                     f"{n['waiting']} lots wait for this group",
                     f"In maintenance since {fmt(n['since'])}" + (f"; back at {fmt(n['until'])}" if n["until"] else "")]
        elif c["kind"] == "queue":
            title = f"{n['waiting']} lots wait for group {g}"
            lines = [f"A {kind} group of {n['tools']} tools, {n['up']} up now"]
            if n["bottleneck"]:
                lines.append("The longest queue in this stretch of the run")
        elif c["kind"] == "hot":
            title = f"A hot lot waits at group {g}"
            lines = [f"Lot {n['lot']} is hot: it goes ahead of the others",
                     f"{n['waiting']} lots wait for this group"]
        else:
            title = f"{n['riding']} lots on the overhead hoist"
            lines = ["Riding the rail within 15 m of him, between tools and stockers"]
        lines.append(tag)
        return {"sight": c["key"], "s0": c["arrive_s"], "s1": c["leave_s"], "title": title, "lines": lines,
                "fab_time": fmt(c["t_arrive"])}

    def plan(self):
        s, run, fl = self.s, self.run, self.fl
        # the group with the longest queue over the run window
        ts = [s["from"] + (s["to"] - s["from"]) * i / 12 for i in range(13)]
        groups = sorted({t["g"] for t in fl.tools})
        self.bottleneck = max(groups, key=lambda g: (sum(run.waiting(g, t) for t in ts), -g))
        self.way_in()
        self.hoist = self.hoist_xs()
        fl.build(self.entry, self.hoist)
        fl.rooms_in = self.rooms_in
        self.cams = {}
        while len(self.sights) < MAX_SIGHTS:
            src = (round(self.pos[0], 4), round(self.pos[1], 4))
            dist, prev = fl.dijkstra(src)
            cands = self.candidates(src, dist, prev)
            if len(cands) < 2:
                break
            c = cands[0]
            c["candidates"] = [{k: o[k] for k in ("key", "kind", "severity", "novelty", "walk_s", "score")}
                               for o in cands[:12]]
            self.go(c, dist, prev, src)
            self.sights.append(c)
        # the closing shot: he keeps watching, the fab keeps working
        self.stand(CLOSE, rate="watch", kind="close")
        self.stages[-1]["s1"] = self.now
        last = self.samples[-1]
        self.samples.append([self.now, last[1], last[2], last[3], self.body, self.head, self.pitch])
        self.meta.append(dict(self.meta[-1]))
        self.knots.append([self.now, self.t])
        self.camera()
        self.check()
        return self.out()

    # the camera

    def piece(self, i):
        """The stretch of his path the walking camera may look back along: since the last cut or watch."""
        lo = i
        while lo > 0 and self.samples[lo][0] not in self.cuts and self.meta[lo - 1]["kind"] not in ("watch", "close"):
            lo -= 1
        hi = i
        while hi + 1 < len(self.samples) and self.samples[hi + 1][0] not in self.cuts and \
                self.meta[hi + 1]["kind"] not in ("watch", "close"):
            hi += 1
        return lo, hi

    def follow(self, i, back=2.6):
        """Behind him along his own path, a little to his right, at the shoulder, aimed through his head."""
        lo, hi = self.piece(i)
        pts = self.samples[lo:i + 1]
        acc, pos, hb = 0.0, None, None
        for a, b in zip(reversed(pts[:-1]), reversed(pts[1:])):
            d = math.hypot(b[1] - a[1], b[2] - a[2])
            if d < 1e-9:
                continue
            if acc + d >= back:
                u = (back - acc) / d
                pos = (b[1] + (a[1] - b[1]) * u, b[2] + (a[2] - b[2]) * u)
                hb = math.atan2(b[2] - a[2], b[1] - a[1])
                break
            acc += d
        me = self.samples[i]
        if pos is None:
            # extend behind where this stretch starts, against the way he walks it
            h0 = me[4]
            for a, b in zip(self.samples[lo:hi], self.samples[lo + 1:hi + 1]):
                if math.hypot(b[1] - a[1], b[2] - a[2]) > 1e-9:
                    h0 = math.atan2(b[2] - a[2], b[1] - a[1])
                    break
            first = pts[0]
            rest = back - acc
            pos = (first[1] - rest * math.cos(h0), first[2] - rest * math.sin(h0))
            hb = h0
        dx, dy = me[1] - pos[0], me[2] - pos[1]
        dd = math.hypot(dx, dy)
        f = (dx / dd, dy / dd) if dd > 1e-6 else (math.cos(hb), math.sin(hb))
        right = (f[1], -f[0])
        cam = (pos[0] + 0.5 * right[0], pos[1] + 0.5 * right[1], me[3] + EYE + 0.35)
        look = (me[1] + 6 * f[0], me[2] + 6 * f[1], me[3] + EYE)
        return cam, look

    def aim(self, i, cam):
        """Hold a camera where it is and keep him in the middle of the frame."""
        me = self.samples[i]
        head = (me[1], me[2], me[3] + EYE)
        v = [head[k] - cam[k] for k in range(3)]
        n = math.sqrt(sum(c * c for c in v)) or 1.0
        return tuple(head[k] + 4 * v[k] / n for k in range(3))

    def camera(self):
        fl, cz = self.fl, self.cz
        lift = [st for st in self.stages if st["name"] == "lift"][0]
        lobby = [r for r in self.rooms_in if r["name"] == "lobby"][0]
        want = []  # (cam, look, mode, source)
        wide = {}  # sample index -> (cams to try, look target fn)
        # wide windows: the reveal, each tool down, the close
        windows = [(self.floor_start, self.floor_start + 4.0, None)]
        for j, c in enumerate(self.sights):
            if c["kind"] == "breakdown":
                windows.append((c["arrive_s"] - 0.5, c["arrive_s"] + 3.0, j))
        close_s0 = self.sights[-1]["leave_s"] if self.sights else self.floor_start
        windows.append((close_s0, self.samples[-1][0] + 1e-9, len(self.sights) - 1 if self.sights else None))
        reveal_cam = (self.entry[0] + 22.0, 0.0, cz + WIDE_Z)
        for i, p in enumerate(self.samples):
            m = self.meta[i]
            head = (p[1], p[2], p[3] + EYE)
            s = p[0]
            if lift["s0"] <= s < lift["s1"]:
                want.append(((self.ax + 3.0, lobby["y0"] + 4.7, 1.7), (self.ax, lobby["y0"] - 0.3, 1.4), "fixed", "lift"))
                continue
            win = [w for w in windows if w[0] <= s < w[1]]
            if win:
                w = win[0]
                if w[2] is None:
                    want.append((reveal_cam, head, "wide", ("wide", w[0])))
                    continue
                c = self.sights[w[2]]
                look = tuple(head[k] + (c["look"][k] - head[k]) * 0.5 for k in range(3)) if s < c["leave_s"] else head
                chosen = None
                for cam in self.wide_cam(c["view"], c["look"]):
                    if fl.hits_tool(*cam, 0.3) or not fl.in_hall(*cam):
                        continue
                    v = [look[k] - cam[k] for k in range(3)]
                    if ang3(v, [head[k] - cam[k] for k in range(3)]) <= IN_FRAME and (
                            s < c["arrive_s"] + 1.5 or s >= c["leave_s"] or
                            ang3(v, [c["look"][k] - cam[k] for k in range(3)]) <= IN_FRAME):
                        chosen = cam
                        break
                if chosen is not None:
                    want.append((chosen, look, "wide", ("wide", w[0])))
                    continue
            held = [j for j, c in enumerate(self.sights) if c["arrive_s"] <= s <= c["leave_s"]]
            if m["kind"] == "watch" or held:
                j = m["sight"] if m["kind"] == "watch" else held[-1]
                cam, look = self.sights[j]["cam"]
                want.append((cam, look, "shoulder", ("watch", j)))
                continue
            for back in (2.6, 2.2, 1.9):
                cam, look = self.follow(i, back)
                if self.cam_ok(i, cam, look, "shoulder"):
                    break
            else:  # the aisle ends behind him: hold the last camera and keep him framed
                cam = want[-1][0]
                look = self.aim(i, cam)
            want.append((cam, look, "shoulder", "follow"))
        # ease between the walking camera and the watching camera over a second
        out = [list(want[0][0]) + list(want[0][1]) + [want[0][2]]]
        i = 1
        while i < len(want):
            a, b = want[i - 1], want[i]
            if a[2] == "shoulder" and b[2] == "shoulder" and a[3] != b[3]:
                n = 8
                start = out[-1]
                blend = []
                ok = True
                for k in range(n):
                    if i + k >= len(want) or want[i + k][3] != b[3]:
                        break
                    u = smooth((k + 1) / n)
                    cam = [start[j] + (want[i + k][0][j] - start[j]) * u for j in range(3)]
                    look = [start[3 + j] + (want[i + k][1][j] - start[3 + j]) * u for j in range(3)]
                    if not self.cam_ok(i + k, cam, look, "shoulder"):
                        ok = False
                        break
                    blend.append(cam + look + ["shoulder"])
                if ok and blend:
                    out += blend
                    i += len(blend)
                    continue
            out.append(list(b[0]) + list(b[1]) + [b[2]])
            i += 1
        self.cam = [[self.samples[i][0]] + [round(v, 4) for v in c[:6]] + [c[6]] for i, c in enumerate(out)]

    def cam_ok(self, i, cam, look, mode):
        fl = self.fl
        p = self.samples[i]
        head = (p[1], p[2], p[3] + EYE)
        if fl.hits_tool(cam[0], cam[1], cam[2], 0.25):
            return False
        if p[0] > self.floor_start + 0.5 and not fl.in_hall(*cam):
            return False
        if mode == "shoulder" and not 1.55 <= math.dist(cam, head) <= 3.95:
            return False
        v = [look[k] - cam[k] for k in range(3)]
        if ang3(v, [head[k] - cam[k] for k in range(3)]) > IN_FRAME:
            return False
        for c in self.sights:
            if c["arrive_s"] + 1.5 <= p[0] <= c["leave_s"] and \
                    ang3(v, [c["look"][k] - cam[k] for k in range(3)]) > IN_FRAME:
                return False
        return True

    def check(self):
        """The planner's own checks, so a bad plan is never written."""
        for i, c in enumerate(self.cam):
            if c[7] == "fixed":
                continue
            if not self.cam_ok(i, c[1:4], c[4:7], c[7]):
                raise SystemExit(f"camera fails its checks at {c[0]:.3f} s ({c[7]}): {c[1:4]}")

    def out(self):
        rooms = self.rooms_in + self.fl.rooms
        sights = []
        for c in self.sights:
            d = {k: c[k] for k in ("kind", "key", "group", "tool", "place", "view", "look", "walk_s", "t_arrive", "severity",
                                   "novelty", "score", "numbers", "arrive_s", "leave_s", "candidates")}
            sights.append(d)
        r4 = lambda v: round(v, 4)
        return {
            "what": "A Walk Through the Fab: a visitor's route, gaze and camera, chosen by the run",
            "badge": BADGE,
            "model": self.s.get("model"),
            "seed": self.seed,
            "fps": FPS,
            "dt": DT,
            "speed": SPEED,
            "eye": EYE,
            "fov_v": FOV_V,
            "clock_rate": RATE,
            "score": "severity x novelty / (1 + walk_s / 15); novelty 1/(1 + same kind seen) x 0.3 if the group "
                     "was seen x 0.5 if the place was seen",
            "entry": list(self.entry),
            "car": {k: r4(v) for k, v in self.car.items()},
            "outfit": self.outfit,
            "rooms": [{k: (r4(v) if isinstance(v, float) else v) for k, v in r.items()} for r in rooms],
            "stages": self.stages,
            "cuts": self.cuts,
            "clock": self.knots,
            "path": [[p[0]] + [r4(v) for v in p[1:]] for p in self.samples],
            "camera": self.cam,
            "sights": sights,
            "cards": [self.card(c) for c in self.sights],
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
    plan = Planner(s, tr, seed).plan()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, separators=(",", ":")))
    sights = plan["sights"]
    print(f"{len(sights)} sights, {plan['path'][-1][0]:.1f} s:", ", ".join(x["key"] for x in sights))


if __name__ == "__main__":
    main(sys.argv[1:])
