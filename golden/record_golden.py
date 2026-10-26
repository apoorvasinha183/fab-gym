"""Record golden files from the pre-existing Python reference engine.

The reference engine lives in Chetnova's private repository and is not part of Fab Gym. This
script runs it and writes plain-text files that the Rust simulator must reproduce exactly:

  pyrandom.txt          values from Python's random.Random seeded with strings
  toy/<name>.shop.txt   small hand-made shops (written here, new for Fab Gym)
  toy/<name>.log.txt    the reference engine's log for each toy shop
  smt2020.sha256        SHA-256 and line counts of logs on the SMT2020 model (the full logs
                        go to the --data folder, which git ignores)

Run with the reference engine's Python:
  .../Chetnova/.venv/bin/python golden/record_golden.py --data data/golden

Floats in logs are written as the 16 hex digits of their IEEE-754 bits, so a match is exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import struct
import sys
import time
from pathlib import Path

from chetnova.org import jobshop as J  # the private reference engine
from chetnova.orgpacks import fab as F

HERE = Path(__file__).resolve().parent
STATES = ("productive", "standby", "scheduled down", "unscheduled down")


def hx(x) -> str:
    return struct.pack(">d", float(x)).hex()


def r(x) -> str:
    """A float as Python's shortest round-trip text; Rust parses it to the same bits."""
    return repr(float(x))


def opt(x, f=r) -> str:
    return "-" if x is None else f(x)


# ------------------------------------------------------------------ shop text


def shop_text(shop: dict) -> str:
    out = ["fabgym-shop 1"]
    lo, hi = (list(shop.get("transport") or [0.0, 0.0]) + [0.0, 0.0])[:2]
    out.append(f"transport\t{r(lo)}\t{r(hi)}")
    if shop.get("release_rule"):
        out.append(f"cap\t{int(shop['release_rule']['cap'])}")
    for tp in shop.get("probes") or []:
        out.append(f"probe\t{r(tp)}")
    for name, g in shop["groups"].items():
        bd = g.get("breakdown")
        bd = bd if bd and float(bd.get("mttf", 0)) > 0 else None
        out.append(
            "\t".join(
                [
                    "group",
                    name,
                    str(int(g.get("count", 1))),
                    r(g.get("load", 0.0)),
                    r(g.get("unload", 0.0)),
                    opt(g.get("batch_wait")),
                    opt(bd and bd["mttf"]),
                    opt(bd and bd["mttr"]),
                ]
            )
        )
        for key, m in (g.get("setups") or {}).items():
            out.append(f"setup\t{key}\t{r(m)}")
        for kind in ("pm", "pm_pieces"):
            for pm in g.get(kind) or []:
                tag = "pm" if kind == "pm" else "pmp"
                out.append(
                    f"{tag}\t{r(pm['every'])}\t{r(pm['lo'])}\t{r(pm['hi'])}\t{opt(pm.get('first'))}"
                )
        for s, e in g.get("down") or []:
            out.append(f"down\t{r(s)}\t{r(e)}")
    for rname, steps in shop["routes"].items():
        out.append(f"route\t{rname}")
        for st in steps:
            b = st.get("batch")
            rw = st.get("rework")
            cq = st.get("cqt")
            out.append(
                "\t".join(
                    [
                        "step",
                        st["group"],
                        st.get("per", "lot"),
                        r(st["time"]),
                        r(st.get("spread") or 0.0),
                        opt(b and b[0]),
                        opt(b and b[1]),
                        opt(st.get("interval")),
                        opt(st.get("batch_wait")),
                        st.get("setup") or "-",
                        opt(st.get("sample")),
                        opt(rw and rw["to"], lambda v: str(int(v))),
                        opt(rw and rw["p"]),
                        opt(cq and cq["to"], lambda v: str(int(v))),
                        opt(cq and cq["limit"]),
                    ]
                )
            )
    for d in shop.get("lots") or []:
        out.append(
            "\t".join(
                [
                    "lot",
                    d["id"],
                    d["route"],
                    str(int(d.get("size", 25))),
                    r(d.get("priority", 10)),
                    r(d.get("start", 0.0)),
                    str(int(d.get("step", 0))),
                ]
            )
        )
    for k, rel in enumerate(shop.get("releases") or []):
        out.append(
            "\t".join(
                [
                    "release",
                    rel["route"],
                    str(int(rel.get("size", 25))),
                    r(rel.get("priority", 10)),
                    r(rel["every"]),
                    r(rel.get("first", 0.0)),
                    opt(rel.get("count"), lambda v: str(int(v))),
                    rel.get("prefix", "R" + str(k)),
                ]
            )
        )
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ log text


