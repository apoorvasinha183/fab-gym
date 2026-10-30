"""The agent loop (docs/AGENT.md): a model writes dispatch rules, the simulator scores them, a person signs.

Everything runs on the SMT2020 model of a fab. The model sees only training scores (seeds 100 and up);
the finalists are scored once on the held-out seeds after the search ends, and nothing from that
scoring is ever sent to the model.

    python3 -m agent.fabgym_agent run --question "..." (--shop FILE | --smt2020 DIR) --out DIR
        [--scenario FILE] [--train 100..104] [--generations 3] [--per-generation 2] [--top 2]
        (--model NAME --base-url URL [--key-file PATH] | --stand-in FILE.json)
    python3 -m agent.fabgym_agent sign CARD.json --name "Operations head"
"""

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY = Path.home() / ".config" / "fab-gym" / "baseten.key"
DEFAULT_CLI = ROOT / "target" / "release" / "fabrule"
CARD_KIND = "fab-gym.rule-card/1"
HELD_OUT_SEEDS = list(range(10))
TRAIN_FROM = 100
KEEP_EXCHANGES = 8  # the model sees the opening and the last few rules with their scores

MEASURE_WORDS = {
    "reward": "reward (lots finished minus 0.01 per lot-hour waiting)",
    "moves": "moves (steps completed)",
    "lots_finished": "lots finished",
    "wait_lot_hours": "lot-hours waiting",
    "wait_per_move_minutes": "minutes waited per move",
    "breaches": "queue-time breaches",
    "mean_wip": "lots in the fab (mean)",
}

SPEC = """You write dispatch rules for a simulated wafer fab (the SMT2020 model of a fab, a published
research model; no real fab or real data). Whenever a free tool could start work, the simulator hands
every waiting candidate (a lot, or a batch of lots) to your function, and the tool starts the candidate
with the smallest key. Ties keep the simulator's own pick (today's rule); a NaN key counts as the largest.

Write exactly one function, in one ```rust code block:

    pub fn key(c: &Cand, x: &Ctx) -> f64 { ... }

Cand, one candidate (every field f64):
  is_batch (1 or 0), lots (lots in it), priority, size_wafers, step (index on its route), steps_left,
  waited_minutes (in this queue), setup_change (1 if the tool must change setup), proc_minutes,
  work_left_minutes (processing left on its route), age_minutes (since release),
  cqt_slack_minutes (minutes before a queue-time limit is breached; 1e9 when none runs),
  is_default (1 for the simulator's own pick),
  family (0 when the fab has one family; with two, 1 is volume and 2 is engineering lots).
Ctx, the decision (every field f64):
  t (minutes since the start), queue (number of candidates), working, idle, down (the deciding tool
  group's tools), lots_waiting, lots_finished (in the whole fab).

Use f64 arithmetic and the standard library's maths (min, max, sqrt, ln_1p, exp, powf, abs, ...).
Write full paths instead of `use`. These are refused before compiling: unsafe, extern, attributes,
use, mod, static, files, network, processes, the environment, threads, the clock, and macros that read
files or the environment. Each decision has a fuel budget; a rule that runs out of fuel, panics or
traps falls back to today's pick, and a rule with faults on more than 1% of decisions is not eligible.

Scoring: a day of warm-up, then a 3-day window, on paired seeds; every measure is the rule minus
today's rule with a 95% interval. Reward is lots finished minus 0.01 per lot-hour waiting; higher is
better. The search keeps the rules with the best training reward; a separate final scoring on seeds
you never see decides what goes to a person to sign."""


# ------------------------------------------------------------------ models


class StandInModel:
    """Returns written replies in order, for tests and offline runs."""

    name = "stand-in (written replies)"

    def __init__(self, replies):
        self._replies = list(replies)
        self._next = 0

    def complete(self, messages):
        if self._next >= len(self._replies):
            raise RuntimeError("the stand-in model has no replies left")
        r = self._replies[self._next]
        self._next += 1
        return r


