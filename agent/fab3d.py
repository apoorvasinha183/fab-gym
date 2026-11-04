"""The 3D fab's helper side (docs/FAB-3D.md): the campus cut into cells, the copper rule, and a whole-fab run held in
memory that answers for the cells near the viewer only. From the SMT2020 testbed; a gigafab-style layout of our own
design; not a real fab."""

import math

SIZE = 24.0          # a cell's side, metres (assumed)
EVERY = 10.0         # minutes between the run's frames (assumed)
WINDOW = 30.0        # minutes of carrier moves fetched at a time
PARK = 5.0           # minutes: with a span, stays that ended this long before t are sent too (a vehicle standing at a port)


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
        # carriers on these cells' stretches at t, or (with span) every stay overlapping [t - PARK, t + span] so the
        # scene can glide them between asks and hold one standing at a port; each with its times on the stretch
        carriers, seen, latest = [], set(), {}
        end = t + max(0.0, span)
        start = t - PARK if span > 0 else t
        for wk in range(math.floor(max(0.0, start) / WINDOW), math.floor(end / WINDOW) + 1):
            w = self.window(wk * WINDOW)
            if not (isinstance(w, dict) and "stays" in w):
                continue
            fields = w.get("fields", [])
            for row_ in w["stays"]:
                row = dict(zip(fields, row_))
                if row["t_in"] <= t:
                    latest[row["vehicle"]] = max(latest.get(row["vehicle"], -math.inf), row["t_in"])
                name = f"{row['from']}>{row['to']}"
                if name not in stretches:
                    continue
                t_in, t_out = row["t_in"], row["t_out"] if row["t_out"] is not None else math.inf
                live = (t_in <= t < t_out) if span <= 0 else (t_in < end and t_out > start)
                if not live or (row["vehicle"], name, t_in) in seen:
                    continue
                seen.add((row["vehicle"], name, t_in))
                dur = t_out - t_in
                along = 1.0 if not math.isfinite(dur) or dur <= 0 else (max(t, t_in) - t_in) / dur
                carriers.append({"vehicle": row["vehicle"], "stretch": name, "along": round(min(1.0, max(0.0, along)), 4),
                                 "t_in": t_in, "t_out": t_out if math.isfinite(t_out) else None,
                                 "loaded": bool(row["loaded"]), "hot": bool(row["hot"]),
                                 "copper": bool(row["loaded"]) and is_copper(row.get("next_group"))})
        # an ended stay stays only when it is that vehicle's latest move anywhere: one that drove on elsewhere is not
        # left standing in these cells
        carriers = [c for c in carriers if c["t_out"] is None or c["t_out"] > t or c["t_in"] >= latest.get(c["vehicle"], -math.inf)]
        return {"t": f["t"], "tools": tools, "queues": queues, "carriers": carriers}


VOICE_MODEL = "muse-voice-transcribe-1.0"


def prepare_audio(audio):
    """Meta accepts mono 16-bit PCM WAV at 16 or 24 kHz; convert other recordings locally."""
    import io
    import subprocess
    import tempfile
    import wave
    from pathlib import Path

    def duration(data):
        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                if wav.getnchannels() == 1 and wav.getsampwidth() == 2 and wav.getframerate() in (16000, 24000):
                    return wav.getnframes() / wav.getframerate()
        except (wave.Error, EOFError):
            pass
        return None

    seconds = duration(audio)
    if seconds is None:
        with tempfile.TemporaryDirectory(prefix="fabgym-voice-") as tmp:
            source, dest = Path(tmp) / "input.audio", Path(tmp) / "output.wav"
            source.write_bytes(audio)
            try:
                p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
                                    "-i", str(source), "-t", "601", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                                    "-map_metadata", "-1", str(dest)], capture_output=True, timeout=60)
            except FileNotFoundError:
                raise ValueError("Install FFmpeg to convert microphone recordings, or send mono 16-bit PCM WAV at 16 or 24 kHz.") from None
            if p.returncode:
                raise ValueError("The recording could not be decoded; try recording it again.")
            audio = dest.read_bytes()
            seconds = duration(audio)
    if seconds is None or not 0 < seconds <= 600:
        raise ValueError("The recording must contain between 0 and 600 seconds of audio.")
    return audio, seconds


