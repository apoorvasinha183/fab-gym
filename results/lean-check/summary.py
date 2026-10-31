"""The Lean referee's verdicts on every scored run, summed for the Evidence page (docs/EVIDENCE-PLAIN.md).

    python3 results/lean-check/summary.py      writes web/data/lean-check.json from results/lean-check/verdicts.tsv
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    rows = [line.split("\t") for line in (ROOT / "results/lean-check/verdicts.tsv").read_text().strip().split("\n")[1:]]
    num = lambda v, k: int((re.search(rf"{k}=(\d+)", v) or [0, 0])[1])
    out = {
        "runs": len(rows),
        "passed": sum(r[4].startswith("yes") for r in rows),
        "jobs": sum(num(r[4], "jobs") for r in rows),
        "states": sum(num(r[4], "states") for r in rows),
        "policies": sorted({r[0] for r in rows}),
        "defects": {d: sum(r[1] == d for r in rows) for d in ("off", "on")},
        "rules": ["no machine does two jobs at once", "every lot follows its route", "no batch is overfilled",
                  "nothing runs on a broken machine", "the breaches counted match"],
        "note": "Each scored run of the long study, replayed and checked by a referee whose rules are proved in Lean (docs/LEAN-CHECK.md). On the SMT2020 testbed.",
    }
    (ROOT / "web/data/lean-check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{out['passed']} of {out['runs']} passed; {out['jobs']:,} jobs checked")


if __name__ == "__main__":
    main()
