"""The drawn film's score (docs/DRAWN-FILM.md, M1 to M5): tempo chosen so hit points fall on beats, checks on every
part, and each cue as MusicXML for MuseScore to print and play. Notes are given at concert pitch as [pitch, beats]:
"D5", "C#4", "Bb3", "r" for a rest, "C4+E4+G4" for a chord. Standard library only."""

import math
import re
import xml.etree.ElementTree as ET

# concert ranges (MIDI numbers), the usual orchestral ranges
RANGES = {"Piccolo": (74, 108), "Flute": (60, 96), "Oboe": (58, 91), "Clarinet in B♭": (50, 91), "Bassoon": (34, 75),
          "Horn in F": (34, 77), "Trumpet in B♭": (52, 82), "Trombone": (40, 72), "Tuba": (28, 65),
          "Timpani": (40, 57), "Glockenspiel": (79, 108), "Xylophone": (65, 108), "Celesta": (60, 108), "Harp": (23, 103),
          "Violin I": (55, 100), "Violin II": (55, 100), "Viola": (48, 88), "Violoncello": (36, 76), "Contrabass": (28, 67)}
FAMILIES = {"strings": ["Violin I", "Violin II", "Viola", "Violoncello", "Contrabass"],
            "woodwinds": ["Piccolo", "Flute", "Oboe", "Clarinet in B♭", "Bassoon"],
            "brass": ["Horn in F", "Trumpet in B♭", "Trombone", "Tuba"],
            "percussion": ["Timpani", "Glockenspiel", "Xylophone"],
            "harp": ["Harp", "Celesta"]}
CLEF = {"Bassoon": ("F", 4), "Trombone": ("F", 4), "Tuba": ("F", 4), "Timpani": ("F", 4), "Violoncello": ("F", 4),
        "Contrabass": ("F", 4), "Viola": ("C", 3)}
TRANSPOSE = {"Clarinet in B♭": (-1, -2), "Trumpet in B♭": (-1, -2), "Horn in F": (-4, -7),
             "Contrabass": (0, -12), "Piccolo": (0, 12), "Glockenspiel": (0, 24), "Xylophone": (0, 12), "Celesta": (0, 12)}
MIDI_PROGRAM = {"Piccolo": 73, "Flute": 74, "Oboe": 69, "Clarinet in B♭": 72, "Bassoon": 71, "Horn in F": 61,
                "Trumpet in B♭": 57, "Trombone": 58, "Tuba": 59, "Timpani": 48, "Glockenspiel": 10, "Xylophone": 14,
                "Celesta": 9, "Harp": 47, "Violin I": 41, "Violin II": 41, "Viola": 42, "Violoncello": 43, "Contrabass": 44}
STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
MAJOR_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7, "F": -1, "Bb": -2, "Eb": -3, "Ab": -4,
                "Db": -5, "Gb": -6, "Cb": -7}
FRAME = 1.0 / 24


def midi(p):
    m = re.fullmatch(r"([A-Ga-g])([#b♭♯]*)(-?\d)", p.strip())
    if not m:
        raise ValueError(f"not a pitch: {p}")
    alt = m.group(2).count("#") + m.group(2).count("♯") - m.group(2).count("b") - m.group(2).count("♭")
    return 12 * (int(m.group(3)) + 1) + STEPS[m.group(1).upper()] + alt


