"""The direction of screenplay v3, written as code so timings follow shots.json and voice.json: every scene's
backgrounds (starting from its room), every drawing and each shot's exposure sheet. Run it to write
film/drawn/scenes/<n>.json; positions are first guesses from each room's measured ground, then set by eye after a
render (docs/FILM-PLAYBOOK.md, step 7)."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHOTS = {s["id"]: s for s in json.loads((ROOT / "film/drawn/shots.json").read_text())["shots"]}
LINES = json.loads((ROOT / "film/drawn/voice.json").read_text())["lines"]
ROOMS = json.loads((ROOT / "film/drawn/rooms.json").read_text())["rooms"]
ART = ROOT / "data/drawn/theatrical/scenes"
FPS = 24


def frames(sid):
    s = SHOTS[sid]
    return int(round((s["end"] - s["start"]) * FPS))


def seq(parts, total):
    """Drawings with weights, stretched to the shot's frames; the last takes the rounding."""
    w = sum(x[1] for x in parts)
    out, used = [], 0
    for i, (name, k) in enumerate(parts):
        n = total - used if i == len(parts) - 1 else max(2, int(round(total * k / w)))
        out.append([name, n])
        used += n
    return out


def talkseq(sid, who, before, key, after):
    """Before the line: `before`; on the line (and 6 frames after): `key`; then `after`."""
    s = SHOTS[sid]
    total = frames(sid)
    ls = [l for l in LINES if l["shot"] == sid and l["who"] == who]
    a = max(2, int((ls[0]["from"] - s["start"]) * FPS))
    b = min(total - 2, int((ls[-1]["to"] - s["start"]) * FPS) + 6)
    out = seq(before, a) if before else []
    if not before:
        b, a = b, 0
    out.append([key, b - a])
    out += seq(after, total - b) if after else []
    if not after:
        out[-1][1] += total - sum(x[1] for x in out)
    return out


def plate(name, n):
    return {"name": "plate", "plate": True, "depth": 0.5, "cels": [[name, n]]}


def plates(cels, dissolve=None):
    lv = {"name": "plate", "plate": True, "depth": 0.5, "cels": cels}
    if dissolve:
        lv["dissolve"] = dissolve
    return lv


def lv(name, h, cels, at=None, path=None, **kw):
    d = {"name": name, "depth": 0.2, "height": h, "cels": cels}
    d.update({"path": path} if path else {"at": at})
    d.update(kw)
    return d


def cam(n, z0=1.0, z1=1.0, x0=0, x1=0, y0=0, y1=0):
    return [[0, {"x": x0, "y": y0, "zoom": z0}], [n - 1, {"x": x1, "y": y1, "zoom": z1}]]


def shot(sid, levels, camera=None, **kw):
    n = frames(sid)
    d = {"id": sid, "start": SHOTS[sid]["start"], "frames": n, "levels": levels, "camera": camera or cam(n)}
    d.update(kw)
    return d


def room(k):
    return dict(ROOMS[str(k)])


def label(text, a, b, y=70):
    return {"text": text, "from": a, "to": b, "y": y, "size": 84}


def key(sheet, pose, **kw):
    return dict({"sheet": sheet, "pose": pose}, **kw)


def nxt(sheet, after, pose):
    return {"sheet": sheet, "kind": "next", "after": after, "pose": pose}


def btw(a, b):
    return {"kind": "between", "between": [a, b]}


SAND, QTZ, GREY, WISP, CRY, WAF, COACH, DIE, PKG, LOU, CARB = ("grain-01-sand", "grain-02-quartz", "grain-03-grey",
    "grain-04-wisp", "grain-05-crystal", "grain-06-wafer", "grain-07-coach", "grain-08-die", "grain-10-packaged",
    "lou-latency", "carbon-thieves")
XS = ("A simplified cross-section diagram for an animated film, side view, flat and clear: a thick slate-blue substrate "
      "filling the lower half with a flat top, plain soft pale light above, no labels")
S = {}

# 0 · a small beginning
n1, n2 = frames("0-1"), frames("0-2")
S[0] = {"plates": {"room": room(0),
                   "tip": {"prompt": "A close view of a giant fingertip holding a few big pale grains of sand against a quiet pale dawn sky, a calm empty band of sky across the top for a title.",
                           "stage": {"where": "on top of the fingertip in the middle", "share": "a quarter", "near": "the other grains on the fingertip are its own size"}}},
        "drawings": {"s_closed": key(SAND, "resting with eyes closed, curled small, calm"),
                     "s_open": nxt(SAND, "s_closed", "the same, eyes just opening, a slow blink"),
                     "s_tilt": key(SAND, "sitting up, head tilted, curious, looking up and off to the right", mouths=True),
                     "s_peer": key(SAND, "leaning forward over an edge on its tummy, peering down, brows up"),
                     "s_steady": key(SAND, "rising to its feet, arms out to steady itself, a little wobble"),
                     "s_look": key(SAND, "standing, a hand shading its eyes, looking out into the distance with growing interest")},
        "shots": [shot("0-1", [plate("room", n1), lv("grain", 260, talkseq("0-1", "grain", [["s_closed", 3], ["s_open", 2]], "s_tilt", []), at=[960, 975], talk={"key": "s_tilt", "who": "grain"})], cam(n1, 1.0, 1.12, 0, 0, 0, 20)),
                  shot("0-2", [plate("tip", n2), lv("grain", 270, seq([["s_peer", 4], ["s_steady", 3], ["s_look", 6]], n2), at=[960, 760])], cam(n2, 1.04, 1.0, 0, 0, 0, -20),
                       titles=[{"text": "From Sand to Chip", "from": int(n2 * 0.35), "to": n2, "y": 110}])]}

