"""A question to a scenario (docs/ASK-FAMILIES.md, part 3): the prompt for the model, the check of its JSON answer,
and the scenario text the simulator scores. From the SMT2020 testbed, a published set of a fab's tool groups, routes and times; not a real fab."""

import json
import re
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent / "examples" / "ask"

AREA_NAMES = {
    "Dry_Etch": "dry etch", "Litho": "lithography", "Diffusion": "diffusion (furnaces)", "Dielectric": "dielectric",
    "Wet_Etch": "wet etch", "Implant": "implant", "Planar": "polishing (CMP)", "TF": "thin film",
    "Def_Met": "defect inspection", "Litho_Met": "litho metrology", "TF_Met": "thin-film metrology",
    "Delay_32": "holding",
}

SHOCKS = {
    # kind: (low, high) for the value
    "breakdowns": (0.0, 5.0),
    "repair": (0.1, 5.0),
    "demand": (0.1, 3.0),
    "hot": (0, 200),
}
RULES = ("today", "fifo", "spt", "cr", "random")
POLICIES = ("today", "bfirst", "cap", "reserve", "qualify")
FLOORS = ("share", "wing", "copies")
SHARE = (0.25, 16.0)
MAX_CANDIDATES = 6
CAND_KEYS = {"name", "rule", "cap", "spare", "demand", "floor", "policy"}
TOP_KEYS = {"question", "family", "shocks", "candidates", "sweep", "example", "note"}


def load_groups(areas_tsv):
    """Each tool group's area, from the page's data (written by `fabsim web-data`)."""
    out = {}
    for line in Path(areas_tsv).read_text().splitlines():
        if line.strip():
            g, a = line.split("\t")[:2]
            out[g] = a
    return out


def prompt(groups):
    by_area = {}
    for g, a in sorted(groups.items()):
        by_area.setdefault(a, []).append(g)
    areas = "\n".join(f"- {AREA_NAMES.get(a, a)}: {', '.join(gs)}" for a, gs in sorted(by_area.items()))
    return f"""You turn a person's question about a wafer fab into a scenario for a simulator. The fab is the SMT2020
model, a published set of a fab's tool groups, routes and times: not a real fab and not real data. Family A is its two volume products.
Family B is small, urgent prototype lots (SMT2020's engineering lots): about 5.7 lots a day at share 1.

Answer with one JSON object and nothing else:

{{
  "question": "the question, one line",
  "family": {{"share": 2, "said": true}},                 // only for questions about prototype lots (family B)
  "shocks": [                                             // what happens to the fab, for today and every candidate
    {{"kind": "breakdowns", "value": 1.5, "said": false, "range": [1.0, 2.0]}},
    {{"kind": "outage", "group": "Planar_FE_79", "from_hours": 30, "hours": 8, "said": true}}
  ],
  "candidates": [                                         // at most {MAX_CANDIDATES} answers to compare with today
    {{"name": "own-wing", "floor": "wing"}},
    {{"name": "b-first", "policy": "bfirst"}}
  ]
}}

Every value is said (in the question) or assumed. An assumed value needs "range": [low, high] holding it.

Shocks: breakdowns (multiplier of breakdown rates, 0 to 5), repair (multiplier of repair times, 0.1 to 5), demand
(multiplier of releases, 0.1 to 3), hot (lots in progress made urgent, 0 to 200), outage (a whole tool group down:
"group", "from_hours" after the start, "hours").
Candidate changes (combine several in one candidate):
- "rule": the dispatch rule: today, fifo (longest wait first), spt (shortest processing first), cr (critical
  ratio), random.
- "cap": the most lots in the fab (a whole number); "spare": [["GROUP", tools]] extra tools; "demand": multiplier.
- Only with "family": "floor": share (no change), wing (copies of the 3 busiest groups prototypes visit, in a new
  hall on pad P3), copies (the same copies inside the existing halls); "policy": today, bfirst (prototype lots go
  before volume lots), cap (prototype lots wait at the door when about 1.5 times their usual number are in the fab),
  reserve (one tool in each of the 3 busiest shared groups takes prototype lots first), qualify (prototypes may use
  only half the tools of those groups). bfirst takes no other rule.
- "family": {{"share": x}} sets how many prototype lots arrive, 0.25 to 16 times the usual.

A one-family question is simulated for 3 days after a day of warm-up; a family question for 120 days after 120 days
of warm-up, scored in money a day. Use only these tool groups (by area):
{areas}

Write JSON only, with no comments."""