def transcribe(base_url, key_file, audio, mime, timeout=60, meter=None, remaining=None):
    """Meta's file transcription contract; https://dev.meta.ai/docs/speech-to-text (checked 5 Nov 2026)."""
    import json
    import math
    import urllib.request
    import uuid
    from contextlib import nullcontext
    from pathlib import Path
    from agent import spend

    audio, seconds = prepare_audio(audio)
    prices = json.loads(spend.PRICES.read_text())
    per_hour = prices["meta"]["audio"][VOICE_MODEL]["usd_per_hour"]
    estimated = math.floor(seconds) * per_hour / 3600
    b = uuid.uuid4().hex
    settings = json.dumps({"model": VOICE_MODEL, "mode": "PUSH_TO_TALK", "audioEncoding": "WAV"})
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="request"\r\nContent-Type: application/json\r\n\r\n{settings}\r\n'.encode(),
             f'--{b}\r\nContent-Disposition: form-data; name="audio"; filename="question.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
             audio, f"\r\n--{b}--\r\n".encode()]
    with meter.request() if meter is not None else nullcontext():
        if (meter is not None and estimated > meter.cap_usd - meter.usd) or (remaining and estimated > remaining()):
            raise spend.CapReached("The recording would exceed the speech or total budget; type the question instead.")
        key = Path(key_file).read_text().strip()
        req = urllib.request.Request(base_url.rstrip("/") + "/asr/transcribe", data=b"".join(parts), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={b}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
        if meter is not None:
            # Billed audio is rounded down to whole seconds. Fall back to the uploaded
            # duration if a provider omits its timing, so the call is still counted.
            processed = float(out.get("audioDurationMs", seconds * 1000)) / 1000
            if not math.isfinite(processed) or processed < 0:
                processed = seconds
            meter.add_usd(math.floor(processed) * per_hour / 3600)
        return (out.get("transcript") or "").strip()


# ------------------------------------------------------------------ from the parking lot to the cleanroom (F9)

LOT = [-78.0, 4.0, -24.0, 60.0]                       # x0, y0, x1, y1 west of phase 1, ground (assumed)
PAVILION = [-14.0, 27.0, 0.0, -6.0, 35.6, 3.6]        # the visitors' entrance against the west wall (assumed)
GROUND_DOOR = [-6.0, 30.7, 0.0, -5.7, 31.9, 2.4]      # through the west wall into the lift (assumed)
LOBBY_WALLS = [[-0.8, 30.0, 7.5, -0.6, 32.8, 10.5],    # the lift lobby on the clean floor, closed off from the
               [-2.6, 32.6, 7.5, -0.6, 32.8, 10.5]]    # west-end strip so the only way on is through gowning (assumed)


def entrance(permit):
    """The way in, for the guide's tour: the permit set's passenger lift, gowning room P1-GW1 with its doors, air
    shower, lockers, bench and garment rack, unchanged; ours (assumed) where the permit set has nothing: the parking
    lot, the visitors' pavilion, the ground door into the lift, the lift lobby's walls, the cars. `permit` is
    boxes.json of the permit set (key -> {key, cls, box}); boxes are [x0, y0, z0, x1, y1, z1] in plan metres."""
    by = {e["key"]: e for e in permit.values()}

    def take(key):
        return {"key": key, "box": by[key]["box"]}

    p = {"lift": take("permit/lift/P1"), "room": take("permit/room/P1-GW1"),
         "entry_door": take("permit/door/P1-GW1/in"), "clean_door": take("permit/door/P1-GW1"),
         "air_shower": take("permit/bim/airshower/P1-GW1"), "bench": take("permit/bim/bench/P1-GW1"),
         "rack": take("permit/bim/rack/P1-GW1"),
         "lockers": [take(f"permit/bim/locker/P1-GW1/{i}") for i in range(8)]}
    lift = p["lift"]["box"]
    lx, ly = (lift[0] + lift[3]) / 2, (lift[1] + lift[4]) / 2
    cz = 7.5
    # parked cars, about two in three bays filled, in rows either side of the walkway (assumed); [x, y, yaw, colour]
    cars, k = [], 0
    for row_y, facing in ((8.6, 1), (13.8, -1), (26.0, 1), (36.6, -1), (48.8, 1), (54.0, -1)):
        x = LOT[0] + 2.0
        while x < LOT[2] - 2.0:
            k += 1
            if (k * 7) % 10 < 7 and not (row_y == 36.6 and abs(x - -40.0) < 1.4):
                cars.append([round(x, 2), row_y, 0.0 if facing > 0 else 3.1416, k % 6])
            x += 2.6
    cars.append([-40.0, 36.6, 3.1416, 6])              # the CEO's, by the walkway
    openings = [
        {"name": "ground door", "box": GROUND_DOOR},
        {"name": "entry door", "box": p["entry_door"]["box"]},
        {"name": "cleanroom door", "box": p["clean_door"]["box"]},
        {"name": "lift shaft", "box": [lift[0], lift[1], 6.0, lift[3], lift[4], cz]},
    ]
    door_in = p["entry_door"]["box"]
    door_cr = p["clean_door"]["box"]
    shower = p["air_shower"]["box"]
    sy = (shower[1] + shower[4]) / 2
    room = p["room"]["box"]

    def stop(kind, x, y, z, **kw):
        return {"kind": kind, "at": [round(x, 3), round(y, 3), z], **kw}

    route = [
        stop("lot", -40.0, ly, 0.0),
        stop("via", PAVILION[0] - 1.0, ly, 0.0, via=True),
        stop("pavilion", (PAVILION[0] + PAVILION[3]) / 2, ly, 0.0),
        stop("via", (GROUND_DOOR[0] + GROUND_DOOR[3]) / 2, ly, 0.0, via=True),
        stop("lift", lift[3] - 0.55, ly, 0.0),                 # at the car's far wall, so the camera fits in with him
        stop("via", lift[3] - 0.55, ly, cz, via=True, ride=True),
        stop("via", (door_in[0] + door_in[3]) / 2, ly, cz, via=True),
        stop("via", (door_in[0] + door_in[3]) / 2, door_in[1] - 0.4, cz, via=True),
        stop("gowning", (room[0] + room[3]) / 2, sy + 2.0, cz),
        stop("via", shower[0] - 0.6, sy, cz, via=True, bump=True),   # he is too tall for the air shower: bonk
        stop("air_shower", (shower[0] + shower[3]) / 2, sy, cz),
        stop("via", door_cr[3] + 0.4, sy, cz, via=True),
        stop("via", 0.9, sy, cz, via=True),
        stop("via", 0.9, 1.5, cz, via=True),
        stop("cleanroom", 3.5, 1.0, cz),
    ]
    return {"about": "The permit set's lift, gowning room, air shower and fittings, unchanged; the parking lot, the "
                     "pavilion, the ground door, the lift lobby's walls and the cars are ours, assumed.",
            "permit": p,
            "assumed": {"lot": LOT, "pavilion": PAVILION, "ground_door": GROUND_DOOR, "lobby_walls": LOBBY_WALLS,
                        "cars": cars},
            "openings": openings, "route": route}


# ------------------------------------------------------------------ the campus outside, and the drone's flight (F10)

def exterior(permit):
    """The campus outside the buildings: the permit set's rooftop make-up air units with their curbs, its chillers and
    transformers in the utility yard, unchanged; ours (assumed): the ring road and the road to the yard, trees along
    them, exhaust stacks on the roofs and the signs. Boxes [x0, y0, z0, x1, y1, z1], plan metres."""
    def pick(prefix):
        return [{"key": e["key"], "box": e["box"]} for e in sorted(permit.values(), key=lambda e: e["key"])
                if e["key"].startswith(prefix)]

    units = [u for u in pick("permit/mau/") if "curb" not in u["key"]]
    curbs = [e for e in ({"key": e["key"], "box": e["box"]} for e in permit.values())
             if e["key"].startswith("permit/") and "curb" in e["key"].lower() and "mau" in e["key"].lower()]
    p = {"air_units": units, "curbs": sorted(curbs, key=lambda c: c["key"]),
         "chillers": pick("permit/plant/chiller/"), "transformers": pick("permit/plant/transformer/")}
    # roads 8 m wide: a ring 14 m off the walls, a road west past the lot to the gate, and one south to the yard
    w = 8.0
    roads = [[-23.0, 84.0, 522.0, 84.0 + w], [-23.0, -92.0, -15.0, 84.0], [514.0, -92.0, 522.0, 84.0],
             [-15.0, -92.0, 514.0, -84.0], [86.0, -152.0, 94.0, -92.0], [-110.0, 24.0, -82.0, 24.0 + w]]
    keep = [(-6.0, -70.0, 504.2, 70.0), (-78.0, 4.0, -24.0, 60.0), (40.0, -122.0, 76.0, -98.0), (-14.0, 27.0, -6.0, 35.6),
            (0.0, -185.0, 360.0, -152.0)]

    def clear(x, y, r):
        a = (x - r, y - r, x + r, y + r)
        return all(not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]) for b in keep + [tuple(rd) for rd in roads])

    trees = []
    for x in range(-60, 520, 14):                     # along the north and south sides of the ring
        for y in (96.0, -98.0):
            if clear(x, y, 1.8):
                trees.append([float(x), y, 1.8, 6.0 + (x % 3)])
    for y in range(-80, 92, 14):                      # along the east and west sides
        for x in (-40.0, 530.0):
            if clear(x, float(y), 1.8):
                trees.append([x, float(y), 1.8, 6.0 + (y % 3)])
    stacks = []
    for f0, f1 in ((-6.0, 261.8), (309.8, 504.2)):    # six scrubbed-exhaust stacks on each roof, clear of the air units
        for k in range(6):
            x = f0 + (f1 - f0) * (k + 0.5) / 6
            for y in (-40.0, 40.0):
                if all(not (u["box"][0] - 2 < x < u["box"][3] + 2 and u["box"][1] - 2 < y < u["box"][4] + 2) for u in units):
                    stacks.append([round(x, 2), y, 0.9, 7.0])
    # the heading picture's FabGYM logo (docs/img/fabgym-hero.jpg) on the walls
    # the heading picture's FabGYM logo (docs/img/fabgym-hero.jpg): across the front, over the visitors' entrance,
    # and on the south side; the phases are named by the drone's labels
    signs = [{"kind": "logo", "at": [-6.2, 31.3, 11.5], "facing": "west", "width": 24.0},
             {"kind": "logo", "at": [128.0, -70.2, 12.5], "facing": "south", "width": 26.0},
             {"kind": "text", "text": "PHASE 2", "at": [407.0, -70.2, 13.5], "facing": "south", "size": 7.0, "pixel": True}]
    # the bridge: the permit set gives only its outline; the deck at the clean floor, the roof and the doorways are ours
    out = next(e for e in permit.values() if e["key"] == "campus/B1")
    bx0, by0, _, bx1, by1, _ = out["box"]
    bridge = {"outline": {"key": "campus/B1", "box": out["box"]},
              "deck": [bx0 - 0.3, by0, 6.9, bx1 + 0.3, by1, 7.5], "roof_z": 13.0,
              "openings": [[bx0 - 0.4, -2.5, 7.45, bx0 + 0.1, 2.5, 11.0], [bx1 - 0.1, -2.5, 7.45, bx1 + 0.4, 2.5, 11.0]],
              "columns": [[x, y] for x in (bx0 + 12.0, bx1 - 12.0) for y in (by0 + 1.0, by1 - 1.0)]}
    return {"about": "The permit set's rooftop air units and curbs, chillers and transformers and the bridge's outline, "
                     "unchanged; roads, trees, exhaust stacks, signs and the bridge's deck, roof and doorways are ours, "
                     "assumed.",
            "permit": p, "bridge": bridge,
            "assumed": {"roads": roads, "trees": trees, "stacks": stacks, "signs": signs}}