class HttpModel:
    """An OpenAI-compatible chat endpoint (Baseten, or Meta's API). The key is read from a file and is
    never printed, logged or put in a message."""

    def __init__(self, base_url, model, key_file=DEFAULT_KEY, temperature=0.7, max_tokens=8000, timeout=300):
        key_file = Path(key_file).expanduser()
        if not key_file.is_file():
            raise FileNotFoundError(f"no key file at {key_file}; put the key there (one line, mode 600)")
        key = key_file.read_text().strip()
        if not key:
            raise ValueError(f"the key file at {key_file} is empty")
        self.__key = key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = model
        self.key_file = key_file
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def __repr__(self):
        return f"HttpModel(base_url={self.base_url!r}, model={self.model!r}, key_file={str(self.key_file)!r})"

    __str__ = __repr__

    def __getstate__(self):
        raise TypeError("HttpModel holds a key and is not pickled")

    def complete(self, messages):
        """The reply's text. The model thinks before it answers and the thinking counts against max_tokens,
        so a reply cut off at the limit is asked again once with twice the room (docs/BASETEN-PRICING.md)."""
        budget = self.max_tokens
        for attempt in (1, 2):
            choice = self._ask(messages, budget)
            text = choice["message"].get("content") or ""
            if choice.get("finish_reason") != "length":
                return text
            if attempt == 1:
                budget *= 2
        if not text:
            raise RuntimeError(
                f"the model used all {budget} max_tokens thinking and wrote no reply; raise max_tokens"
            )
        return text

    def _ask(self, messages, max_tokens):
        body = json.dumps(
            {"model": self.model, "messages": messages, "temperature": self.temperature, "max_tokens": max_tokens}
        ).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.__key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:500].decode("utf-8", "replace").replace(self.__key, "[key]")
            raise RuntimeError(f"the model endpoint answered {e.code}: {detail}") from None
        return out["choices"][0]


# ------------------------------------------------------------------ the scorer


class Scorer:
    """Runs `fabrule score` on training seeds, or once on the held-out seeds for the final scoring."""

    def __init__(self, cli, shop, train, threads=4, scenario=None, cache=None):
        self.cli = Path(cli)
        self.shop = Path(shop)
        self.train = [int(s) for s in train]
        if len(self.train) < 2:
            raise ValueError("at least two training seeds")
        if min(self.train) < TRAIN_FROM:
            raise ValueError(f"training seeds start at {TRAIN_FROM}; 0 to 9 are held out")
        if self.train != list(range(self.train[0], self.train[-1] + 1)):
            raise ValueError("training seeds must run without gaps, for example 100 to 109")
        self.threads = max(1, min(4, int(threads)))
        self.scenario = Path(scenario) if scenario else None
        self.cache = Path(cache) if cache else ROOT / "target" / "fabrule-cache"

    def describe(self):
        return {
            "shop": str(self.shop),
            "scenario": self.scenario.read_text() if self.scenario else None,
            "train_seeds": self.train,
        }

    def score(self, source, held_out=False):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "rule.rs"
            f.write_text(source)
            cmd = [str(self.cli), "score", str(f)]
            cmd += ["--smt2020" if self.shop.is_dir() else "--shop", str(self.shop)]
            if self.scenario:
                cmd += ["--scenario", str(self.scenario)]
            cmd += ["--held-out"] if held_out else ["--train", f"{self.train[0]}..{self.train[-1] + 1}"]
            cmd += ["--threads", str(self.threads), "--cache", str(self.cache)]
            p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, preexec_fn=lambda: os.nice(10))
        try:
            return json.loads(p.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "stage": "scorer", "error": (p.stderr or p.stdout)[-2000:]}


# ------------------------------------------------------------------ the search

TODAY = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { if c.is_default > 0.5 { 0.0 } else { 1.0 } }"


