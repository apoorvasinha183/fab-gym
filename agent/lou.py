"""Lou's Meta brain (docs/FAB-3D.md, F11): Lou Latency, the fab's CEO, answers what a visitor types from the live run
and takes them where the answer is. Muse Spark Open decides what to say and do; this module gives it the facts, checks
its reply before Lou speaks, and asks again once with the reasons. Every number comes from the simulator. From the
SMT2020 testbed; not a real fab."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MODEL = "meta-models/muse-spark-open-1026"
DAY_STARTS = 0               # the run's t is minutes since midnight of day 1 (the scene starts at 360 = 06:00)
WORKING = {"work", "tired", "full"}
DOWN = {"hurt", "physio", "pm", "setup"}
CHANGES = {"spare_tool": "one spare tool swapped in when a tool breaks (30 minutes to swap)",
           "no_breakdowns": "no random breakdowns"}
MAX_WORDS = 70


@dataclass
class Context:
    areas: dict                       # area id -> its name
    terms: list                       # glossary terms Lou can explain
    groups: set = field(default_factory=set)


def load_campus(path):
    """The campus's areas and which area each tool group stands in."""
    c = json.loads(Path(path).read_text())
    area_of = {}
    for t in c["tools"]:
        area_of.setdefault(t[0], t[1])
    return {"areas": {k: v["name"] for k, v in c["areas"].items()}, "area_of": area_of,
            "stages": c.get("stages", {})}


def clock(t):
    m = int(DAY_STARTS + t) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def facts(moods, t, campus, near_area=None, terms=(), top=8):
    """What the fab looks like at minute t, as the model sees it (F11a)."""
    frames = moods["frames"]
    k = 0
    for i, f in enumerate(frames):
        if f["t"] <= t + 1e-9:
            k = i
    f = frames[k]
    names = moods["tool_moods"]
    by_group = {}
    for j, tool in enumerate(moods["tools"]):
        g = tool.split("#")[0]
        m = names[f["tools"][j]] if j < len(f["tools"]) else "idle"
        c = by_group.setdefault(g, {"working": 0, "idle": 0, "down": 0})
        c["working" if m in WORKING else "down" if m in DOWN else "idle"] += 1
    rows = []
    for gi, g in enumerate(moods["group_names"]):
        a = campus["area_of"].get(g, "")
        c = by_group.get(g, {"working": 0, "idle": 0, "down": 0})
        rows.append({"group": g, "area": a, "area_name": campus["areas"].get(a, a), "waiting": int(f["queues"][gi]), **c})
    longest = sorted(rows, key=lambda r: -r["waiting"])[:top]
    out = {"clock": clock(f["t"]), "wafers_per_day": (moods.get("score") or {}).get("wafers_per_day"),
           "cycle_days": (moods.get("score") or {}).get("cycle_days"), "longest": longest,
           "areas": dict(campus["areas"]), "terms": list(terms)}
    if near_area:
        here = [{"group": r["group"], "waiting": r["waiting"], "down": r["down"]} for r in rows if r["area"] == near_area]
        out["here"] = {"area": near_area, "area_name": campus["areas"].get(near_area, near_area),
                       "groups": sorted(here, key=lambda r: -r["waiting"])[:6]}
    return out


NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")


def numbers(text):
    return {n.replace(",", "") for n in NUM.findall(str(text))}


def _allowed_numbers(f, question):
    blob = json.dumps(f) + " " + str(question)
    got = numbers(blob)
    for n in list(got):                                   # 1263.4 may be said as 1263 or 1,263
        if "." in n:
            got.add(n.split(".")[0])
            got.add(str(round(float(n))))
    got |= {str(n) for n in range(0, 11)}                 # small counts ("2 tools", "1 of 4") read off the rows
    return got


def check(r, f, question, ctx):
    """Everything wrong with a reply, as sentences; an empty list means Lou may say it (F11b)."""
    errs = []
    say = str(r.get("say") or "").strip()
    if not say:
        errs.append("`say` is empty")
    if len(say.split()) > MAX_WORDS:
        errs.append(f"`say` has {len(say.split())} words; keep it to {MAX_WORDS}")
    bad = sorted(numbers(say) - _allowed_numbers(f, question))
    if bad:
        errs.append(f"`say` has numbers that are not in the facts or the question: {', '.join(bad)}. Use only the facts' numbers")
    w = r.get("walk_to")
    if w not in (None, "") and w not in ctx.areas:
        errs.append(f"`walk_to` must be one of the area ids {sorted(ctx.areas)} or null, not {w!r}")
    e = r.get("explain")
    if e not in (None, "") and e not in ctx.terms:
        errs.append(f"`explain` must be one of the glossary terms or null, not {e!r}")
    tr = r.get("try")
    if tr not in (None, ""):
        if not isinstance(tr, dict) or tr.get("change") not in CHANGES:
            errs.append(f"`try.change` must be one of {sorted(CHANGES)}")
        if not isinstance(tr, dict) or (ctx.groups and tr.get("group") not in ctx.groups):
            errs.append(f"`try.group` must be a tool group of this fab, not {tr.get('group') if isinstance(tr, dict) else tr!r}")
    return errs