def drone(building, ext, ent, shop_text):
    """The opening flight: timed keys {t, at, look, say?, label?} in plan metres (z up). The scene flies a Catmull-Rom
    curve through the points and eases the look between the look points; Lou's lines take their numbers from the data."""
    tools = len(building["tools"])
    fleet = next(int(l.split()[1]) for l in shop_text.splitlines() if l.startswith("fleet"))
    p1 = len({l[3] for l in building["labels"] if l[1] < 261.8})
    lot = ent["route"][0]["at"]
    eye = [lot[0] - 5.0, lot[1], 1.75]
    keys = [
        {"t": 0.0, "at": [-170.0, -40.0, 110.0], "look": [170.0, 0.0, 0.0],
         "say": "This is Fab Gym, a chip factory of our own design. It runs on the SMT2020 testbed, a public model of a "
                "full-size fab, and everything inside is simulated. It isn't a real fab."},
        {"t": 5.0, "at": [10.0, -152.0, 40.0], "look": [58.0, -110.0, 2.0], "label": "cinema",
         "say": "Down there, the cinema, for later."},
        {"t": 9.0, "at": [85.0, -128.0, 55.0], "look": [128.0, 0.0, 10.0], "label": "phase 1",
         "say": f"The long building is phase one, the front end: {p1} areas where the transistors are made."},
        {"t": 13.0, "at": [175.0, -120.0, 48.0], "look": [200.0, -165.0, 0.0], "label": "utility yard",
         "say": "Out back, the chillers and transformers that keep the whole fab cold and powered."},
        {"t": 17.0, "at": [285.0, -58.0, 42.0], "look": [285.0, 0.0, 12.0], "label": "bridge",
         "say": "The bridge joins the two phases. Lots headed for the copper wiring ride orange carriers, so copper never "
                "reaches the front-end tools."},
        {"t": 21.5, "at": [430.0, -95.0, 55.0], "look": [407.0, 0.0, 10.0], "label": "phase 2",
         "say": f"Phase two, the back end, lays down the copper. Altogether {tools:,} tools and {fleet} overhead "
                "vehicles, every one of them run by the simulator as you watch."},
        {"t": 25.5, "at": [540.0, 40.0, 65.0], "look": [250.0, 30.0, 0.0]},
        {"t": 29.0, "at": [120.0, 98.0, 58.0], "look": [-40.0, 31.0, 0.0],
         "say": "Now let's head down to the parking lot. I'll meet you there."},
        {"t": 32.5, "at": [-25.0, 46.0, 26.0], "look": [lot[0], lot[1], 1.5]},
        {"t": 34.0, "at": [-34.0, 38.0, 8.0], "look": [lot[0], lot[1], 1.5]},
        {"t": 35.0, "at": eye, "look": [lot[0], lot[1], 1.55], "label": "parking lot"},
    ]
    labels = {"cinema": [58.0, -110.0, 14.0], "utility yard": [179.0, -170.0, 10.0], "bridge": [285.8, 0.0, 22.0],
              "phase 2": [407.0, 0.0, 26.0], "phase 1": [127.9, 0.0, 26.0], "parking lot": [-51.0, 32.0, 8.0]}
    return {"keys": keys, "labels": labels}