# 1 · meet the material
n1, n2, n3 = frames("1-1"), frames("1-2"), frames("1-3")
S[1] = {"plates": {"room": room(1),
                   "net": {"prompt": "A simplified diagram for an animated film: a connected network of pale silicon spheres and smaller red oxygen spheres joined by short bonds in a repeating pattern that runs past every edge, on a soft ochre ground, no labels"},
                   "netbig": {"prompt": "A simplified diagram filling the frame: a connected network of big pale silicon spheres and red oxygen spheres joined by short bonds in a repeating pattern running past every edge, soft ochre ground, a clear space in the front middle, no labels",
                              "stage": {"where": "in the front middle of the network", "share": "a third", "near": "the spheres around it are a little smaller than it"}}},
        "drawings": {"q_rock": key(QTZ, "without its companions: a pale quartz rock sitting still, eyes closed, as if part of the pile"),
                     "q_wake": nxt(QTZ, "q_rock", "without its companions: eyes opening, looking around, surprised to be moving"),
                     "q_ride": nxt(QTZ, "q_rock", "without its companions: sitting up, riding along, enjoying it, looking ahead to the right"),
                     "q_tap": key(QTZ, "without its companions: tapping its own side with one finger, puzzled, brows knitted", mouths=True),
                     "q_peek": nxt(QTZ, "q_tap", "without its companions: leaning toward its own side, peering closely, curious"),
                     "q_greet": key(QTZ, "the two small red twins greeting it, waving, all three delighted"),
                     "q_link": nxt(QTZ, "q_greet", "all three holding hands in a row, linked, smiling")},
        "shots": [shot("1-1", [plate("room", n1), lv("grain", 300, seq([["q_rock", 4], ["q_wake", 3], ["q_ride", 6]], n1), path=[[0, 900, 820], [n1 - 1, 1060, 820]])], cam(n1, 1.0, 1.0, 0, 160)),
                  shot("1-2", [plate("room", n2), lv("grain", 330, talkseq("1-2", "grain", [["q_ride", 1]], "q_tap", [["q_peek", 1]]), at=[880, 820], talk={"key": "q_tap", "who": "grain"})], cam(n2, 1.05, 1.1),
                       insets=[{"at": [1380, 420], "r": 250, "from": int(n2 * 0.45), "to": n2, "cels": [["net", n2]], "label": "simplified view"}]),
                  shot("1-3", [plate("netbig", n3), lv("grain", 380, seq([["q_greet", 5], ["q_link", 5]], n3), at=[960, 940])], cam(n3, 1.0, 1.06), view="simplified",
                       titles=[label("QUARTZ · SiO₂", int(n3 * 0.3), n3)])]}

# 2 · freeing the silicon (the tested furnace rim; the carbon purposeful, not sneaking)
n1, n2, n3 = frames("2-1"), frames("2-2"), frames("2-3")
d2 = json.loads((ROOT / "film/drawn/scenes/2.json").read_text())
keep = {k: v for k, v in d2["drawings"].items() if k.startswith(("tumble_", "land_", "Q_see", "Q_antic", "T_lead"))}
S[2] = {"plates": {"furnace": d2["plates"]["furnace"],
                   "imp": {"prompt": "A simplified diagram for an animated film: a cut-away block of grey silicon with small dark specks of other elements mixed all through its inside, on a soft charcoal ground, no labels"}},
        "drawings": dict(keep, **{
            "Q_brace": key(QTZ, "standing braced, feet planted, knees bent, the two red twins gripping its hands tightly, all three looking right"),
            "T_step": key(CARB, "both stepping forward side by side with purpose, polite and calm, each reaching out a hand toward the twins"),
            "T_offer": nxt(CARB, "T_step", "both standing with an open hand held out, calm friendly smiles, waiting"),
            "st_b": btw("T_step", "T_offer"),
            "Q_reach": key(QTZ, "reaching after the twins who are leaving up and to the right, one arm out, brows up"),
            "G_talk": key(GREY, "standing, giving a small wave up to the right, a little sad smile, mouth open speaking", mouths=True),
            "qg_b": btw("Q_reach", "G_talk"),
            "G_watch": key(GREY, "standing, watching up and to the right, hand lowered, thoughtful"),
            "T_rise_1": key(CARB, "each holding the hand of a small red twin, all rising up and away to the upper right as soft wisps of gas, the twins waving back"),
            "T_rise_2": nxt(CARB, "T_rise_1", "the same, higher and fainter, more wisp than body"),
            "G_turn": key(GREY, "looking down at its own grey body in surprise, hands held up in front of it, brows high"),
            "G_fleck": key(GREY, "frowning at a dark fleck on its arm, rubbing at it, finding it is inside, not on top"),
            "G_go": key(GREY, "stepping off to the right with determination, chin up")}),
        "shots": [shot("2-1", [plate("furnace", n1),
                               lv("grain", 290, seq([[f"tumble_{k}", 3] for k in range(1, 7)] + [["land_squash", 3], ["land_up", 4], ["land_settle", 3], ["Q_see", 10], ["Q_antic", 4], ["Q_brace", 40]], n1),
                                  path=[[0, 600, 470], [6, 680, 560], [12, 760, 700], [18, 880, 875], [n1 - 1, 880, 875]], noshadow=[f"tumble_{k}" for k in range(1, 7)]),
                               lv("carbon", 220, seq([["none", 30], ["T_step", 40], ["st_b", 3], ["T_offer", 50]], n1), at=[1480, 850])],
                       cam(n1, 1.0, 1.08, -30, 30, -20, 10), view="simplified"),
                  shot("2-2", [plate("furnace", n2),
                               lv("grain", 290, talkseq("2-2", "grain", [["Q_reach", 3], ["qg_b", 1]], "G_talk", [["G_watch", 1]]), at=[880, 875], talk={"key": "G_talk", "who": "grain"}),
                               lv("carbon", 230, seq([["T_rise_1", 5], ["T_rise_2", 4], ["none", 3]], n2), path=[[0, 1400, 830], [int(n2 * 0.75), 1720, 430], [n2 - 1, 1720, 430]], noshadow=["T_rise_1", "T_rise_2"])],
                       cam(n2, 1.08, 1.08, 30, 30, 10, -20), view="simplified"),
                  shot("2-3", [plate("furnace", n3),
                               lv("grain", 290, seq([["G_turn", 4], ["G_fleck", 3], ["G_go", 3]], n3), path=[[0, 880, 875], [int(n3 * 0.7), 880, 875], [n3 - 1, 1100, 875]])],
                       cam(n3, 1.1, 1.0, 0, 120),
                       insets=[{"at": [1430, 420], "r": 230, "from": int(n3 * 0.3), "to": int(n3 * 0.72), "cels": [["imp", n3]], "label": "simplified view"}])]}