def log_text(res: dict) -> str:
    out = ["fabgym-log 1"]
    for s in res["states"]:
        out.append(f"state\t{s['tool']}\t{hx(s['time'])}\t{s['state']}\t{s['why'] or '-'}")
    for lid, lot in res["lots"].items():
        out.append(f"lot\t{lid}\t{hx(lot['release'])}\t{opt(lot['done'], hx)}")
        for st in lot["steps"]:
            out.append(
                f"step\t{st['step']}\t{st['tool']}\t{hx(st['arrive'])}\t{hx(st['start'])}\t{hx(st['end'])}"
            )
    for b in res["breaches"]:
        out.append(f"breach\t{b['lot']}\t{b['from']}\t{b['to']}\t{hx(b['waited'])}")
    for name, mins in res["tools"].items():
        out.append("tool\t" + name + "\t" + "\t".join(hx(mins.get(s, 0.0)) for s in STATES))
    for g, v in res["groups"].items():
        out.append(f"group\t{g}\t{hx(v['busy'])}\t{hx(v['wait'])}\t{v['visits']}")
    for row in res["release_log"]:
        wb = row["wip_before"]
        out.append(
            f"release\t{row['id']}\t{hx(row['scheduled'])}\t{opt(row['released'], hx)}\t{'-' if wb is None else wb}"
        )
    for p in res["probes"]:
        out.append(
            f"probe\t{hx(p['t'])}\t{p['finished']}\t{p['wip']}\t{p['moves']}\t{p['waiting']}"
            f"\t{hx(p['wait_lot_minutes'])}\t{hx(p['wip_lot_minutes'])}"
        )
    c = res["counters"]
    out.append(f"counters\t{c['finished']}\t{c['waiting']}\t{hx(c['wait_lot_minutes'])}")
    out.append(f"until\t{hx(res['until'])}")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ toy shops (new for Fab Gym)


def toy_shops() -> dict[str, tuple[dict, int, float]]:
    """Small shops that exercise every rule of the engine. Values are made up."""
    tiny = {
        "groups": {"A": {"count": 1}},
        "routes": {"r": [{"group": "A", "time": 10.0, "per": "lot"}]},
        "lots": [
            {"id": "L1", "route": "r", "size": 25, "priority": 10, "start": 0.0},
            {"id": "L2", "route": "r", "size": 25, "priority": 10, "start": 0.0},
        ],
    }
    mixed = {
        "groups": {
            "Litho": {
                "count": 2,
                "load": 1.0,
                "unload": 1.0,
                "setups": {">S1": 20.0, ">S2": 15.0, "S1>S2": 30.0, "S2>S1": 25.0},
                "pm": [{"every": 600.0, "lo": 20.0, "hi": 40.0}],
                "breakdown": {"mttf": 900.0, "mttr": 45.0},
            },
            "Furnace": {"count": 1, "load": 2.0, "unload": 2.0, "batch_wait": 120.0},
            "Etch": {
                "count": 2,
                "pm_pieces": [{"every": 400.0, "lo": 30.0, "hi": 60.0}],
                "breakdown": {"mttf": 1500.0, "mttr": 60.0},
            },
            "Metro": {"count": 1, "down": [[300.0, 420.0]]},
            "Single": {"count": 1, "pm": [{"every": 700.0, "lo": 10.0, "hi": 10.0, "first": 50.0}]},
        },
        "routes": {
            "p1": [
                {"group": "Litho", "time": 30.0, "spread": 3.0, "per": "lot", "setup": "S1"},
                {"group": "Furnace", "time": 200.0, "spread": 10.0, "per": "batch", "batch": [50, 100]},
                {"group": "Etch", "time": 1.2, "spread": 0.1, "per": "piece", "interval": 0.8,
                 "cqt": {"to": 3, "limit": 60.0}},
                {"group": "Metro", "time": 15.0, "per": "lot", "sample": 0.5},
                {"group": "Litho", "time": 25.0, "per": "lot", "setup": "S2",
                 "rework": {"to": 2, "p": 0.1}},
                {"group": "Single", "time": 12.0, "spread": 2.0, "per": "lot"},
                {"group": "Etch", "time": 0.9, "per": "piece"},
            ],
            "p2": [
                {"group": "Etch", "time": 1.0, "spread": 0.2, "per": "piece"},
                {"group": "Furnace", "time": 180.0, "per": "batch", "batch": [25, 75],
                 "batch_wait": 60.0},
                {"group": "Litho", "time": 20.0, "per": "lot", "setup": "S2",
                 "cqt": {"to": 3, "limit": 45.0}},
                {"group": "Single", "time": 8.0, "per": "lot", "sample": 0.7},
                {"group": "Metro", "time": 10.0, "spread": 1.0, "per": "lot"},
            ],
        },
        "lots": [
            {"id": "W1", "route": "p1", "size": 25, "priority": 10, "start": 0.0, "step": 2},
            {"id": "W2", "route": "p1", "size": 25, "priority": 20, "start": 0.0, "step": 4},
            {"id": "W3", "route": "p2", "size": 25, "priority": 10, "start": 0.0, "step": 1},
            {"id": "W4", "route": "p2", "size": 25, "priority": 10, "start": -30.0, "step": 0},
        ],
        "releases": [
            {"route": "p1", "size": 25, "priority": 10, "every": 37.0, "first": 0.0,
             "count": 60, "prefix": "P1"},
            {"route": "p2", "size": 25, "priority": 10, "every": 53.0, "first": 5.0,
             "count": 40, "prefix": "P2"},
            {"route": "p1", "size": 25, "priority": 20, "every": 400.0, "first": 100.0,
             "count": 5, "prefix": "HOT"},
        ],
        "transport": [5.0, 10.0],
    }
    capped = dict(mixed, release_rule={"cap": 12}, probes=[0.0, 600.0, 1440.0, 2880.0])
    return {"tiny": (tiny, 0, None), "mixed": (mixed, 7, 4320.0), "capped": (capped, 3, 4320.0)}