def read_reply(reply):
    """The JSON object in a model's reply, with or without a code fence."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.S)
    text = m.group(1) if m else reply.strip()
    if not text.startswith("{"):
        i = text.find("{")
        if i < 0:
            raise ValueError("the reply holds no JSON object")
        text = text[i:]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"the reply is not valid JSON: {e}") from None
    if not isinstance(obj, dict):
        raise ValueError("the reply is not a JSON object")
    return obj


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _said_or_range(item, value, where, out):
    said = item.get("said")
    if not isinstance(said, bool):
        out.append(f"{where}: say whether it was said in the question (said: true or false)")
        return
    if not said:
        r = item.get("range")
        if not (isinstance(r, list) and len(r) == 2 and all(_num(v) for v in r)):
            out.append(f"{where}: an assumed value needs a range [low, high]")
        elif not (r[0] <= value <= r[1]):
            out.append(f"{where}: the range {r} does not hold the value {value}")


def check(a, groups):
    """Every reason the answer is refused; empty when it may run."""
    out = []
    if not isinstance(a, dict):
        return ["the answer is not a JSON object"]
    for k in a:
        if k not in TOP_KEYS:
            out.append(f"unknown field {k!r}")
    q = a.get("question")
    if not isinstance(q, str) or not q.strip() or "\n" in q or "\t" in q:
        out.append("the question must be one line of text")
    fam = a.get("family")
    if fam is not None:
        share = fam.get("share") if isinstance(fam, dict) else None
        if not _num(share) or not (SHARE[0] <= share <= SHARE[1]):
            out.append(f"family share must be a number from {SHARE[0]} to {SHARE[1]}")
        else:
            _said_or_range(fam, share, "family share", out)
    shocks = a.get("shocks", [])
    if not isinstance(shocks, list):
        out.append("shocks must be a list")
        shocks = []
    seen = set()
    for i, s in enumerate(shocks):
        where = f"shock {i + 1}"
        if not isinstance(s, dict):
            out.append(f"{where}: not an object")
            continue
        kind = s.get("kind")
        if kind in seen:
            out.append(f"{where}: two {kind} shocks")
        seen.add(kind)
        if kind in SHOCKS:
            lo, hi = SHOCKS[kind]
            v = s.get("value")
            if not _num(v) or not (lo <= v <= hi) or (kind == "hot" and v != int(v)):
                out.append(f"{where}: {kind} must be from {lo} to {hi}")
            else:
                _said_or_range(s, v, where, out)
        elif kind == "outage":
            if s.get("group") not in groups:
                out.append(f"{where}: no tool group {s.get('group')!r}")
            f, h = s.get("from_hours"), s.get("hours")
            if not (_num(f) and f >= 0 and _num(h) and 0 < h <= 24 * 30):
                out.append(f"{where}: an outage needs from_hours >= 0 and hours from 0 to 720")
            else:
                _said_or_range(s, h, where, out)
        else:
            out.append(f"{where}: unknown shock {kind!r}")
    cands = a.get("candidates", [])
    if not isinstance(cands, list):
        out.append("candidates must be a list")
        cands = []
    if len(cands) > MAX_CANDIDATES:
        out.append(f"{len(cands)} candidates, at most {MAX_CANDIDATES}")
    names = set()
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            out.append(f"candidate {i + 1}: not an object")
            continue
        n = c.get("name")
        where = f"candidate {n!r}" if isinstance(n, str) else f"candidate {i + 1}"
        if not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", n):
            out.append(f"{where}: a name of letters, digits, - and _")
        elif n in names:
            out.append(f"{where}: two candidates with one name")
        names.add(n)
        for k in c:
            if k not in CAND_KEYS:
                out.append(f"{where}: unknown change {k!r}")
        if set(c) <= {"name"}:
            out.append(f"{where}: changes nothing")
        if "rule" in c and c["rule"] not in RULES:
            out.append(f"{where}: unknown rule {c['rule']!r}")
        if "cap" in c and not (isinstance(c["cap"], int) and not isinstance(c["cap"], bool) and c["cap"] >= 1):
            out.append(f"{where}: a cap is a whole number of lots, at least 1")
        if "demand" in c and not (_num(c["demand"]) and 0 < c["demand"] <= 3):
            out.append(f"{where}: demand from 0 to 3")
        if "spare" in c:
            sp = c["spare"]
            if not isinstance(sp, list) or not sp:
                out.append(f"{where}: spare is a list of [group, tools]")
            else:
                for x in sp:
                    if not (isinstance(x, list) and len(x) == 2 and x[0] in groups and isinstance(x[1], int) and 1 <= x[1] <= 10):
                        out.append(f"{where}: spare {x!r} needs a known group and 1 to 10 tools")
        if "floor" in c and c["floor"] not in FLOORS:
            out.append(f"{where}: unknown floor {c['floor']!r}")
        if "policy" in c and c["policy"] not in POLICIES:
            out.append(f"{where}: unknown policy {c['policy']!r}")
        if ("floor" in c or "policy" in c) and fam is None:
            out.append(f"{where}: a floor or policy needs a family share")
        if c.get("policy") == "bfirst" and c.get("rule", "today") != "today":
            out.append(f"{where}: bfirst decides the order, so it takes no other rule")
    sw = a.get("sweep")
    if sw is not None:
        out.append("sweeps are written by hand in the scenario editor for now")
    return out


def _n(x):
    return str(int(x)) if float(x) == int(x) else repr(float(x))


def to_scenario(a):
    """The checked answer as `fabgym-scenario 1` text."""
    tag = lambda item: "said" if item.get("said") else "assumed"
    L = ["fabgym-scenario 1", f"question\t{a['question'].strip()}"]
    if a.get("family") is not None:
        L.append(f"family\tshare\t{_n(a['family']['share'])}\t{tag(a['family'])}")
    for s in a.get("shocks", []):
        if s["kind"] == "outage":
            L.append(f"shock\toutage\t{s['group']}\t{_n(s['from_hours'])}\t{_n(s['hours'])}\t{tag(s)}")
        else:
            L.append(f"shock\t{s['kind']}\t{_n(s['value'])}\t{tag(s)}")
    for c in a.get("candidates", []):
        n = c["name"]
        if "floor" in c:
            L.append(f"candidate\t{n}\tfloor\t{c['floor']}")
        if "policy" in c:
            L.append(f"candidate\t{n}\tpolicy\t{c['policy']}")
        if "rule" in c:
            L.append(f"candidate\t{n}\trule\t{c['rule']}")
        if "cap" in c:
            L.append(f"candidate\t{n}\tcap\t{c['cap']}")
        for g, k in c.get("spare", []):
            L.append(f"candidate\t{n}\tspare\t{g}\t{k}")
        if "demand" in c:
            L.append(f"candidate\t{n}\tdemand\t{_n(c['demand'])}")
    return "\n".join(L) + "\n"


def examples():
    """The recorded example answers, written by us and marked as examples (not from a model)."""
    return [json.loads(p.read_text()) for p in sorted(EXAMPLES.glob("*.json"))]


def ask_model(model, question, groups):
    """The model's answer to a question, read from its reply (not yet checked)."""
    reply = model.complete([{"role": "system", "content": prompt(groups)}, {"role": "user", "content": question}])
    return reply, read_reply(reply)