# 3 · purity takes work
n1, n2, n3 = frames("3-1"), frames("3-2"), frames("3-3")
S[3] = {"plates": {"room": room(3),
                   "conv": {"prompt": "A simplified diagram for an animated film: grey silicon lumps in a vessel meeting a pale gas and turning into a soft violet vapour that rises, lilac ground, no labels"},
                   "column": {"prompt": "A clean cutaway of a tall glass distillation column in pale violet and warm white: violet vapour rising up the middle, pale liquid running back down the sides, three separate coloured streams leaving through pipes at different heights on the right",
                              "stage": {"where": "floating in the middle of the column", "share": "a third", "near": "the column's trays are drawn large beside it"}},
                   "rods": {"prompt": "A deposition chamber in muted steel blue and violet: a row of thin heated seed rods glowing orange-red standing upright, soft violet haze around them",
                            "stage": {"where": "in front of the middle rod", "share": "a third", "near": "the rods are a little taller than it"}},
                   "rods2": {"from": "rods", "prompt": "the rods are now much thicker, heavy grey silicon columns grown around each glowing core"},
                   "chunks": {"prompt": "Cooled grey silicon rods broken into rough chunks piled on a tray in soft steel-blue light",
                              "stage": {"where": "on top of the pile in the front middle", "share": "a third", "near": "the chunks are about its own size"}}},
        "drawings": {"G_in": key(GREY, "stepping forward into a soft violet glow, curious, a little nervous"),
                     "W_rise": key(WISP, "rising upward as a soft violet wisp, curious, arms out"),
                     "gw_b": btw("G_in", "W_rise"),
                     "W_follow": key(WISP, "floating up and to the right, eyes fixed on something ahead, intent"),
                     "W_pick": nxt(WISP, "W_follow", "pointing to the right with one arm, choosing the way, pleased"),
                     "W_settle": key(WISP, "drifting down, arms spread, settling gently"),
                     "R_stand": key(GREY, "standing tall and straight like a column, content, eyes half closed, arms at its sides"),
                     "wr_b": btw("W_settle", "R_stand"),
                     "C_chunk": key(GREY, "smaller and chipped like a rough chunk, sitting on a pile, cheerful, looking right")},
        "shots": [shot("3-1", [plate("room", n1), lv("grain", 330, seq([["G_in", 5], ["gw_b", 1], ["W_rise", 6]], n1), path=[[0, 760, 940], [int(n1 * 0.4), 820, 900], [n1 - 1, 900, 700]])], cam(n1, 1.0, 1.04, 0, 0, 0, -30),
                       insets=[{"at": [1450, 400], "r": 240, "from": int(n1 * 0.15), "to": int(n1 * 0.85), "cels": [["conv", n1]], "label": "simplified view"}]),
                  shot("3-2", [plate("column", n2), lv("grain", 320, seq([["W_follow", 6], ["W_pick", 5]], n2), path=[[0, 900, 900], [n2 - 1, 1150, 520]], noshadow=["W_follow", "W_pick"])], cam(n2, 1.0, 1.0, 0, 60, 30, -60), view="simplified",
                       titles=[label("DISTILLATION", int(n2 * 0.3), n2)]),
                  shot("3-3", [plates([["rods", int(n3 * 0.55)], ["rods2", int(n3 * 0.2)], ["chunks", n3 - int(n3 * 0.55) - int(n3 * 0.2)]], dissolve=14),
                               lv("grain", 330, seq([["W_settle", 4], ["wr_b", 1], ["R_stand", 5], ["C_chunk", 4]], n3), at=[960, 900], noshadow=["W_settle"])], cam(n3, 1.0, 1.05))]}