@dataclass
class Search:
    question: str
    model_name: str
    scorer: dict
    baselines: dict
    candidates: list = field(default_factory=list)


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _code(reply):
    blocks = re.findall(r"```[ \t]*([A-Za-z0-9_+-]*)[^\n]*\n(.*?)```", reply or "", re.S)
    rust = [b for lang, b in blocks if lang.lower() in ("rust", "rs")]
    for b in rust + [b for _, b in blocks]:
        if "fn key" in b:
            return b.strip()
    return None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def _f(x, plus=True):
    if x is None:
        return "n/a"
    return f"{x:+.2f}" if plus else f"{x:.2f}"


def _baselines(report):
    out = {}
    for arm in report["arms"]:
        if arm["name"] == "rule":
            continue
        out[arm["name"]] = {k: _mean(arm[k]) for k in MEASURE_WORDS if k in arm}
    return out


def _train_reward(report):
    arm = [a for a in report["arms"] if a["name"] == "rule"][0]
    return _mean(arm["reward"])


def _feedback(c, train):
    head = f"Rule {c['generation']}.{c['index']}"
    if not c["ok"]:
        return f"{head} was not scored.\n{c['error'][:3000]}"
    r = c["report"]
    lines = [f"{head}: scored on training seeds {train[0]} to {train[-1]} ({len(train)} seeds)."]
    lines.append("Against today's rule (rule minus today, 95% interval):")
    for m in r["vs_today"]:
        iv = m["interval"]
        word = MEASURE_WORDS.get(m["key"], m["key"])
        lines.append(f"  {word}: {_f(iv['mean'])} ({_f(iv['lo'])} to {_f(iv['hi'])}), {m['verdict']}")
    lines.append(
        "Against the baselines on reward: "
        + "; ".join(
            f"{b['name']} {_f(b['interval']['mean'])} ({_f(b['interval']['lo'])} to {_f(b['interval']['hi'])})"
            for b in r["vs_baselines"]
        )
    )
    lines.append(
        f"Faults: {r['faults']} of {r['decisions']} decisions; "
        + ("eligible." if r["eligible"] else "not eligible (faults over 1%).")
    )
    return "\n".join(lines)


def search(question, model, scorer, generations=3, per_generation=2):
    """Ask the model for rules, score each on training seeds, and send the scores back."""
    base = scorer.score(TODAY)
    if not base.get("ok"):
        raise RuntimeError(f"the scorer failed on today's rule: {base.get('error')}")
    if base.get("held_out"):
        raise RuntimeError("the scorer returned a held-out scoring during the search")
    train = scorer.train
    s = Search(question, getattr(model, "name", type(model).__name__), scorer.describe(), _baselines(base))
    table = "\n".join(
        f"  {arm}: " + ", ".join(f"{k} {_f(v, plus=False)}" for k, v in vals.items()) for arm, vals in s.baselines.items()
    )
    scen = s.scorer["scenario"]
    opening = (
        f"Question: {question}\n\n"
        + (f"Scenario (applied before every run):\n{scen}\n\n" if scen else "")
        + f"Training scores of today's rule and the baselines, mean per seed over seeds {train[0]} to {train[-1]}:\n"
        + table
        + f"\n\nWrite rule 1.1. You will write {generations * per_generation} rules in {generations} "
        + f"generations of {per_generation}; after each you see its training scores."
    )
    system = {"role": "system", "content": SPEC}
    first = {"role": "user", "content": opening}
    pairs = []
    for g in range(1, generations + 1):
        for k in range(1, per_generation + 1):
            msgs = [system, first] + [m for p in pairs[-KEEP_EXCHANGES:] for m in p]
            reply = model.complete(msgs)
            src = _code(reply)
            c = {"generation": g, "index": k, "reply": reply, "source": src, "ok": False, "error": None}
            if src is None:
                c["error"] = "No Rust code: the reply has no ```rust block defining `pub fn key`."
            else:
                c["source_sha256"] = _sha(src)
                rep = scorer.score(src)
                if rep.get("held_out"):
                    raise RuntimeError("the scorer returned a held-out scoring during the search")
                if rep.get("ok"):
                    c.update(ok=True, report=rep, eligible=rep["eligible"], train_reward=_train_reward(rep))
                else:
                    c["error"] = f"{rep.get('stage', 'scorer')}: {rep.get('error', '')}"
            s.candidates.append(c)
            best = max(
                (x for x in s.candidates if x["ok"] and x["eligible"]), key=lambda x: x["train_reward"], default=None
            )
            note = _feedback(c, train)
            if best is not None:
                note += (
                    f"\nBest eligible so far: rule {best['generation']}.{best['index']}, "
                    f"mean training reward {best['train_reward']:.2f}."
                )
            nxt = (g, k + 1) if k < per_generation else (g + 1, 1)
            if nxt[0] <= generations:
                note += f"\n\nWrite rule {nxt[0]}.{nxt[1]}."
            pairs.append(({"role": "assistant", "content": reply}, {"role": "user", "content": note}))
    return s


