"""Exposure sheets (docs/DRAWN-FILM.md): which drawing each level shows on every frame, where it sits, and where the
camera is. A level holds its drawing until the sheet changes it; a cycle repeats its drawings, each held `on` frames
(two by default: animation on twos)."""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Level:
    name: str
    depth: float
    timeline: list                      # drawing name (or None) for every frame of the shot
    at: tuple = (0.0, 0.0)              # where the drawing's top-left corner sits in the frame's world, in pixels
    path: list = field(default_factory=list)   # [(frame, x, y)]: a slide; the drawing travels between the keys


@dataclass
class Sheet:
    shot: str
    frames: int
    fps: int
    levels: list
    camera: list                        # [(frame, {"x", "y", "zoom"})]
    cuts: list
    captions: list
    palette: str = ""

    def at(self, f):
        return {lv.name: lv.timeline[f] if f < len(lv.timeline) else None for lv in self.levels}

    def camera_at(self, f):
        return _ease_keys(self.camera, f, ("x", "y", "zoom"), {"x": 0.0, "y": 0.0, "zoom": 1.0})

    def place(self, lv, f):
        """Where level lv's drawing sits on frame f: its `at`, moved along its path if it has one."""
        if not lv.path:
            return lv.at
        keys = [(k[0], {"x": k[1], "y": k[2]}) for k in lv.path]
        p = _ease_keys(keys, f, ("x", "y"), {"x": lv.at[0], "y": lv.at[1]})
        return (p["x"], p["y"])


def _ease_keys(keys, f, names, default):
    if not keys:
        return dict(default)
    keys = sorted(keys, key=lambda k: k[0])
    if f <= keys[0][0]:
        return {n: float(keys[0][1].get(n, default[n])) for n in names}
    for (f0, a), (f1, b) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            u = 0.0 if f1 == f0 else (f - f0) / (f1 - f0)
            u = u * u * (3 - 2 * u)     # ease in and out, as a camera operator would
            return {n: float(a.get(n, default[n])) + (float(b.get(n, default[n])) - float(a.get(n, default[n]))) * u for n in names}
    return {n: float(keys[-1][1].get(n, default[n])) for n in names}


def _timeline(spec, frames):
    if "cycle" in spec:
        on = int(spec.get("on", 2))
        cyc = list(spec["cycle"])
        return [cyc[(f // on) % len(cyc)] for f in range(frames)] if cyc else [None] * frames
    out = []
    for name, n in spec.get("cels", []):
        out += [name] * int(n)
    return (out + [None] * frames)[:frames] if len(out) < frames else out[:frames]


def load(src):
    d = src if isinstance(src, dict) else json.loads(Path(src).read_text())
    frames = int(d["frames"])
    levels = [Level(name=s["name"], depth=float(s.get("depth", 0.5)), timeline=_timeline(s, frames),
                    at=tuple(float(v) for v in s.get("at", (0, 0))), path=[tuple(k) for k in s.get("path", [])])
              for s in d["levels"]]
    return Sheet(shot=str(d.get("shot", "")), frames=frames, fps=int(d.get("fps", 24)), levels=levels,
                 camera=[(int(k[0]), dict(k[1])) for k in d.get("camera", [])], cuts=[int(c) for c in d.get("cuts", [])],
                 captions=list(d.get("captions", [])), palette=str(d.get("palette", "")))


def validate(sheet, names):
    """Everything wrong with a sheet, as sentences; [] when every frame of every level resolves to a drawing (D1)."""
    errors = []
    for lv in sheet.levels:
        missing = sorted({n for n in lv.timeline if n is not None and n not in names})
        for n in missing:
            errors.append(f"level {lv.name}: no drawing called {n}")
        empty = [f for f, n in enumerate(lv.timeline) if n is None]
        if empty:
            errors.append(f"level {lv.name}: frames {empty[0]} to {empty[-1]} have no drawing ({len(empty)} frames)")
        if not 0.0 <= lv.depth <= 1.0:
            errors.append(f"level {lv.name}: depth {lv.depth} is outside 0 to 1")
    for f, _ in sheet.camera:
        if not 0 <= f <= sheet.frames:
            errors.append(f"camera key at frame {f} is outside the shot")
    return errors