# 4 · growing one crystal
n1, n2, n3, n4 = frames("4-1"), frames("4-2"), frames("4-3"), frames("4-4")
S[4] = {"plates": {"room": room(4),
                   "pull": {"prompt": "A close view of a glowing crucible of white-orange melt in amber light with indigo shadows, a thin pull rod coming straight down from above, its tip holding a small plain silver seed crystal just above the middle of the melt",
                            "stage": {"where": "hanging below the seed, just above the melt", "share": "a third", "near": "the crucible's rim is drawn to its size"}},
                   "lattice": {"prompt": "A simplified diagram for an animated film: the lower third glowing orange liquid, above it an orderly schematic grid of silver atoms in neat rows continuing up from a seed at the top, a few loose atoms in the liquid moving up to join the grid at the boundary, no labels"},
                   "lattice2": {"from": "lattice", "prompt": "more loose atoms have joined and the ordered grid has grown a little further down into the liquid"},
                   "hall": {"prompt": "A tall crystal-pulling hall in amber and indigo light: a tall puller machine in the middle with its chamber opened wide and its pull cable hanging down empty in the middle of the opening, and far back on the right one small worker in a white clean-room suit",
                            "stage": {"where": "hanging from the cable in the open chamber", "share": "a half", "near": "the far worker is small with distance; the chamber is a little taller than it"}}},
        "drawings": {"M_down": key(CRY, "only a face showing in a glowing pool of melt, eyes closed, calm, no body"),
                     "M_up": nxt(CRY, "M_down", "the face in the melt opening its eyes and looking straight up, brows rising"),
                     "C_neck": key(CRY, "a short silver crystal just pulled up out of the melt, hanging from its top, its face forming, eyes wide, brows up"),
                     "C_mid": nxt(CRY, "C_neck", "the crystal longer now, turning slowly, hanging from its top, a wondering smile"),
                     "C_watch": key(CRY, "small, looking down at its own lower end with interest, hanging from its top"),
                     "C_long": key(CRY, "very long like a giant silver ingot, hanging from its top, looking down along its own long body, astonished, mouth open", mouths=True),
                     "C_proud": nxt(CRY, "C_long", "very long like a giant silver ingot, hanging from its top, a quiet proud smile")},
        "shots": [shot("4-1", [plate("room", n1), lv("grain", 170, seq([["M_down", 5], ["M_up", 5]], n1), at=[960, 910], noshadow=["M_down", "M_up"])], cam(n1, 1.0, 1.08, 0, 0, 0, 20)),
                  shot("4-2", [plate("pull", n2), lv("grain", 320, seq([["C_neck", 5], ["C_mid", 6]], n2), path=[[0, 960, 380], [n2 - 1, 960, 300]], anchor="top")], cam(n2, 1.0, 1.0, 0, 0, 0, -40)),
                  shot("4-3", [plates([["lattice", int(n3 * 0.5)], ["lattice2", n3 - int(n3 * 0.5)]], dissolve=24),
                               lv("grain", 260, [["C_watch", n3]], at=[300, 360], anchor="top")], cam(n3, 1.0, 1.04), view="simplified"),
                  shot("4-4", [plate("hall", n4), lv("grain", 560, talkseq("4-4", "grain", [], "C_long", [["C_proud", 1]]), at=[960, 260], anchor="top", talk={"key": "C_long", "who": "grain"})],
                       cam(n4, 1.15, 1.0, 0, 0, -40, 0), titles=[label("INGOT", int(n4 * 0.6), n4)])]}

