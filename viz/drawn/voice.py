"""The drawn film's voice-over (docs/DRAWN-FILM.md, V1 to V3): each line sits inside its shot at a speaking pace, the
narrator's numbers are the script's, and Grain and Lou say little."""

import re

PACE = {"narrator": 2.8, "grain": 3.2, "lou": 3.2}       # words a second, at most (assumed comfortable)


def check(lines, shots):
    by = {s["id"]: s for s in shots}
    errs = []
    for ln in lines:
        s = by.get(str(ln["shot"]))
        if not s:
            errs.append(f"line {ln['text'][:40]!r}: no shot {ln['shot']}")
            continue
        a, b = float(ln["from"]), float(ln["to"])
        if b <= a:
            errs.append(f"line {ln['text'][:40]!r} ends before it starts")
            continue
        if a < float(s["start"]) - 0.01 or b > float(s["end"]) + 0.01:
            errs.append(f"line {ln['text'][:40]!r} runs outside shot {s['id']} ({s['start']} to {s['end']} s)")
        n = len(ln["text"].split())
        pace = PACE.get(ln["who"], 2.8)
        if n / (b - a) > pace:
            errs.append(f"line {ln['text'][:40]!r}: {n / (b - a):.1f} words a second, over {pace}")
    return errs


def numbers_not_in_script(texts, script):
    flat = script.replace(" ", " ")
    out = []
    for t in texts:
        for num in re.findall(r"\d[\d,]*(?:\.\d+)?", t):
            num = num.rstrip(",.")
            if num not in flat:
                out.append(num)
    return out


def cast_limits(lines):
    errs = []
    grain = [ln for ln in lines if ln["who"] == "grain"]
    lou = [ln for ln in lines if ln["who"] == "lou"]
    if len(grain) > 8:
        errs.append(f"Grain has {len(grain)} lines, at most 8")
    for ln in grain:
        if len(ln["text"].split()) > 8:
            errs.append(f"Grain's line {ln['text'][:40]!r} is over 8 words")
    if not 1 <= len(lou) <= 2:
        errs.append(f"Lou has {len(lou)} lines, 1 or 2 wanted")
    return errs