# ------------------------------------------------------------------ the card


def _card_hash(card):
    payload = [{"source_sha256": f["source_sha256"], "held_out": f["held_out"]} for f in card["finalists"]]
    payload = {"seeds": card["seeds"], "question": card["question"], "finalists": payload}
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _render(card):
    L = ["# Rule card", ""]
    L.append(
        "Everything here runs on the SMT2020 model of a fab (a published research model; no real fab or real data)."
    )
    L.append("Agents propose, the simulator scores, a person signs.")
    L.append("")
    if card["signed_by"]:
        L.append(f"**Signed by {card['signed_by']}** on {card['signed_at']}.")
    else:
        L.append("**Not signed.** A person signs with `python3 -m agent.fabgym_agent sign card.json --name NAME`.")
    L += ["", f"Question: {card['question']}", ""]
    L.append(f"- Model: {card['model']}")
    L.append(f"- Shop: `{card['scorer']['shop']}`")
    tr = card["scorer"]["train_seeds"]
    L.append(f"- Rules tried: {card['tried']}, scored: {card['scored']}; training seeds {tr[0]} to {tr[-1]}")
    L.append(
        f"- Final scoring: seeds {card['seeds'][0]} to {card['seeds'][-1]}, run once after the search; "
        "the model never saw them"
    )
    L.append(
        "- Window: a day of warm-up, then 3 days; every number is the rule minus today's rule, 95% paired t interval"
    )
    L.append(f"- Card hash: `{card['hash']}`")
    if card["scorer"].get("scenario"):
        L += ["", "Scenario:", "", "```", card["scorer"]["scenario"].strip(), "```"]
    for i, f in enumerate(card["finalists"], 1):
        h = f["held_out"]
        L += ["", f"## Finalist {i} (rule {f['generation']}.{f['index']})", ""]
        rew = [m for m in h["vs_today"] if m["key"] == "reward"][0]["interval"]
        L.append(
            f"Reward against today on the held-out seeds: {_f(rew['mean'])} (95% {_f(rew['lo'])} to "
            f"{_f(rew['hi'])}); training mean reward {f['train_reward']:.2f}."
        )
        L += ["", "| Measure | Rule minus today | 95% interval | Verdict |", "| --- | --- | --- | --- |"]
        for m in h["vs_today"]:
            iv = m["interval"]
            L.append(
                f"| {MEASURE_WORDS.get(m['key'], m['key'])} | {_f(iv['mean'])} | "
                f"{_f(iv['lo'])} to {_f(iv['hi'])} | {m['verdict']} |"
            )
        L.append("")
        L.append(
            "Against the baselines on reward: "
            + "; ".join(
                f"{b['name']} {_f(b['interval']['mean'])} ({_f(b['interval']['lo'])} to {_f(b['interval']['hi'])})"
                for b in h["vs_baselines"]
            )
            + "."
        )
        L.append(
            f"Faults: {h['faults']} of {h['decisions']} decisions; {'eligible' if h['eligible'] else 'not eligible'}."
        )
        L += ["", f"Source (sha256 `{f['source_sha256']}`):", "", "```rust", f["source"], "```"]
    return "\n".join(L) + "\n"