# 5 · making the wafer
n1, n2, n3 = frames("5-1"), frames("5-2"), frames("5-3")
S[5] = {"plates": {"room": room(5),
                   "saw": {"prompt": "A wire saw in a cool pearl and steel-blue workshop: a long silver ingot lying supported in a cradle across the picture, a frame of fine glinting wires cutting through it into thin discs, the discs separating at the right end",
                           "stage": {"where": "at the right end where the discs separate", "share": "a third", "near": "each disc is its own size"}},
                   "edge": {"prompt": "A close view of an edge grinder in steel-blue light: a soft spinning wheel touching the rim of a thin round disc held on a small chuck", "stage": {"where": "on the chuck in the middle", "share": "a third", "near": "the wheel is about its own size"}},
                   "polish": {"prompt": "A close view of a soft round polishing pad in pearl light, one broad soft reflection across it", "stage": {"where": "on the pad in the middle", "share": "a third", "near": "the pad is wider than it"}},
                   "clean": {"prompt": "A close view of a rinse station: a gentle sheet of clean water falling over a small stand, pearl light", "stage": {"where": "on the stand in the middle", "share": "a third", "near": "the stand is its own size"}},
                   "carrier": {"prompt": "A loading station in pearl and steel-blue light: an open clear wafer carrier with slots on the right, thin shiny discs standing in most of them, one slot empty at the front",
                               "stage": {"where": "just in front of the empty slot", "share": "a third", "near": "each slot is its own size"}},
                   "carrier2": {"from": "carrier", "prompt": "the carrier's clear lid is now closed"}},
        "drawings": {"W_cut": key(WAF, "a thin round disc just separated, standing, surprised, looking at its own thinness"),
                     "W_spin": key(WAF, "standing on its edge, held steady, eyes squeezed, a little dizzy"),
                     "W_shine": key(WAF, "facing us, its surface mirror-bright with one broad soft reflection, delighted"),
                     "W_rinse": key(WAF, "eyes closed, water running off it, shaking off drops, pleased"),
                     "W_admire": key(WAF, "turning to inspect its own new smooth edge, pleased, one hand on its rim"),
                     "W_ask": key(WAF, "standing in front of a slot, hopeful brows raised, hands together, asking", mouths=True),
                     "W_nod": nxt(WAF, "W_ask", "a small understanding nod, a warm smile")},
        "shots": [shot("5-1", [plate("saw", n1), lv("grain", 290, [["W_cut", n1]], at=[1560, 860])], cam(n1, 1.0, 1.0, -60, 60)),
                  shot("5-2", [plates([["edge", int(n2 * 0.26)], ["polish", int(n2 * 0.26)], ["clean", int(n2 * 0.24)], ["polish", n2 - int(n2 * 0.26) * 2 - int(n2 * 0.24)]]),
                               lv("grain", 320, seq([["W_spin", 26], ["W_shine", 26], ["W_rinse", 24], ["W_admire", 24]], n2), at=[960, 900])], cam(n2, 1.04, 1.04),
                       cuts=[int(n2 * 0.26), int(n2 * 0.52), int(n2 * 0.76)]),
                  shot("5-3", [plates([["carrier", int(n3 * 0.82)], ["carrier2", n3 - int(n3 * 0.82)]]),
                               lv("grain", 300, talkseq("5-3", "grain", [], "W_ask", [["W_nod", 3], ["none", 2]]), at=[1350, 900], talk={"key": "W_ask", "who": "grain"})],
                       cam(n3, 1.0, 1.05, 0, 40), titles=[label("WAFER", int(n3 * 0.55), n3)])]}

# 6 · welcome to the fab
n1, n2 = frames("6-1"), frames("6-2")
S[6] = {"plates": {"room": room(6),
                   "dust": {"prompt": "A simplified diagram for an animated film: a huge rough grey dust particle sitting beside a tiny delicate circuit feature on a smooth wafer surface, close-up, no labels"}},
        "drawings": {"carrier": key(WAF, "seen through the clear front window of a closed wafer carrier box on a small cart: one wafer inside peeking out, eyes bright"),
                     "L_walk1": key(LOU, "walking beside something to its right, one hand resting on it, small precise steps"),
                     "L_walk2": nxt(LOU, "L_walk1", "the next step of the walk, the other foot forward"),
                     "L_check": key(LOU, "stopping to check a label on the box beside it, one finger raised, then speaking warmly", mouths=True),
                     "L_look": key(LOU, "turning its head to look at a panel on the wall, attentive"),
                     "L_stern": nxt(LOU, "L_look", "one eyebrow raised sternly at the panel, arms folded")},
        "shots": [shot("6-1", [plate("room", n1),
                               lv("box", 230, [["carrier", n1]], path=[[0, 500, 1000], [int(n1 * 0.4), 860, 1000], [n1 - 1, 860, 1000]]),
                               lv("lou", 540, talkseq("6-1", "lou", [["L_walk1", 1], ["L_walk2", 1]], "L_check", []), path=[[0, 760, 1010], [int(n1 * 0.4), 1120, 1010], [n1 - 1, 1120, 1010]], talk={"key": "L_check", "who": "lou"})],
                       cam(n1, 1.0, 1.0, 0, 60)),
                  shot("6-2", [plate("room", n2), lv("box", 230, [["carrier", n2]], path=[[0, 860, 1000], [int(n2 * 0.7), 860, 1000], [n2 - 1, 660, 1000]]),
                               lv("lou", 540, seq([["L_look", 3], ["L_stern", 5]], n2), at=[1120, 1010])], cam(n2, 1.0, 1.0),
                       insets=[{"at": [1450, 380], "r": 250, "from": int(n2 * 0.2), "to": int(n2 * 0.7), "cels": [["dust", n2]], "label": "simplified view"}],
                       titles=[label("FAB · CHIP FACTORY", int(n2 * 0.1), int(n2 * 0.6))])]}

# 7 · building the circuits (one cross-section, each step edited from the last so its colours keep their meaning)
f = {k: frames(f"7-{k}") for k in range(1, 9)}
xs = {"xs0": {"prompt": XS},
      "xs_film": {"from": "xs0", "prompt": "a thin even ochre film now covers the slate-blue substrate's whole top surface"},
      "xs_half": {"from": "xs0", "prompt": "a thin even ochre film has begun to cover the left half of the substrate's top surface"},
      "xs_res": {"from": "xs_film", "prompt": "a muted coral coating now covers the ochre film"},
      "xs_exp": {"from": "xs_res", "prompt": "a patterned mask hangs above with light shining through its gaps, and the coral coating under the gaps has turned paler"},
      "xs_dev": {"from": "xs_exp", "prompt": "the mask and light are gone and the paler parts of the coral coating have dissolved away, leaving openings down to the ochre film"},
      "xs_etch": {"from": "xs_dev", "prompt": "under each opening the ochre film has been removed down to the slate blue, the coral coating still protecting the rest"},
      "xs_strip": {"from": "xs_etch", "prompt": "the coral coating is gone, leaving the patterned ochre film on the slate-blue substrate"}}