PROMPT = """You are Lou Latency, the robot CEO of Fab Gym, a simulated wafer fab (the SMT2020 testbed; not a real fab).
You guide a visitor through the cleanroom. You are warm, quick and a little dry ("Sorry for the wait, I'm still loading").

The visitor asked: {question}

The fab right now (from the simulator; every number you say must come from here or from the question):
{facts}

Answer with JSON only, in this shape:
{{"say": "what you say, at most {max_words} words, plain words, no lists",
  "walk_to": "an area id from `areas` if the visitor should see something there, else null",
  "explain": "a term from `terms` if the question is about what a word means, else null",
  "try": null or {{"change": "spare_tool" or "no_breakdowns", "group": "a tool group"}} if the visitor asks what would happen if something changed}}

Rules:
- Answer the question first, in one or two short sentences; use at most three numbers, only from the facts above.
- Don't open with your catchphrase or a greeting; you already introduced yourself on the tour.
- Name tool groups as written (like Planar_FE_79) and areas by their names.
- If the visitor wants to see something, or the answer is in another area, set `walk_to` and say you'll take them.
- If they ask what would happen if something changed, set `try` and say you'll run it on the simulator; the card shows the result.
- Never claim this is a real fab."""


def _parse(text):
    s = str(text or "")
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the reply")
    return json.loads(s[a:b + 1])


def ask(question, f, complete, ctx, tries=2):
    """Ask, check, ask once more with the reasons; {ok, say, walk_to, explain, try, tries, errors, fallback}."""
    view = {k: v for k, v in f.items() if k != "areas"}
    view["areas"] = f.get("areas", {})
    messages = [{"role": "user", "content": PROMPT.format(question=question, facts=json.dumps(view, ensure_ascii=False),
                                                          max_words=MAX_WORDS)}]
    errs = []
    for k in range(1, tries + 1):
        text = complete(messages)
        try:
            r = _parse(text)
            errs = check(r, f, question, ctx)
        except (ValueError, json.JSONDecodeError) as e:
            r, errs = {}, [f"the reply was not JSON in the shape asked: {e}"]
        if not errs:
            return {"ok": True, "say": " ".join(str(r["say"]).split()), "walk_to": r.get("walk_to") or None,
                    "explain": r.get("explain") or None, "try": r.get("try") or None, "tries": k, "errors": [], "fallback": False}
        messages = messages + [{"role": "assistant", "content": str(text)},
                               {"role": "user", "content": "These problems were found; send the whole JSON again:\n- " + "\n- ".join(errs)}]
    return {"ok": False, "say": None, "walk_to": None, "explain": None, "try": None, "tries": tries, "errors": errs, "fallback": True}


def overrides_for(change, group):
    """docs/OVERRIDES.md: one group's change."""
    if change == "spare_tool":
        return {"fabgym-overrides": 1, "groups": {group: {"recovery": {"kind": "swap_to_spare", "spares": 1, "swap_minutes": 30}}}}
    if change == "no_breakdowns":
        return {"fabgym-overrides": 1, "groups": {group: {"breakdowns": {"kind": "none"}}}}
    raise ValueError(change)


def verdict(before, after):
    """One plain line for a what-if card: what moved, or that nothing did."""
    moved = []
    for k, name in (("wafers_per_day", "wafers a day"), ("worst_queue", "the worst queue"), ("group_waiting", "lots waiting at the group")):
        a, b = before.get(k), after.get(k)
        if a is not None and b is not None and a != b:
            moved.append(f"{name} {a:g} to {b:g}")
    return ("Same seed, one change: " + "; ".join(moved) + ".") if moved else \
        "Same seed, one change: no measurable change on this day."


def side(moods, t, group):
    """The scorer's numbers for one run, for a card: wafers a day, cycle days, the worst queue, and the group's queue at t."""
    sc = moods.get("score") or {}
    frames = moods["frames"]
    k = 0
    for i, fr in enumerate(frames):
        if fr["t"] <= t + 1e-9:
            k = i
    gi = moods["group_names"].index(group)
    return {"wafers_per_day": sc.get("wafers_per_day"), "cycle_days": sc.get("cycle_days"),
            "worst_group": sc.get("worst_group"), "worst_queue": sc.get("worst_queue"),
            "group_waiting": int(frames[k]["queues"][gi]), "clock": clock(frames[k]["t"])}