def _write(card, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "card.json").write_text(json.dumps(card, indent=1) + "\n")
    (out_dir / "card.md").write_text(_render(card))


def finalise(s, scorer, top=2, out_dir=None):
    """Score the best eligible rules once on the held-out seeds and write an unsigned card."""
    seen, picks = set(), []
    for c in sorted((c for c in s.candidates if c["ok"] and c["eligible"]), key=lambda c: -c["train_reward"]):
        if c["source_sha256"] not in seen:
            seen.add(c["source_sha256"])
            picks.append(c)
        if len(picks) == top:
            break
    if not picks:
        raise ValueError("no eligible rule to score")
    finalists = []
    for c in picks:
        h = scorer.score(c["source"], held_out=True)
        if not h.get("ok") or not h.get("held_out") or h.get("seeds") != HELD_OUT_SEEDS:
            raise RuntimeError(f"the final scoring failed: {h.get('error', h)}")
        finalists.append(
            {
                "generation": c["generation"],
                "index": c["index"],
                "source": c["source"],
                "source_sha256": c["source_sha256"],
                "train_reward": c["train_reward"],
                "held_out": h,
            }
        )
    card = {
        "kind": CARD_KIND,
        "on": "the SMT2020 model",
        "question": s.question,
        "model": s.model_name,
        "scorer": s.scorer,
        "tried": len(s.candidates),
        "scored": sum(1 for c in s.candidates if c["ok"]),
        "seeds": HELD_OUT_SEEDS,
        "finalists": finalists,
        "made_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "signed_by": None,
        "signed_at": None,
    }
    card["hash"] = _card_hash(card)
    if out_dir is not None:
        _write(card, out_dir)
    return card


def sign(card_path, name):
    """A person signs a card. Refuses a card already signed and one whose numbers were changed."""
    card_path = Path(card_path)
    card = json.loads(card_path.read_text())
    if card.get("kind") != CARD_KIND:
        raise ValueError("not a rule card")
    if card.get("signed_by"):
        raise ValueError(f"already signed by {card['signed_by']}")
    if _card_hash(card) != card.get("hash"):
        raise ValueError("the card's numbers no longer match its scoring; not signed")
    if not str(name).strip():
        raise ValueError("a name is needed to sign")
    card["signed_by"] = str(name).strip()
    card["signed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    _write(card, card_path.parent)
    return card


# ------------------------------------------------------------------ command line


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fabgym_agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--question", required=True)
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--shop")
    g.add_argument("--smt2020")
    r.add_argument("--scenario")
    r.add_argument("--train", default="100..104")
    r.add_argument("--generations", type=int, default=3)
    r.add_argument("--per-generation", type=int, default=2)
    r.add_argument("--top", type=int, default=2)
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--cli", default=str(DEFAULT_CLI))
    r.add_argument("--out", required=True)
    m = r.add_mutually_exclusive_group(required=True)
    m.add_argument("--stand-in", help="a JSON list of written replies")
    m.add_argument("--model")
    r.add_argument("--base-url")
    r.add_argument("--key-file", default=str(DEFAULT_KEY))
    sg = sub.add_parser("sign")
    sg.add_argument("card")
    sg.add_argument("--name", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "sign":
        card = sign(a.card, a.name)
        print(f"signed by {card['signed_by']} at {card['signed_at']}")
        return 0
    lo, hi = (int(x) for x in a.train.split(".."))
    scorer = Scorer(a.cli, a.shop or a.smt2020, range(lo, hi), threads=a.threads, scenario=a.scenario)
    if a.stand_in:
        model = StandInModel(json.loads(Path(a.stand_in).read_text()))
    else:
        if not a.base_url:
            ap.error("--model needs --base-url")
        model = HttpModel(a.base_url, a.model, a.key_file)
    s = search(a.question, model, scorer, a.generations, a.per_generation)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "search.json").write_text(json.dumps(asdict(s), indent=1) + "\n")
    card = finalise(s, scorer, a.top, out)
    print(f"{card['tried']} rules tried, {card['scored']} scored; card at {out / 'card.md'} (not signed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
