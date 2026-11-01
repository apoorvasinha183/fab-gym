"""Ask the glossary (docs/GLOSSARY-PLUS.md, part 3). A question in your own words, answered by Muse Spark from the
glossary's own entries alone: the entries that share the question's words are picked here, only those are sent, and
the answer must name the entries it rests on as [[Term]]; a name that was not sent is dropped. On the SMT2020 testbed
and a teaching fab of our own; not a real fab."""

import math
import re

from agent.glossary_pictures import TEXT_MODEL, terms as _terms

MODEL = TEXT_MODEL
MAX_ENTRIES = 6
STOP = set("""a an and are as at be been but by can could did do does for from had has have how i if in into is it its
just more most much my no not of on or our so than that the their them then there these they this those to too up us
very was we were what when where which while who why will with would you your about after all also any because before
being between both each few get got make many may might must only other over same should some such through under until
while long""".split())

terms = _terms


def words(text):
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) >= 3 and w not in STOP}


def _match(q, ws):
    """Question words found among `ws`, counting a shared stem of five letters or more (polisher, polishing)."""
    out = set()
    for w in q:
        if w in ws or any(len(w) >= 5 and len(x) >= 5 and w[:6] == x[:6] for x in ws):
            out.add(w)
    return out


def related(question, entries, k=MAX_ENTRIES):
    """The entries that share the most of the question's words, at most k: a word in the term or its other names counts
    three times one in its plain line or meaning, and a rarer word counts more. None when no word is shared."""
    q = words(question)
    if not q:
        return []
    names = [words(" ".join([t["term"], *(t.get("aliases") or [])])) for t in entries]
    texts = [words(" ".join([t.get("plain") or "", t.get("meaning") or ""])) for t in entries]
    n = len(entries)
    df = {w: sum(1 for a, b in zip(names, texts) if _match({w}, a | b)) for w in q}
    idf = {w: math.log((n + 1) / (1 + df[w])) + 0.1 for w in q}
    scored = []
    for t, a, b in zip(entries, names, texts):
        s = sum(3 * idf[w] for w in _match(q, a)) + sum(idf[w] for w in _match(q, b) - _match(q, a))
        if s > 0:
            scored.append((-s, t["term"], t))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [t for _, _, t in scored[:k]]


PROMPT = """You answer a newcomer's question about a chip factory simulator, using ONLY the glossary entries below.

Write two to four short sentences in plain, everyday words. After each claim, name the entry it rests on in double
square brackets, exactly as the entry's name is written, like [[WIP cap]]. Name only entries listed below. If the entries
do not answer the question, say only: The glossary does not cover this.

Question: {question}

Entries:
{entries}"""


def _entry(t):
    return (f"[[{t['term']}]]\nPlain: {t.get('plain') or ''}\nMeaning: {t.get('meaning') or ''}\n"
            f"In this fab: {t.get('here') or ''}")


def answer(question, entries, complete):
    """Ask `complete` (messages in, text out) from these entries alone: {answer, cites, covered, entries}. A cited name
    that was not sent loses its brackets and is not cited."""
    allowed = [t["term"] for t in entries]
    text = complete([{"role": "user", "content": PROMPT.format(question=question, entries="\n\n".join(_entry(t) for t in entries))}])
    text = " ".join(str(text or "").split())
    cites = []

    def keep(m):
        name = m.group(1).strip()
        if name in allowed:
            if name not in cites:
                cites.append(name)
            return f"[[{name}]]"
        return name

    text = re.sub(r"\[\[([^\[\]]{1,80})\]\]", keep, text)
    return {"answer": text, "cites": cites, "covered": bool(cites), "entries": allowed}
