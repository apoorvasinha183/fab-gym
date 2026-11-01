"""One bar for anything, on the Floor (docs/ONE-BAR.md). The page's plain rules read a question first; only a question
none of them reads comes here, and Muse Spark picks a tool for it. It writes no answer and no numbers: it rephrases the
question into the bar's own words, which the page's rules then read again. A pick is kept only when it reads; anything
else is none, and the bar says what it can do. On the SMT2020 testbed; not a real fab."""

import json
import re

from agent.glossary_pictures import TEXT_MODEL

MODEL = TEXT_MODEL
KINDS = ("now", "words", "go", "change", "whatif")

PROMPT = """You route one question typed into a chip factory simulator's search bar. Pick exactly one tool and reply
with JSON only, no other text.

Tools:
- {{"kind": "now", "term": T}}: the question asks what the simulated floor is doing at this moment. T is one of: {terms}.
- {{"kind": "words", "question": Q}}: the question asks what a word or idea means. Q is the question in plain words.
- {{"kind": "go", "to": W}}: the person wants to open a place. W is a short command such as "open challenge 2",
  "open simulation settings", "open the glossary", "open evidence", "open runs", "open S-0001" or "take me to Planar_FE_79".
- {{"kind": "change", "change": C}}: the person wants to change a setting. C is a short command such as
  "double the breakdowns", "repairs 50% worse", "demand up 20%", "no urgent lots", "triple the rework",
  "quality holds on", "cap lots at 2400", "use first come, first served" or "Planar_FE_79 down for 8 hours".
- {{"kind": "whatif", "question": Q}}: the person asks what would happen under a change, or which choice is better.
  Q is the question, starting "What if".
- {{"kind": "none"}}: none of these fits.

Question: {question}"""

# the page counts these right now (web/app.js liveFor); the rest of the glossary has no live number
NOW_TERMS = ("Breakdown", "Repair time", "Setup change", "Tool", "WIP", "Lot", "Wafer", "Cycle time", "Tool group",
             "Hot lot", "Track (overhead track)", "Seed", "Simulator", "Lithography", "Etch", "Polishing (CMP)",
             "Checks (metrology)")
_GO = re.compile(r"\b[QSBF]-\d{4}\b|\bchallenge\s*\d+\b|\bbuild\b|\bsettings\b|\bglossary\b|\bevidence\b|\bruns\b|"
                 r"\b[A-Z][A-Za-z]*_[A-Za-z0-9_]*\d\b|\blongest line\b", re.I)
_SETTING = re.compile(r"break ?down|failure|repair|demand|release|urgent|hot lot|rework|quality hold|defect|\bcap\b|"
                      r"first come|first in|quickest|shortest|\bdown for\b", re.I)
_AMOUNT = re.compile(r"\d|\b(double|twice|triple|thrice|half|halve|no|none|on|off|without)\b", re.I)


def _text(x, n=160):
    return " ".join(str(x).split())[:n] if isinstance(x, str) and 2 <= len(x.strip()) <= n else None


def check(pick, glossary_terms=()):
    """The pick if it reads, else {"kind": "none"}: a known kind; a term the page can count; a place or a change in
    words the page's rules can read; a question of a sensible length."""
    none = {"kind": "none"}
    if not isinstance(pick, dict) or pick.get("kind") not in KINDS:
        return none
    k = pick["kind"]
    if k == "now":
        t = pick.get("term")
        return {"kind": "now", "term": t} if t in NOW_TERMS and (not glossary_terms or t in glossary_terms) else none
    if k == "words":
        q = _text(pick.get("question"), 300)
        return {"kind": "words", "question": q} if q else {"kind": "words"}
    if k == "go":
        w = _text(pick.get("to"))
        return {"kind": "go", "to": w} if w and _GO.search(w) else none
    if k == "change":
        w = _text(pick.get("change"))
        return {"kind": "change", "change": w} if w and _SETTING.search(w) and _AMOUNT.search(w) else none
    q = _text(pick.get("question"), 300)
    return {"kind": "whatif", "question": q} if q else none


def parse(text):
    """The first JSON object in a reply, or None."""
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def pick(question, complete, glossary_terms=()):
    """Ask `complete` (messages in, text out) for a tool, and keep it only if it reads."""
    text = complete([{"role": "user", "content": PROMPT.format(question=question, terms=", ".join(NOW_TERMS))}])
    return check(parse(text), glossary_terms)