# ------------------------------------------------------------------ random vectors


def pyrandom_text() -> str:
    out = ["fabgym-pyrandom 1"]
    for s in ["0/lot/L1", "7/tool/Litho#1", "0/lot/wip.0.Init_Lot_3_2", "123/break/X#9/4410", ""]:
        g = random.Random(s)
        vals = [g.random() for _ in range(3)]
        vals += [g.uniform(2.5, 7.5), g.expovariate(1.0 / 35.28), g.random()]
        out.append(s + "\t" + "\t".join(hx(v) for v in vals))
    for data in [b"", b"abc", b"0/lot/L1"]:
        out.append("sha512\t" + data.decode() + "\t" + hashlib.sha512(data).hexdigest())
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="folder for large logs (ignored by git)")
    a = ap.parse_args()
    data = Path(a.data)
    data.mkdir(parents=True, exist_ok=True)
    (HERE / "toy").mkdir(exist_ok=True)

    (HERE / "pyrandom.txt").write_text(pyrandom_text())

    for name, (shop, seed, until) in toy_shops().items():
        (HERE / "toy" / f"{name}.shop.txt").write_text(shop_text(shop))
        res = J.run(shop, seed=seed, until=until, keep="all")
        (HERE / "toy" / f"{name}.log.txt").write_text(log_text(res))
        meta = {"seed": seed, "until": until}
        (HERE / "toy" / f"{name}.run.json").write_text(json.dumps(meta) + "\n")

    rec = F.compile_fab().session.record
    shop = F.shop(rec)
    st = shop_text(shop)
    (data / "smt2020.shop.txt").write_text(st)
    lines = [f"shop\t{hashlib.sha256(st.encode()).hexdigest()}\t{st.count(chr(10))}"]
    timing = []
    for seed, days in [(0, 1), (1, 1), (2, 1), (0, 3)]:
        until = 1440.0 * days
        t0 = time.perf_counter()
        res = J.run(shop, seed=seed, until=until, keep="all")
        secs = time.perf_counter() - t0
        lt = log_text(res)
        name = f"smt2020.seed{seed}.{days}d.log.txt"
        (data / name).write_text(lt)
        lines.append(f"{name}\t{hashlib.sha256(lt.encode()).hexdigest()}\t{lt.count(chr(10))}")
        timing.append(f"seed {seed}, {days} day(s): {secs:.2f} s (keep=all)")
    (HERE / "smt2020.sha256").write_text("\n".join(lines) + "\n")
    (HERE / "reference-timing.txt").write_text(
        "Pre-existing Python reference engine, one core, this machine:\n" + "\n".join(timing) + "\n"
    )
    print("\n".join(lines))
    print("\n".join(timing))


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    main()
