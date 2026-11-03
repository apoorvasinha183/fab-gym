"""Captions from the soundtrack's word times (docs/DRAWN-FILM.md, D10 and D11)."""

import re


def _norm(w):
    return re.sub(r"[^a-z0-9%.]+", "", w.lower().replace("’", "'")).strip(".")


def cues(lines, words):
    """Each caption line from its first word's start to its last word's end, matching the transcript word by word."""
    out, k = [], 0
    for line in lines:
        toks = [t for t in (_norm(x) for x in line.split()) if t]
        start = end = None
        for t in toks:
            j = k
            while j < len(words) and _norm(words[j]["word"]) != t:
                j += 1
            if j == len(words):
                continue
            if start is None:
                start = float(words[j]["start"])
            end = float(words[j]["end"])
            k = j + 1
        out.append({"from": start, "to": end, "text": line})
    return out


def _flat(s):
    return " ".join(s.replace("’", "'").replace("“", '"').replace("”", '"').split())


def not_in_script(captions, script):
    """The captions whose words are not in the script, as written."""
    flat = _flat(script)
    return [c for c in captions if _flat(c) not in flat]