def name(n, flats=False):
    sharp = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    flat = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    return (flat if flats else sharp)[n % 12] + str(n // 12 - 1)


def canon(inst):
    """An instrument's name as the orchestra list spells it: "Clarinet in Bb" and "Clarinet in B-flat" are the B-flat
    clarinet; case and spacing do not matter."""
    k = " ".join(str(inst).replace("B-flat", "B\u266d").replace("Bb", "B\u266d").split()).lower()
    for name in RANGES:
        if name.lower() == k:
            return name
    aliases = {"violin 1": "Violin I", "violin 2": "Violin II", "cello": "Violoncello", "double bass": "Contrabass",
               "bass": "Contrabass", "french horn": "Horn in F", "horn": "Horn in F", "clarinet": "Clarinet in B\u266d",
               "trumpet": "Trumpet in B\u266d", "timpani": "Timpani", "glock": "Glockenspiel"}
    return aliases.get(k, inst)


def beats_per_bar(meter):
    return meter[0] * 4.0 / meter[1]


# ------------------------------------------------------------------ tempo

def hit_errors(start, hits, tempo):
    beat = 60.0 / tempo
    return [abs(start + round((h - start) / beat) * beat - h) for h in hits]


def fit_tempo(start, hits, lo=60, hi=160, prefer=100):
    """The tempo (to 0.1 beats a minute) whose beats come nearest every hit point, within a frame if any can; among
    those within a frame, the one nearest `prefer`."""
    best, ok = None, []
    for k in range(int(lo * 10), int(hi * 10) + 1):
        t = k / 10.0
        e = max(hit_errors(start, hits, t)) if hits else 0.0
        if e <= FRAME:
            ok.append(t)
        if best is None or e < best[0]:
            best = (e, t)
    return min(ok, key=lambda t: abs(t - prefer)) if ok else best[1]


def check_hits(start, hits, tempo):
    return [f"hit at {h:.2f} s is {e:.3f} s off the beat at {tempo} a minute"
            for h, e in zip(hits, hit_errors(start, hits, tempo)) if e > FRAME]


# ------------------------------------------------------------------ checks

def _notes(part):
    for item in part:
        p, d = item[0], float(item[1])
        yield p, d


def check(c):
    """Everything wrong with a cue, as sentences (M2, M3)."""
    errs = []
    bpb = beats_per_bar(c.get("meter", [4, 4]))
    totals = {}
    for inst, part in c["parts"].items():
        if inst not in RANGES:
            errs.append(f"{inst}: not an instrument of the orchestra")
            continue
        lo, hi = RANGES[inst]
        total = 0.0
        for p, d in _notes(part):
            if d <= 0:
                errs.append(f"{inst}: a note of {d} beats")
            total += d
            if p == "r":
                continue
            for q in p.split("+"):
                try:
                    n = midi(q)
                except ValueError as e:
                    errs.append(f"{inst}: {e}")
                    continue
                if not lo <= n <= hi:
                    errs.append(f"{inst}: {q} is outside its range ({name(lo)} to {name(hi)})")
        totals[inst] = total
    if totals:
        want = max(totals.values(), key=list(totals.values()).count)
        for inst, t in totals.items():
            if abs(t - want) > 1e-6:
                errs.append(f"{inst}: {t:g} beats where the other parts have {want:g}")
            elif abs(t / bpb - round(t / bpb)) > 1e-6:
                errs.append(f"{inst}: {t:g} beats is not a whole number of bars of {bpb:g}")
        seconds = want * 60.0 / float(c["tempo"])
        length = float(c["to"]) - float(c["from"])
        if abs(seconds - length) > 30.0 / float(c["tempo"]):
            errs.append(f"the cue lasts {seconds:.2f} s at {c['tempo']} a minute; its place on the film is {length:.2f} s")
    return errs


def families_missing(instruments):
    have = set(instruments)
    return [f for f, members in FAMILIES.items() if not have & set(members)]


# ------------------------------------------------------------------ MusicXML

DIV = 12                                                 # divisions of a beat: eighths, sixteenths and triplets
VALUES = [(4.0, "whole", 0), (3.0, "half", 1), (2.0, "half", 0), (1.5, "quarter", 1), (1.0, "quarter", 0),
          (0.75, "eighth", 1), (0.5, "eighth", 0), (0.375, "16th", 1), (0.25, "16th", 0), (1 / 3, "eighth", 0),
          (1 / 6, "16th", 0)]


def _pieces(beats):
    out, left = [], beats
    while left > 1e-6:
        for v, t, dots in VALUES:
            if v <= left + 1e-6:
                out.append((v, t, dots))
                left -= v
                break
        else:
            out.append((left, "32nd", 0))
            break
    return out


def _key_fifths(key):
    parts = key.replace("♭", "b").replace("♯", "#").split()
    tonic, mode = parts[0], (parts[1].lower() if len(parts) > 1 else "major")
    if mode.startswith("min"):
        rel = name((midi(tonic + "4") + 3) % 12 + 60, flats=True)[:-1]
        rel = {"Gb": "Gb", "Db": "Db"}.get(rel, rel)
        return MAJOR_FIFTHS.get(rel, MAJOR_FIFTHS.get(name(midi(tonic + "4") + 3)[:-1], 0)), "minor"
    return MAJOR_FIFTHS.get(tonic, 0), "major"


ORDER = ["Piccolo", "Flute", "Oboe", "Clarinet in B\u266d", "Bassoon", "Horn in F", "Trumpet in B\u266d", "Trombone", "Tuba",
         "Timpani", "Glockenspiel", "Xylophone", "Celesta", "Harp", "Violin I", "Violin II", "Viola", "Violoncello",
         "Contrabass"]


def plan_cue(frm, to, hits, meter, lo=60, hi=160, prefer=100):
    """A cue's tempo and bars (M6): its bars fill its place on the film within a frame and its hits land on beats
    (else on half beats) within a frame, the tempo nearest `prefer` among those that do. Hits as (bar, beat), from 1."""
    bpb = beats_per_bar(meter)
    length = float(to) - float(frm)
    pick = None
    for sub in (1.0, 0.5):
        ok = []
        for k in range(int(lo * 100), int(hi * 100) + 1):
            t = k / 100.0
            bars = round(length * t / 60.0 / bpb)
            if bars < 1 or abs(bars * bpb * 60.0 / t - length) > FRAME:
                continue
            step = 60.0 / t * sub
            if all(abs(round((h - frm) / step) * step - (h - frm)) <= FRAME for h in hits):
                ok.append((abs(t - prefer), t, bars))
        if ok:
            _, t, bars = min(ok)
            pick = (t, bars, sub)
            break
    if pick is None:                                   # nothing lands every hit: fill the place exactly, report the hits
        bars = max(1, round(length * prefer / 60.0 / bpb))
        pick = (bars * bpb * 60.0 / length, bars, 0.5)
    t, bars, sub = pick
    beat = 60.0 / t
    out = []
    for h in hits:
        pos = round((h - frm) / (beat * sub)) * sub
        out.append((int(pos // bpb) + 1, round(pos % bpb + 1, 3)))
    return {"tempo": round(t, 2), "bars": int(bars), "half_beats": sub == 0.5, "hits": out}


def _split(part, bpb):
    """A part's notes cut at bar lines: a list of measures, each [(pitch, beats, tie_start, tie_stop)]."""
    measures, cur, room = [], [], bpb
    for p, d in _notes(part):
        left, first = d, True
        while left > 1e-6:
            take = min(left, room)
            cont = left - take > 1e-6
            cur.append((p, take, cont and p != "r", (not first) and p != "r"))
            left -= take
            room -= take
            first = False
            if room <= 1e-6:
                measures.append(cur)
                cur, room = [], bpb
    if cur:
        measures.append(cur)
    return measures


def _written_key(inst, fifths):
    chrom = TRANSPOSE.get(inst, (0, 0))[1]
    pf = fifths + {-2: 2, -7: 1}.get(chrom, 0)
    return pf - 12 if pf > 7 else pf


def _measure(part_el, num, notes, inst, *, attrs=None, tempo=None, mark=None, flats=False):
    m = ET.SubElement(part_el, "measure", number=str(num))
    dia, chrom = TRANSPOSE.get(inst, (0, 0))
    if attrs:
        at = ET.SubElement(m, "attributes")
        if attrs.get("divisions"):
            ET.SubElement(at, "divisions").text = str(DIV)
        k = ET.SubElement(at, "key")
        ET.SubElement(k, "fifths").text = str(attrs["fifths"])
        ET.SubElement(k, "mode").text = attrs["mode"]
        t = ET.SubElement(at, "time")
        ET.SubElement(t, "beats").text = str(attrs["meter"][0])
        ET.SubElement(t, "beat-type").text = str(attrs["meter"][1])
        if attrs.get("divisions"):
            if chrom:
                tr = ET.SubElement(at, "transpose")
                if chrom % 12 == 0:
                    ET.SubElement(tr, "diatonic").text = "0"
                    ET.SubElement(tr, "chromatic").text = "0"
                    ET.SubElement(tr, "octave-change").text = str(chrom // 12)
                else:
                    ET.SubElement(tr, "diatonic").text = str(dia)
                    ET.SubElement(tr, "chromatic").text = str(chrom)
            cl = ET.SubElement(at, "clef")
            sign, line = CLEF.get(inst, ("G", 2))
            ET.SubElement(cl, "sign").text = sign
            ET.SubElement(cl, "line").text = str(line)
    if mark:
        d = ET.SubElement(m, "direction", placement="above")
        ET.SubElement(ET.SubElement(d, "direction-type"), "rehearsal").text = mark
    if tempo:
        d = ET.SubElement(m, "direction", placement="above")
        dt = ET.SubElement(ET.SubElement(d, "direction-type"), "metronome")
        ET.SubElement(dt, "beat-unit").text = "quarter"
        ET.SubElement(dt, "per-minute").text = f"{float(tempo):g}"
        ET.SubElement(d, "sound", tempo=f"{float(tempo):g}")
    for p, beats, tie_on, tie_off in notes:
        pieces = _pieces(beats)
        for j, (v, typ, dots) in enumerate(pieces):
            starts = tie_on or j < len(pieces) - 1
            stops = tie_off or j > 0
            pitches = [None] if p == "r" else p.split("+")
            for ci, q in enumerate(pitches):
                n = ET.SubElement(m, "note")
                if ci:
                    ET.SubElement(n, "chord")
                if q is None:
                    ET.SubElement(n, "rest")
                else:
                    written = midi(q) - chrom
                    nm = name(written, flats)
                    pe = ET.SubElement(n, "pitch")
                    ET.SubElement(pe, "step").text = nm[0]
                    if len(nm) > 2 or nm[1] in "#b":
                        ET.SubElement(pe, "alter").text = "1" if "#" in nm else "-1"
                    ET.SubElement(pe, "octave").text = str(written // 12 - 1)
                ET.SubElement(n, "duration").text = str(int(round(v * DIV)))
                if q is not None and stops:
                    ET.SubElement(n, "tie", type="stop")
                if q is not None and starts:
                    ET.SubElement(n, "tie", type="start")
                ET.SubElement(n, "type").text = typ
                for _ in range(dots):
                    ET.SubElement(n, "dot")
    return m


def _xml(root):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
            '"http://www.musicxml.org/dtds/partwise.dtd">\n' + ET.tostring(root, encoding="unicode"))


def _part_list(root, insts, title):
    ET.SubElement(ET.SubElement(root, "work"), "work-title").text = title
    pl = ET.SubElement(root, "part-list")
    for i, inst in enumerate(insts, 1):
        sp = ET.SubElement(pl, "score-part", id=f"P{i}")
        ET.SubElement(sp, "part-name").text = inst
        mi = ET.SubElement(sp, "midi-instrument", id=f"P{i}-I1")
        ch = (i - 1) % 15 + 1
        ET.SubElement(mi, "midi-channel").text = str(ch if ch < 10 else ch + 1)
        ET.SubElement(mi, "midi-program").text = str(MIDI_PROGRAM.get(inst, 1))


def musicxml(c):
    """One cue as score-partwise MusicXML: one part per instrument, in the cue's order, notes split at bar lines (M4)."""
    return film_musicxml([c], order=list(c["parts"].keys()), marks=False, title=str(c.get("title", c["cue"])))


def film_musicxml(cues, order=None, marks=True, title="Sand to Chip"):
    """The whole film as one score (M7): the cues in order, each from its own measure with its tempo, key and
    rehearsal mark; every instrument in every measure, resting where a cue leaves it out."""
    used = {i for c in cues for i in c["parts"]}
    insts = order or [i for i in ORDER if i in used] + sorted(used - set(ORDER))
    root = ET.Element("score-partwise", version="4.0")
    _part_list(root, insts, title)
    for pi, inst in enumerate(insts, 1):
        part = ET.SubElement(root, "part", id=f"P{pi}")
        num = 1
        for ci, c in enumerate(cues):
            meter = c.get("meter", [4, 4])
            bpb = beats_per_bar(meter)
            fifths, mode = _key_fifths(c.get("key", "C major"))
            total = sum(float(x[1]) for x in next(iter(c["parts"].values())))
            notes = c["parts"].get(inst) or [["r", bpb]] * int(round(total / bpb))
            pf = _written_key(inst, fifths)
            for mi, ms in enumerate(_split(notes, bpb)):
                attrs = {"divisions": num == 1, "fifths": pf, "mode": mode, "meter": meter} if mi == 0 else None
                _measure(part, num, ms, inst, attrs=attrs, tempo=c["tempo"] if mi == 0 else None, flats=pf < 0,
                         mark=(str(c.get("title", c["cue"])) if (marks and pi == 1 and mi == 0) else None))
                num += 1
    return _xml(root)