S[7] = {"plates": dict({"room": room(7),
                        "dop": {"prompt": "A simplified diagram for an animated film: a slate-blue silicon block seen from the side, a framed region near its top where a stream of small bright green atoms enters only that region, no labels"},
                        "dop2": {"from": "dop", "prompt": "the green atoms now sit spread through that one region, the rest unchanged"},
                        "clean": {"prompt": "Inside a cleaning tool in blue-green light: a round wafer stage under a soft spray of clean water", "stage": {"where": "on the stage", "share": "a third", "near": "the stage is its own size"}},
                        "measure": {"prompt": "A measuring tool in blue-green light: a fine glowing measuring beam pointing down at a round wafer stage, a small readout", "stage": {"where": "on the stage", "share": "a third", "near": "the stage is its own size"}},
                        "route": {"prompt": "A calm clean room in blue-green light seen past a row of familiar process tools, a big clock face on the wall, an empty floor in front",
                                  "stage": {"where": "on the floor in the front right", "share": "a half", "near": "the tools are taller than it"}},
                        "circuit": {"prompt": "A simplified diagram for an animated film: an orderly simple circuit of a few transistors joined by neat ochre connection lines on a slate-blue ground, clear and calm, no labels"}}, **xs),
        "drawings": {"w_watch": key(WAF, "standing, watching something up and to the right with interest"),
                     "w_watch2": nxt(WAF, "w_watch", "the same, leaning a little closer, eyes wide"),
                     "w_lean": key(WAF, "leaning in close with real curiosity, a hand on its rim"),
                     "w_window": key(WAF, "small, seen through the round window of a process tool, looking out", mouths=True),
                     "L_clean": key(LOU, "watching a cleaning step closely, hands behind its back"),
                     "L_measure": key(LOU, "reading a small handheld gauge, focused"),
                     "L_ok": key(LOU, "checking a panel, then a small firm nod", mouths=True),
                     "L_route": key(LOU, "consulting a clipboard of the route, then speaking kindly", mouths=True),
                     "L_avatar": key(LOU, "holding up a small tablet that shows a tiny cheerful character wearing a red headband, Lou smiling down at it")},
        "shots": [shot("7-1", [plate("room", f[1]), lv("grain", 250, seq([["w_watch", 4], ["w_watch2", 5]], f[1]), at=[960, 700])], cam(f[1], 1.0, 1.05),
                       insets=[{"at": [1460, 420], "r": 270, "from": int(f[1] * 0.15), "to": f[1], "cels": [["xs0", int(f[1] * 0.3)], ["xs_half", int(f[1] * 0.25)], ["xs_film", f[1]]], "label": "simplified view"}],
                       titles=[label("DEPOSITION", int(f[1] * 0.4), f[1])]),
                  shot("7-2", [plate("room", f[2]), lv("grain", 250, [["w_watch2", f[2]]], at=[960, 700])], cam(f[2], 1.05, 1.05),
                       insets=[{"at": [1460, 420], "r": 270, "from": 0, "to": f[2], "cels": [["xs_film", int(f[2] * 0.3)], ["xs_res", f[2]]], "label": "simplified view"}],
                       titles=[label("PHOTORESIST", int(f[2] * 0.3), f[2])]),
                  shot("7-3", [plate("room", f[3]), lv("grain", 250, [["w_watch", f[3]]], at=[960, 700])], cam(f[3], 1.05, 1.05),
                       insets=[{"at": [1460, 420], "r": 270, "from": 0, "to": f[3], "cels": [["xs_res", int(f[3] * 0.2)], ["xs_exp", int(f[3] * 0.4)], ["xs_dev", f[3]]], "label": "simplified view"}],
                       titles=[label("LITHOGRAPHY", int(f[3] * 0.2), f[3])]),
                  shot("7-4", [plate("room", f[4]), lv("grain", 250, [["w_watch2", f[4]]], at=[960, 700])], cam(f[4], 1.05, 1.05),
                       insets=[{"at": [1460, 420], "r": 270, "from": 0, "to": f[4], "cels": [["xs_dev", int(f[4] * 0.2)], ["xs_etch", int(f[4] * 0.45)], ["xs_strip", f[4]]], "label": "simplified view"}],
                       titles=[label("ETCHING", int(f[4] * 0.2), f[4])]),
                  shot("7-5", [plate("room", f[5]), lv("grain", 250, seq([["w_watch", 3], ["w_lean", 6]], f[5]), at=[960, 700])], cam(f[5], 1.05, 1.1),
                       insets=[{"at": [1460, 420], "r": 270, "from": int(f[5] * 0.1), "to": f[5], "cels": [["dop", int(f[5] * 0.45)], ["dop2", f[5]]], "label": "simplified view"}],
                       titles=[label("DOPING", int(f[5] * 0.3), f[5])]),
                  shot("7-6", [plates([["clean", int(f[6] * 0.3)], ["measure", int(f[6] * 0.3)], ["route", f[6] - int(f[6] * 0.3) * 2]]),
                               lv("lou", 520, talkseq("7-6", "lou", [], "L_ok", []), at=[1350, 1010], talk={"key": "L_ok", "who": "lou"})],
                       cam(f[6], 1.0, 1.0), cuts=[int(f[6] * 0.3), int(f[6] * 0.6)]),
                  shot("7-7", [plates([["room", int(f[7] * 0.35)], ["route", f[7] - int(f[7] * 0.35)]], dissolve=12),
                               lv("grain", 200, talkseq("7-7", "grain", [], "w_window", []), at=[700, 640], talk={"key": "w_window", "who": "grain"}),
                               lv("lou", 520, talkseq("7-7", "lou", [["none", 1]], "L_route", []), at=[1380, 1010], talk={"key": "L_route", "who": "lou"})],
                       cam(f[7], 1.0, 1.0, 0, 40)),
                  shot("7-8", [plate("route", f[8]), lv("lou", 520, [["L_avatar", f[8]]], at=[1380, 1010])], cam(f[8], 1.0, 1.06),
                       insets=[{"at": [620, 420], "r": 280, "from": 0, "to": f[8], "cels": [["circuit", f[8]]], "label": "simplified view"}])]}

