"""D0, the readiness ledger (docs/PERMIT.md): every item a fab permit set needs, with its status.

    missing          a permit set needs it and nothing makes it yet
    drawn            on its sheet and in the IFC, no rule bound to it
    checked          every rule bound to it was met, each with its citation
    assumed          drawn and checked, but a number it rests on is assumed
    open             a rule bound to it says cannot say (or not met), or a question has no answer
    licensed review  done as far as a pipeline can; a licensed person judges it
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ["missing", "open", "licensed review", "assumed", "checked", "drawn"]


def build(C, V):
    items = json.loads((HERE / "items.json").read_text())
    by_rule = {}
    for v in V:
        by_rule.setdefault(v["rule"], []).append(v)
    out = []
    for it in items:
        made = it["made"] in C.made
        vs = [v for r in it["rules"] for v in by_rule.get(r, [])]
        bad = [v for v in vs if v["verdict"] != "met"]
        if not made:
            st, why = "missing", f"nothing makes it yet ({it['made']})"
        elif it["licensed_review"]:
            note = f"; {len(bad)} of {len(vs)} verdicts not settled" if bad else (f"; {len(vs)} verdicts met" if vs else "")
            st, why = "licensed review", f"drawn on {it['sheet']}{note}; a licensed person judges it"
        elif bad:
            v = bad[0]
            st, why = "open", f"{v['rule']} ({v['scope']}): {v['verdict']}: {v['why']}"
        elif it.get("question"):
            st, why = "open", it["question"]
        elif vs:
            st = "assumed" if it["assumed"] else "checked"
            why = f"{len(vs)} verdicts met: " + ", ".join(sorted({c for v in vs for c in v['cite']}))
            if it["assumed"]:
                why += "; rests on assumed numbers"
        else:
            st = "assumed" if it["assumed"] else "drawn"
            why = f"drawn on {it['sheet']}" + ("; its numbers are assumed" if it["assumed"] else "; no rule binds it")
        out.append({"id": it["id"], "discipline": it["discipline"], "item": it["item"], "sheet": it["sheet"], "ifc": it["ifc"],
                    "stage": it["stage"], "status": st, "why": why, "licensed_review": it["licensed_review"], "rules": it["rules"]})
    counts = {s: sum(1 for i in out if i["status"] == s) for s in ORDER}
    return {"truth": C.P["truth"], "status": "NOT FOR CONSTRUCTION", "items": out, "counts": counts,
            "gate": "no item missing", "gate_met": counts["missing"] == 0}
