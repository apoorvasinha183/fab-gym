"""Sketch to fab (docs/SKETCH.md): Muse Spark reads a photo of a fab drawn on paper (boxes for machines, lines for
track), and this module snaps what it read onto the editor's grid. The page then builds it with the editor's own moves,
and the checks say what is missing. On a teaching fab of our own; not a real fab."""

import json
import re
import statistics

MODEL = "muse-spark-1.3-contributor"
AREAS = ["litho", "lithomet", "dry", "wet", "diff", "diel", "tf", "tfmet", "imp", "cmp", "defmet"]
KINDS = AREAS + ["stocker", "entry", "exit"]
# words a person might write in a box, in the order they are tried (longer phrases first)
WORDS = [("litho met", "lithomet"), ("overlay", "lithomet"), ("metrology", "lithomet"), ("film met", "tfmet"),
         ("thickness", "tfmet"), ("thin film", "tf"), ("dry etch", "dry"), ("wet etch", "wet"), ("defect", "defmet"),
         ("inspect", "defmet"), ("litho", "litho"), ("photo", "litho"), ("expos", "litho"), ("etch", "dry"),
         ("clean", "wet"), ("wet", "wet"), ("diffusion", "diff"), ("furnace", "diff"), ("oxide", "diel"), ("dielectric", "diel"),
         ("cvd", "diel"), ("metal", "tf"), ("pvd", "tf"), ("implant", "imp"), ("cmp", "cmp"), ("polish", "cmp"),
         ("storage", "stocker"), ("stocker", "stocker"), ("store", "stocker"), ("wafers in", "entry"), ("start", "entry"),
         ("wafers out", "exit"), ("exit", "exit"), ("end", "exit"), ("in", "entry"), ("out", "exit")]
NAMES = {"litho": "Lithography", "lithomet": "Litho metrology", "dry": "Dry etch", "wet": "Wet etch and clean", "diff": "Diffusion",
         "diel": "Dielectric", "tf": "Thin film", "tfmet": "Thin film metrology", "imp": "Ion implant", "cmp": "Polishing",
         "defmet": "Defect inspection", "stocker": "Storage", "entry": "Wafers in", "exit": "Wafers out"}

PROMPT = """This is a photo of a chip fab's floor plan drawn on paper. Boxes are pieces; lines are track that cars run on;
an arrow on a line shows which way the track runs. Each box has a word written in it. Say which piece each box is:
one of litho (lithography), lithomet (litho metrology), dry (dry etch), wet (wet etch and clean), diff (diffusion),
diel (dielectric), tf (thin film), tfmet (thin film metrology), imp (ion implant), cmp (polishing), defmet (defect
inspection), stocker (storage), entry (wafers in), exit (wafers out), or "" if the word names none of them.
Give pixel positions in the picture as it is ({w} by {h} pixels). List every line's corners in order, following its
arrow when one is drawn. Reply with JSON only:
{{"boxes": [{{"box": [x1, y1, x2, y2], "word": "the word written", "kind": "one of the kinds"}}],
 "lines": [[[x, y], [x, y], ...]]}}"""


def footprint(kind):
    return (1, 2) if kind in ("entry", "exit") else (2, 2)


def kind_of(kind, word):
    """The piece a box is: its kind when that is one we know, else the first piece its word names, else None."""
    if kind in KINDS:
        return kind
    w = " ".join(str(word or "").lower().split())
    for phrase, k in WORDS:
        if re.search(rf"\b{re.escape(phrase)}", w):
            return k
    return None


def manhattan(corners):
    """Neighbouring tiles from corner to corner: across first, then up or down."""
    out = []
    for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
        x, y = x0, y0
        if not out:
            out.append([x, y])
        while x != x1:
            x += 1 if x1 > x else -1
            out.append([x, y])
        while y != y1:
            y += 1 if y1 > y else -1
            out.append([x, y])
    if not out and corners:
        out.append(list(corners[0]))
    return out


def read(text):
    """Spark's reply as {"boxes": [...], "lines": [...]}, or an empty reading."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        d = {}
    return {"boxes": d.get("boxes") or [], "lines": d.get("lines") or []}


def to_fab(reading):
    """Pieces and track on the editor's grid, the floor's size, and notes on what was left out."""
    notes, boxes = [], []
    for b in reading.get("boxes", []):
        try:
            x1, y1, x2, y2 = [float(v) for v in b["box"]]
        except (KeyError, TypeError, ValueError):
            continue
        k = kind_of(b.get("kind"), b.get("word"))
        word = str(b.get("word") or "").strip()
        if k is None:
            notes.append(f'A box reading "{word or "?"}" names no piece we know, so it was left out.')
            continue
        boxes.append((k, word, min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
    widths = [x2 - x1 for _, _, x1, _, x2, _ in boxes if x2 > x1]
    cell = statistics.median(widths) / 2 if widths else 40.0
    pieces = []
    for k, word, x1, y1, x2, y2 in boxes:
        w, h = footprint(k)
        pieces.append({"piece": k, "word": word, "x": round((x1 + x2) / 2 / cell - w / 2), "y": round((y1 + y2) / 2 / cell - h / 2), "w": w, "h": h})
    paths = []
    for line in reading.get("lines", []):
        try:
            corners = [[int((float(p[0])) // cell), int((float(p[1])) // cell)] for p in line]
        except (TypeError, ValueError, IndexError):
            continue
        paths.append(manhattan(corners))
    # a margin of one tile all round
    xs = [p["x"] for p in pieces] + [c[0] for path in paths for c in path]
    ys = [p["y"] for p in pieces] + [c[1] for path in paths for c in path]
    dx, dy = (1 - min(xs), 1 - min(ys)) if xs else (1, 1)
    for p in pieces:
        p["x"] += dx
        p["y"] += dy
    paths = [[[c[0] + dx, c[1] + dy] for c in path] for path in paths]
    taken = {(p["x"] + i, p["y"] + j) for p in pieces for i in range(p["w"]) for j in range(p["h"])}
    def touches(c):
        x, y = c
        return any((x + i, y + j) in taken for i, j in ((1, 0), (-1, 0), (0, 1), (0, -1)))

    split = []
    for n, path in enumerate(paths):
        others = {tuple(c) for m, q in enumerate(paths) if m != n for c in q}
        runs, run = [], []
        for c in path:
            if tuple(c) in taken:
                if run:
                    runs.append(run)
                run = []
            else:
                run.append(c)
        if run:
            runs.append(run)
        # spurs: the stretch between a machine and the nearest crossing of other track. Cars must come back out
        # the way they went in, so a spur is laid there and back, starting and ending on the other track.
        if runs:
            first, last = runs[0], runs[-1]
            on = [k for k, c in enumerate(first) if tuple(c) in others]
            head = touches(first[0]) and on and on[0] > 0
            on = [k for k, c in enumerate(last) if tuple(c) in others]
            tail = touches(last[-1]) and on and on[-1] < len(last) - 1
            i = on[-1] if tail else None
            if head:
                j = [k for k, c in enumerate(first) if tuple(c) in others][0]
                runs[0] = first[j::-1] + first[1:]
            if tail:
                runs[-1] = runs[-1] + last[i:-1][::-1]
        split.extend(runs)
    W = max([p["x"] + p["w"] for p in pieces] + [c[0] + 1 for path in split for c in path] + [4]) + 1
    H = max([p["y"] + p["h"] for p in pieces] + [c[1] + 1 for path in split for c in path] + [4]) + 1
    return {"floor": [W, H], "pieces": pieces, "paths": split, "notes": notes, "names": NAMES}