# 8 · many chips, one wafer
n1, n2 = frames("8-1"), frames("8-2")
S[8] = {"plates": {"room": {"prompt": "A calm wafer inspection station under restrained white light: a round wafer covered in a neat grid of small square dies lies on a dark stage, soft light from above, the rest of the room quiet and dim",
                            "stage": {"where": "on the stage in front of the wafer", "share": "a third", "near": "one die of the grid is a little smaller than it"}},
                   "transistor": {"prompt": "A simplified diagram for an animated film: a single switch-like transistor on a simple path, a signal of little light dots stopped at its closed gate, slate-blue and ochre, no labels"},
                   "transistor2": {"from": "transistor", "prompt": "the gate is open and the little dots of light flow through"},
                   "transistor3": {"from": "transistor2", "prompt": "several more transistors in a row pass the dots of light along a simple path"}},
        "drawings": {"w_whole": key(WAF, "standing proudly in front of a gridded wafer, arms out, presenting it"),
                     "d_one": key(DIE, "a single small square die, stepping forward out of a neat grid, the only one with a face, pleased"),
                     "wd_b": btw("w_whole", "d_one"),
                     "d_watch": key(DIE, "small, looking up and to the right with interest")},
        "shots": [shot("8-1", [plate("room", n1), lv("grain", 300, seq([["w_whole", 5], ["wd_b", 1], ["d_one", 5]], n1), at=[960, 930])], cam(n1, 1.0, 1.06),
                       titles=[label("DIE", int(n1 * 0.55), n1)]),
                  shot("8-2", [plates([["transistor", int(n2 * 0.35)], ["transistor2", int(n2 * 0.3)], ["transistor3", n2 - int(n2 * 0.35) - int(n2 * 0.3)]], dissolve=10),
                               lv("grain", 220, [["d_watch", n2]], at=[260, 1000])], cam(n2, 1.0, 1.05), view="simplified",
                       titles=[label("TRANSISTOR", int(n2 * 0.3), n2)])]}

# 9 · does it work?
n1, n2 = frames("9-1"), frames("9-2")
S[9] = {"plates": {"room": room(9),
                   "touch": {"from": "room", "prompt": "the fine probe needles have come down and touch only the small pads around the edges of the front die"},
                   "map": {"prompt": "A test map for an animated film: a round wafer drawn as a grid of small squares, most of them green, a few red, one square in the middle outlined brightly, no labels"}},
        "drawings": {"d_up": key(DIE, "looking up at something coming down from above, drawing in a breath"),
                     "d_hold": nxt(DIE, "d_up", "holding very still, cheeks puffed, holding its breath, eyes squeezed"),
                     "d_ask": key(DIE, "looking off to the right, hopeful and nervous, asking", mouths=True),
                     "d_relief": nxt(DIE, "d_ask", "shoulders dropping in relief, a big relieved smile, a small green glow")},
        "shots": [shot("9-1", [plates([["room", int(n1 * 0.55)], ["touch", n1 - int(n1 * 0.55)]]), lv("grain", 300, seq([["d_up", 5], ["d_hold", 5]], n1), at=[960, 930])], cam(n1, 1.0, 1.05)),
                  shot("9-2", [plate("touch", n2), lv("grain", 300, talkseq("9-2", "grain", [], "d_ask", [["d_relief", 1]]), at=[760, 930], talk={"key": "d_ask", "who": "grain"})], cam(n2, 1.05, 1.05),
                       insets=[{"at": [1450, 400], "r": 250, "from": int(n2 * 0.1), "to": n2, "cels": [["map", n2]], "label": "test map"}])]}

# 10 · going separate ways
n1, n2 = frames("10-1"), frames("10-2")
S[10] = {"plates": {"room": room(10),
                    "lift": {"prompt": "A close view in cool slate light: the soft suction tip of a pick-up tool coming down from above over a single small die in a neatly cut grid, the wafer held flat",
                             "stage": {"where": "on the front die under the tip", "share": "a third", "near": "the neighbouring dies are its own size"}}},
         "drawings": {"d_lane": key(DIE, "watching a cut run along the lane beside it, leaning away a little, eyes on it"),
                      "d_free": key(DIE, "standing alone in its own square, cut free, looking around, a little amazed"),
                      "d_back": key(DIE, "lifted up from its top, looking back down at the grid below"),
                      "d_squash": key(DIE, "squashed down a little, bracing as something takes hold of its top"),
                      "d_ahead": key(DIE, "lifted from its top, looking ahead to the right, asking, curious", mouths=True)},
         "shots": [shot("10-1", [plate("room", n1), lv("grain", 300, seq([["d_lane", 6], ["d_free", 4]], n1), at=[960, 960])], cam(n1, 1.0, 1.04)),
                   shot("10-2", [plate("lift", n2), lv("grain", 300, talkseq("10-2", "grain", [["d_squash", 1], ["d_back", 3]], "d_ahead", []), path=[[0, 960, 640], [int(n2 * 0.2), 960, 640], [int(n2 * 0.45), 960, 560], [n2 - 1, 1080, 540]], anchor="top", talk={"key": "d_ahead", "who": "grain"})],
                        cam(n2, 1.0, 1.0, 0, 60))]}

