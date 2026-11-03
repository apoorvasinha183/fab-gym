"""Mouths on the lines (docs/ART-DIRECTION.md, decided 3 Nov): eight mouth shapes, as the old studios timed dialogue on
exposure sheets. A line's letters become shapes spread evenly over its time, each held at least two frames (on twos);
outside its lines the character keeps its own drawing. Timing comes from voice.json, so it follows the recordings once
their times are in.
"""

FPS = 24

SHAPES = {
    "rest": "lips closed, relaxed (for M, B and P)",
    "ah": "mouth wide open, jaw dropped, tongue low (for A and I)",
    "ee": "mouth wide and stretched sideways, teeth showing (for E)",
    "oh": "mouth a round open O (for O)",
    "oo": "lips pushed forward in a small round pucker (for U, W and Q)",
    "ff": "top teeth resting on the lower lip (for F and V)",
    "ll": "mouth half open, the tip of the tongue up behind the top teeth (for L, T, D, N and TH)",
    "ss": "teeth nearly together, lips parted (for S, Z, C, K, G, R, H, J, X and Y)",
}

LETTER = {**{c: "ah" for c in "ai"}, "e": "ee", "o": "oh", **{c: "oo" for c in "uwq"}, **{c: "ff" for c in "fv"},
          **{c: "ll" for c in "ltdn"}, **{c: "rest" for c in "mbp"}, **{c: "ss" for c in "szckgrhjxy"}}


def shapes(text):
    """The mouth shapes of a line, in order, with repeats merged; 'th' is one tongue shape."""
    out = []
    t = text.lower().replace("th", "l")
    for ch in t:
        s = LETTER.get(ch)
        if s and (not out or out[-1] != s):
            out.append(s)
        elif ch in " ,.!?;:" and out and out[-1] != "rest" and ch != " ":
            out.append("rest")
    return out or ["rest"]


def frames(text, start, end, hold=2):
    """One shape per frame from start to end (frames), each shape held at least `hold` frames: when a line has more
    shapes than its time allows, every other shape is dropped until they fit."""
    n = max(1, end - start)
    seq = shapes(text)
    while len(seq) * hold > n and len(seq) > 1:
        seq = seq[::2]
    per = n / len(seq)
    return [seq[min(len(seq) - 1, int(k / per))] for k in range(n)]


def talk(cels, key, lines, shot_start, who):
    """A level's exposure sheet with `key`'s frames inside `who`'s lines replaced by `key@shape` drawings."""
    seq = [name for name, k in cels for _ in range(int(k))]
    for ln in lines:
        if ln["who"] != who:
            continue
        a = int(round((float(ln["from"]) - shot_start) * FPS))
        b = int(round((float(ln["to"]) - shot_start) * FPS))
        a, b = max(0, a), min(len(seq), b)
        if b <= a:
            continue
        for f, s in zip(range(a, b), frames(ln["text"], a, b)):
            if seq[f] == key:
                seq[f] = f"{key}@{s}"
    out = []
    for name in seq:
        if out and out[-1][0] == name:
            out[-1][1] += 1
        else:
            out.append([name, 1])
    return out
