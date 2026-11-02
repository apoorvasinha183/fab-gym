"""The 3D fab's helper side (docs/FAB-3D.md): the campus cut into cells, the copper rule, and a whole-fab run held in
memory that answers for the cells near the viewer only. From the SMT2020 testbed; a gigafab-style layout of our own
design; not a real fab."""

import math

SIZE = 24.0          # a cell's side, metres (assumed)
EVERY = 10.0         # minutes between the run's frames (assumed)
WINDOW = 30.0        # minutes of carrier moves fetched at a time


def cell_of(x, y, size=SIZE):
    return f"{math.floor(x / size)},{math.floor(y / size)}"


def cells(building, size=SIZE):
    """Cells of `size` metres over the campus: each cell's tools (by centre, into building['tools']), rail stretches
    (every cell a stretch crosses, named 'n{from}>n{to}'), stockers (by centre) and bounds [x0, x1, y0, y1]."""
    out = {}

    def get(cid):
        if cid not in out:
            ix, iy = (int(v) for v in cid.split(","))
            out[cid] = {"tools": [], "stretches": [], "stockers": [], "bounds": [ix * size, (ix + 1) * size, iy * size, (iy + 1) * size]}
        return out[cid]

    for i, t in enumerate(building["tools"]):
        get(cell_of((t[1] + t[2]) / 2, (t[3] + t[4]) / 2, size))["tools"].append(i)
    nodes = building["track"]["nodes"]
    for a, b, _ in building["track"]["edges"]:
        (x0, y0), (x1, y1) = nodes[a][:2], nodes[b][:2]
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / (size / 4)) + 1)
        name = f"n{a}>n{b}"
        for k in range(n + 1):
            u = k / n
            c = get(cell_of(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, size))
            if name not in c["stretches"]:
                c["stretches"].append(name)
    for i, s in enumerate(building.get("stockers", [])):
        get(cell_of((s[0] + s[1]) / 2, (s[2] + s[3]) / 2, size))["stockers"].append(i)
    return {"size": size, "cells": dict(sorted(out.items()))}


def is_copper(group):
    """The copper rule (docs/FAB-3D.md, F2): a lot bound for a back-end (copper) group rides a copper carrier."""
    return bool(group) and "_BE_" in group


class Run:
    """A whole-fab run's moods (`fabsim moods`) with the building's tools mapped onto them, and carrier windows
    (`fabsim replay`) fetched on demand by `replay(start, end)` and cached."""

    def __init__(self, moods, building, cell_map, replay, every=EVERY, minutes=None):
        self.moods = moods
        self.every = every
        self.frames = moods["frames"]
        self.minutes = minutes if minutes is not None else (self.frames[-1]["t"] if self.frames else 0.0)
        self.tool_moods = moods["tool_moods"]
        self.cells = cell_map["cells"]
        self.building = building
        index = {name: j for j, name in enumerate(moods["tools"])}
        seen = {}
        self.to_moods = []
        for t in building["tools"]:
            k = seen.get(t[0], 0) + 1
            seen[t[0]] = k
            self.to_moods.append(index.get(f"{t[0]}#{k}"))
        self.group_index = {g: j for j, g in enumerate(moods["group_names"])}
        self._replay = replay
        self._windows = {}

    def frame_at(self, t):
        """The frame at or before minute t."""
        k = max(0, min(len(self.frames) - 1, int(math.floor(t / self.every + 1e-9))))
        while k > 0 and self.frames[k]["t"] > t:
            k -= 1
        return self.frames[k]

    def mood_at(self, tool, t):
        j = self.to_moods[tool]
        if j is None:
            return None
        return self.tool_moods[self.frame_at(t)["tools"][j]]

    def window(self, t):
        w = math.floor(t / WINDOW)
        if w not in self._windows:
            got = self._replay(w * WINDOW, (w + 1) * WINDOW)
            if isinstance(got, dict) and "error" in got:
                return got  # busy or refused: not kept, asked again next time
            self._windows[w] = got
        return self._windows[w]

    def state(self, t, cell_ids, span=0.0):
        bad = [c for c in cell_ids if c not in self.cells]
        if bad:
            return {"error": f"No such cell: {', '.join(bad)}."}
        f = self.frame_at(t)
        tools, queues, stretches = {}, {}, set()
        for cid in cell_ids:
            c = self.cells[cid]
            for i in c["tools"]:
                tools[str(i)] = self.mood_at(i, t)
                g = self.building["tools"][i][0]
                if g in self.group_index:
                    queues[g] = f["queues"][self.group_index[g]]
            stretches.update(c["stretches"])
        # carriers on these cells' stretches at t, or (with span) every stay overlapping [t, t + span] so the scene
        # can glide them between asks; each with its times on the stretch
        carriers, seen = [], set()
        end = t + max(0.0, span)
        for wk in range(math.floor(t / WINDOW), math.floor(end / WINDOW) + 1):
            w = self.window(wk * WINDOW)
            if not (isinstance(w, dict) and "stays" in w):
                continue
            fields = w.get("fields", [])
            for row_ in w["stays"]:
                row = dict(zip(fields, row_))
                name = f"{row['from']}>{row['to']}"
                if name not in stretches:
                    continue
                t_in, t_out = row["t_in"], row["t_out"] if row["t_out"] is not None else math.inf
                live = (t_in <= t < t_out) if span <= 0 else (t_in < end and t_out > t)
                if not live or (row["vehicle"], name, t_in) in seen:
                    continue
                seen.add((row["vehicle"], name, t_in))
                dur = t_out - t_in
                along = 1.0 if not math.isfinite(dur) or dur <= 0 else (max(t, t_in) - t_in) / dur
                carriers.append({"vehicle": row["vehicle"], "stretch": name, "along": round(min(1.0, max(0.0, along)), 4),
                                 "t_in": t_in, "t_out": t_out if math.isfinite(t_out) else None,
                                 "loaded": bool(row["loaded"]), "hot": bool(row["hot"]),
                                 "copper": bool(row["loaded"]) and is_copper(row.get("next_group"))})
        return {"t": f["t"], "tools": tools, "queues": queues, "carriers": carriers}


VOICE_MODEL = "muse-voice-transcribe-1.0"


def transcribe(base_url, key_file, audio, mime, timeout=60):
    """Spoken words to text with Meta's speech model, as an OpenAI-style transcription (multipart form). The key is
    read here and sent only in the request header."""
    import json
    import urllib.request
    import uuid
    from pathlib import Path
    key = Path(key_file).read_text().strip()
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a"}.get(mime.split(";")[0], "webm")
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{VOICE_MODEL}\r\n'.encode(),
             f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="question.{ext}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),
             audio, f"\r\n--{b}--\r\n".encode()]
    req = urllib.request.Request(base_url.rstrip("/") + "/audio/transcriptions", data=b"".join(parts), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return (out.get("text") or "").strip()