# 11 · a connection to the world
n1, n2 = frames("11-1"), frames("11-2")
S[11] = {"plates": {"room": room(11),
                    "bond": {"prompt": "A simplified close-up for an animated film: a small square die seated on a green package substrate, fine gold wires arching from pads on the die to pads on the substrate, warm cream and muted gold, no labels"},
                    "closed": {"from": "room", "prompt": "the black protective lid now sits closed over the substrate"}},
         "drawings": {"d_seat": key(DIE, "settling down gently into place, knees bending, careful"),
                      "d_set": nxt(DIE, "d_seat", "seated, looking at fine gold wires arching from its edges, pleased"),
                      "p_eyes": key(PKG, "a black package with its eyes opening on top, hopeful, a small gesture", mouths=True),
                      "dp_b": btw("d_set", "p_eyes")},
         "shots": [shot("11-1", [plate("room", n1), lv("grain", 230, seq([["d_seat", 4], ["d_set", 6]], n1), at=[780, 850])], cam(n1, 1.0, 1.06),
                        insets=[{"at": [1450, 380], "r": 250, "from": int(n1 * 0.35), "to": n1, "cels": [["bond", n1]], "label": "simplified view"}],
                        titles=[label("PACKAGE", int(n1 * 0.5), n1)]),
                   shot("11-2", [plates([["room", int(n2 * 0.3)], ["closed", n2 - int(n2 * 0.3)]]), lv("grain", 250, talkseq("11-2", "grain", [["d_set", 3], ["dp_b", 1]], "p_eyes", []), at=[780, 850], talk={"key": "p_eyes", "who": "grain"})], cam(n2, 1.06, 1.06))]}

# 12 · something useful
n1, n2 = frames("12-1"), frames("12-2")
S[12] = {"plates": {"room": room(12),
                    "awake": {"from": "room", "prompt": "the phone's screen has woken and glows softly with warm light"},
                    "socket": {"prompt": "A final test socket in warm light: a small black chip seated in it, a small green pass light beside it", "stage": {"where": "in the socket", "share": "a quarter", "near": "the socket is its own size"}},
                    "board": {"prompt": "A green circuit board in warm light with one small black chip soldered in place among other parts", "stage": {"where": "in its place on the board", "share": "a quarter", "near": "the other parts are its own size"}},
                    "phone": {"prompt": "A circuit board being closed inside a smartphone's case, warm light"}},
         "drawings": {"p_test": key(PKG, "seated, hopeful, waiting"),
                      "p_pass": nxt(PKG, "p_test", "relieved, a small happy bounce"),
                      "p_board": key(PKG, "in its place among other parts, settling in, content"),
                      "a_tilt": key(SAND, "a tiny glowing figure on a phone screen tilting its head, curious and warm", mouths=True)},
         "shots": [shot("12-1", [plates([["socket", int(n1 * 0.35)], ["board", int(n1 * 0.4)], ["phone", n1 - int(n1 * 0.35) - int(n1 * 0.4)]], dissolve=10),
                                 lv("grain", 230, seq([["p_test", 3], ["p_pass", 3], ["p_board", 4], ["none", 2]], n1), at=[960, 760])], cam(n1, 1.0, 1.04)),
                   shot("12-2", [plates([["room", int(n2 * 0.25)], ["awake", n2 - int(n2 * 0.25)]], dissolve=12),
                                 lv("grain", 200, talkseq("12-2", "grain", [["none", 3]], "a_tilt", []), at=[1100, 790], talk={"key": "a_tilt", "who": "grain"}, noshadow=["a_tilt"])],
                        cam(n2, 1.1, 1.0, 0, 0, 0, -20),
                        titles=[label("QUARTZ → SILICON → CRYSTAL → WAFER → CHIPS", int(n2 * 0.62), n2, 90)])]}

if __name__ == "__main__":
    for n, sc in S.items():
        sc = dict(sc, scene=str(n))
        for sh in sc["shots"]:
            for l in sh["levels"]:
                if not l.get("plate"):
                    assert sum(c[1] for c in l["cels"]) == sh["frames"], (sh["id"], l["name"], sum(c[1] for c in l["cels"]), sh["frames"])
        (ROOT / f"film/drawn/scenes/{n}.json").write_text(json.dumps(sc, indent=1, ensure_ascii=False))
        # each scene's room is the room already painted at the character's scale
        out = ART / str(n)
        out.mkdir(parents=True, exist_ok=True)
        src = ROOT / f"data/drawn/theatrical/rooms/{n}.png"
        if "room" in sc["plates"] and n != 8 and src.exists() and not (out / "room.png").exists():
            shutil.copy2(src, out / "room.png")
        print(n, len(sc["shots"]), "shots")
