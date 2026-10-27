"""The rule engine for the permit set (docs/PERMIT.md, D3).

A rule is data: the sections it cites (each must be in the register: a section is read before a rule cites it), what
it binds, its input, its test (`le`, `ge` or `true`) and its limit, read from the register or computed by a pass and
handed in as an input. For one thing it binds, a rule is **met**, **not met** or **cannot say**: cannot say when an
input is missing, when the law it rests on is not read, when it applies only if a question is answered and nobody
has answered it, or when an input's range of doubt would flip the verdict.

An input is {"value", "lo", "hi", "basis"}. A computed input has lo = hi = value.
"""

UNLIMITED = ("UL", None)


def _limit(rule, inputs, register):
    lim = rule.get("limit")
    if lim is None:
        return None
    if "input" in lim:
        q = inputs.get(lim["input"])
        return None if q is None else q["value"]
    v = register["sections"][lim["section"]]["facts"][lim["fact"]]
    if "key" in lim:
        v = v[lim["key"]]
    return v


def _test(op, v, limit):
    if op == "true":
        return bool(v)
    if limit in UNLIMITED:
        return op == "le"
    if op == "le":
        return v <= limit + 1e-9
    if op == "ge":
        return v >= limit - 1e-9
    raise ValueError(f"unknown test {op!r}")


def _show(v):
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def evaluate(rule, inputs, register):
    """One rule for one thing it binds. Returns {"verdict", "limit", "why", "fix"}."""
    for c in rule["cite"]:
        if c not in register["sections"]:
            raise ValueError(f"rule {rule['id']} cites {c}, which is not in the register (not read)")
    out = {"verdict": "cannot say", "limit": None, "why": "", "fix": rule.get("fix", "")}
    not_read = {n["id"] for n in register.get("not_read", [])}
    missing_law = [x for x in rule.get("rests_on", []) if x in not_read]
    if missing_law:
        out["why"] = f"rests on {', '.join(missing_law)}: not read"
        return out
    when = rule.get("when")
    if when:
        w = inputs.get(when)
        if w is None or w["value"] is None:
            out["why"] = f"applies only if {when.replace('_', ' ')}: a judgement nobody has made"
            return out
        if not w["value"]:
            out.update(verdict="met", why=f"does not apply: not {when.replace('_', ' ')}")
            return out
    q = inputs.get(rule["input"])
    if q is None or q["value"] is None:
        out["why"] = (q or {}).get("why") or f"input {rule['input']} missing"
        return out
    limit = _limit(rule, inputs, register)
    out["limit"] = limit
    if rule["op"] != "true" and limit is None:
        out["why"] = "limit missing"
        return out
    at = [_test(rule["op"], x, limit) for x in (q["lo"], q["value"], q["hi"])]
    sign = {"le": "<=", "ge": ">=", "true": "is"}[rule["op"]]
    shown = f"{_show(q['value'])}" + (f" (range {_show(q['lo'])} to {_show(q['hi'])}, {q['basis']})"
                                     if q["lo"] != q["hi"] else f" ({q['basis']})")
    lim = "" if rule["op"] == "true" else f" {sign} {_show(limit) if limit not in UNLIMITED else 'unlimited'}"
    if len(set(at)) > 1:
        out["why"] = f"{rule['input']} {shown}: its range of doubt crosses the limit{lim}"
        return out
    out["verdict"] = "met" if at[1] else "not met"
    out["why"] = f"{rule['input']} {shown}{lim}" if rule["op"] != "true" else f"{rule['input']} {'yes' if at[1] else 'no'} ({q['basis']})"
    return out


def q(value, basis="computed", lo=None, hi=None, why=None):
    d = {"value": value, "lo": value if lo is None else lo, "hi": value if hi is None else hi, "basis": basis}
    if why:
        d["why"] = why
    return d


def run_all(rules, cases, register):
    """cases: {rule id: [(scope, inputs)]}. Every rule gets a verdict for each scope; a rule with no case gets one
    "cannot say" for its binding, so nothing is silently skipped."""
    out = []
    for r in rules:
        for scope, inputs in cases.get(r["id"], [("all", {})]):
            v = evaluate(r, inputs, register)
            out.append({"rule": r["id"], "topic": r["topic"], "scope": scope, "verdict": v["verdict"],
                        "limit": v["limit"], "why": v["why"], "fix": v["fix"] if v["verdict"] != "met" else "",
                        "cite": r["cite"]})
    return out
