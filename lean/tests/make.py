"""Write the referee's hand-made test receipts (docs/LEAN-CHECK.md, tests L1 to L3) and expected.txt.

One valid receipt, `v-base`, is written out by hand below; every other receipt is it with one or two records changed,
so each change is easy to read here. Times are minutes; `421/1` is 210.5 (exact: M over 2 to the E).

Run from the repository root: python3 lean/tests/make.py
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent

HEADER = """fabgym-receipt 1
run 0000000000000000000000000000000000000000000000000000000000000000 0 hand 400 100 400
group 0 Litho
group 1 Furnace
group 2 Etch
group 3 Metro
tool 0 0
tool 1 1
tool 2 2
tool 3 3
route 0 5
step 0 0 0 - 0 - - -
step 0 1 1 100 0 - 2 60
step 0 2 2 - 0 - - -
step 0 3 3 - 1 - - -
step 0 4 0 - 0 1 - -
lot 0 0 25 0
lot 1 0 25 0
lot 2 0 25 2"""

# Lot 2 starts mid-route at step 2, skips the sampled step 3, reworks from step 4 back to step 1. Lots 0 and 1 share a
# furnace batch (50 wafers of 100). Step 1's clock to step 2 is 60 minutes: lot 1 waits 70, one breach.
# Tool 2 is down for maintenance from 290 to 320. Tool 0 sets up from 0 to 10.
EVENTS = """S 0 0 2
S 2 0 0
J 2 0 20 1 2 2 0
S 0 10 0
J 0 10 40 1 0 0 0
S 2 20 1
S 0 40 1
S 0 40 0
J 0 40 70 1 1 0 0
S 0 70 1
S 0 70 0
J 0 70 90 1 2 4 25
S 1 80 0
J 1 80 200 2 0 1 45 1 1 75
S 0 90 1
S 1 200 1
S 1 205 0
J 1 205 325 1 2 1 95
S 2 230 0
J 2 230 250 1 0 2 421/1
S 2 250 1
S 2 270 0
J 2 270 285 1 1 2 205
S 2 285 1
S 2 290 3
S 2 320 1
S 1 325 1
S 2 330 0
J 2 330 350 1 2 2 328
S 2 350 1"""

END = "end 9 21 1 1"

BASE = f"{HEADER}\n{EVENTS}\n{END}\n"


def change(text: str, *pairs: tuple[str, str]) -> str:
    """Replace each whole line `old` by `new` (new may be several lines, or "" to drop the line)."""
    lines = text.splitlines()
    for old, new in pairs:
        assert lines.count(old) == 1, f"not exactly one line {old!r}"
        i = lines.index(old)
        lines[i : i + 1] = new.splitlines() if new else []
    return "\n".join(lines) + "\n"


def after(text: str, line: str, *new: str) -> str:
    lines = text.splitlines()
    assert lines.count(line) == 1, line
    i = lines.index(line) + 1
    lines[i:i] = list(new)
    return "\n".join(lines) + "\n"


CASES: dict[str, tuple[str, str]] = {}


def case(name: str, verdict: str, text: str) -> None:
    CASES[name] = (verdict, text)


# L1: valid
case("v-base", "yes", BASE)
# a gap exactly at the limit is no breach: lot 1 begins step 2 at 260, 60 after step 1 ended
case(
    "v-at-limit",
    "yes",
    change(
        BASE,
        ("S 2 270 0", "S 2 260 0"),
        ("J 2 270 285 1 1 2 205", "J 2 260 275 1 1 2 205"),
        ("S 2 285 1", "S 2 275 1"),
        (END, "end 9 21 0 0"),
    ),
)
# L2: one rule broken each
case(
    "b-overlap",
    "no one-job",
    after(change(BASE, ("S 0 40 1", ""), ("S 0 40 0", ""), ("J 0 40 70 1 1 0 0", "")), "S 2 20 1", "J 0 35 70 1 1 0 0").replace(
        "end 9 21", "end 9 19"
    ),
)
case(
    "b-overlap-batch-tool",
    "no one-job",
    after(change(BASE, ("S 1 200 1", ""), ("S 1 205 0", ""), ("J 1 205 325 1 2 1 95", "")), "S 0 90 1", "J 1 190 325 1 2 1 95").replace(
        "end 9 21", "end 9 19"
    ),
)
case("b-wrong-group", "no route", change(BASE, ("S 2 230 0", "S 3 230 0"), ("J 2 230 250 1 0 2 421/1", "J 3 230 250 1 0 2 421/1"), ("S 2 250 1", "S 3 250 1")))
case("b-skip", "no route", change(BASE, ("lot 2 0 25 2", "lot 2 0 25 1")))
case("b-start-before-arrival", "no route", change(BASE, ("J 2 230 250 1 0 2 421/1", "J 2 230 250 1 0 2 240")))
case("b-arrive-before-left", "no route", change(BASE, ("J 2 230 250 1 0 2 421/1", "J 2 230 250 1 0 2 190")))
case("b-overfill", "no batch", change(BASE, ("lot 1 0 25 0", "lot 1 0 80 0")))
case("b-mixed-steps", "no batch", change(BASE, ("J 1 80 200 2 0 1 45 1 1 75", "J 1 80 200 2 0 1 45 1 0 75")))
case(
    "b-two-lots-not-batch",
    "no batch",
    change(BASE, ("J 0 10 40 1 0 0 0", "J 0 10 40 2 0 0 0 1 0 0"), ("J 0 40 70 1 1 0 0", "")).replace("end 9 21", "end 8 21"),
)
case("b-job-in-breakdown", "no down", change(BASE, ("S 2 290 3", "S 2 290 4"), ("S 2 320 1", ""), ("S 2 330 0", "")).replace("end 9 21", "end 9 19"))
case("b-down-starts-in-job", "no down", after(BASE, "J 2 330 350 1 2 2 328", "S 2 340 3").replace("end 9 21", "end 9 22"))
case("b-breach-high", "no breach", change(BASE, (END, "end 9 21 2 2")))
case("b-breach-low", "no breach", change(BASE, (END, "end 9 21 0 0")))
case("b-breach-window", "no breach", change(BASE, (END, "end 9 21 1 0")))
# L3: malformed
case("f-out-of-order", "no format", change(BASE, ("S 2 20 1", ""), ("S 0 0 2", "S 2 20 1\nS 0 0 2")))
case("f-cut-off", "no format", change(BASE, (END, "")))
case("f-unknown-tool", "no format", change(BASE, ("J 2 230 250 1 0 2 421/1", "J 9 230 250 1 0 2 421/1")))
case("f-unknown-lot", "no format", change(BASE, ("J 2 230 250 1 0 2 421/1", "J 2 230 250 1 7 2 421/1")))
case("f-header-after-event", "no format", change(BASE, ("lot 2 0 25 2", ""), ("S 2 350 1", "S 2 350 1\nlot 2 0 25 2")))
case("f-wrong-counts", "no format", change(BASE, (END, "end 8 21 1 1")))


def main() -> None:
    lines = []
    for name, (verdict, text) in CASES.items():
        (HERE / f"{name}.receipt").write_text(text)
        lines.append(f"{name} {verdict}")
    (HERE / "expected.txt").write_text("\n".join(lines) + "\n")
    print(f"wrote {len(CASES)} receipts")


if __name__ == "__main__":
    main()
