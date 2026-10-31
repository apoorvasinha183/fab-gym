"""The supervisor, a toy experiment (docs/SUPERVISOR-TOY.md): the model's side and the experiment's driver.

`fabsim supervise ... --arm ask` stops at each look, writes what the supervisor may see as one JSON line and waits for
the settings to try. Here a model (Muse Spark, contributor, low effort) reads that view and proposes up to three
settings with a reason each; the simulator tries them on copies with fresh luck and keeps the best. The other arms
(today, best fixed, the simulator alone) need no model. On a teaching fab of our own and the SMT2020 testbed; not a
real fab. Agents propose, the simulator scores, a person signs.

    python3 -m agent.supervise toy --out results/supervisor-toy      (the arms that need no model)
    python3 -m agent.supervise toy --out results/supervisor-toy --ask (adds the model's arm; spends, capped)
"""

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FABSIM = ROOT / "target" / "release" / "fabsim"
RULE_WORDS = {"today": "today's rule", "fifo": "first come first served", "spt": "shortest first", "cr": "critical ratio"}
# two-sided 95% t quantiles by degrees of freedom (the normal's 1.96 beyond 30)
T975 = [12.706, 4.303, 3.182, 2.776445, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
        2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]

SYSTEM = """You supervise a small chip fab in a simulator. Once a day you see how the fab has been doing since your last
look, and you pick up to three settings worth trying for the next stretch. A setting is the rule the floor uses to
choose the next lot, and a cap on how many lots may be inside the fab at once. The simulator tries your settings, and
the one you have now, on copies of the fab with fresh luck, and keeps the best. Look for patterns: lines growing at a
group, machines down, machines close to their wear limit (they break after so many wafers, so pushing more work through
them makes them break sooner). Reply with JSON only:
{"settings": [{"rule": "today|fifo|spt|cr", "cap": null or a number from the list, "why": "one short sentence"}]}"""


def setting_name(s):
    rule, cap = s
    return f"{RULE_WORDS.get(rule, rule)}, {'no cap' if cap is None else f'cap {cap}'}"


def view(state, grid):
    """What the model is shown at a look: the past and the present only, in plain words, and the settings to choose from."""
    lines = [f"Day {state['t'] / 1440:.1f} of the run. Now: {setting_name(state['current'])}.",
             f"{state['lots_inside']} lots inside. Since the last look: {state['lots_finished']} lots finished, "
             f"{state['lot_hours_waiting']:.0f} lot-hours spent waiting.", "Machine groups now:"]
    for name, tools, down, queue, worn in state["groups"]:
        wear = f", most worn machine {round(worn * 100)}% of the way to its wear limit" if worn > 0 else ""
        lines.append(f"- {name}: {down} of {tools} down, {queue} lots waiting{wear}")
    lines.append("Settings you can choose from:")
    lines += [f"- {setting_name(s)}" for s in grid]
    return "\n".join(lines)


def parse_reply(text, grid, most=3):
    """The model's reply as up to `most` valid settings from `grid`, each with its reason; anything else dropped."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for item in data.get("settings", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        s = [item.get("rule"), item.get("cap")]
        if s in grid and s not in [x for x, _ in out]:
            out.append((s, str(item.get("why", ""))[:200]))
        if len(out) == most:
            break
    return out


def paired(a, b):
    """Mean of a - b and its two-sided 95% t interval."""
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    m = sum(d) / n
    if n < 2:
        return m, m, m
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
    t = T975[n - 2] if n - 2 < len(T975) else 1.96
    h = t * sd / math.sqrt(n)
    return m, m - h, m + h


# ---------------------------------------------------------------- the driver

def _args(shop, seed, plan, caps, ov, arm, out):
    a = [str(FABSIM), "supervise", str(shop), "--seed", str(seed), "--warmup", str(plan["warmup"]), "--window", str(plan["window"]),
         "--every", str(plan["every"]), "--horizon", str(plan["horizon"]), "--copies", str(plan["copies"]),
         "--caps", ",".join("none" if c is None else str(c) for c in caps), "--arm", arm, "--out", str(out)]
    if ov:
        a += ["--overrides", str(ov)]
    return a


def run_arm(shop, seed, plan, caps, ov, arm, out):
    subprocess.run(["nice", "-n", "10", *_args(shop, seed, plan, caps, ov, arm, out)], check=True, capture_output=True)
    return json.loads(Path(out).read_text())


def run_ask(shop, seed, plan, caps, ov, out, model, log):
    """The model's arm: answer each look from the model; what it was shown and said goes to `log`."""
    p = subprocess.Popen(["nice", "-n", "10", *_args(shop, seed, plan, caps, ov, "ask", out)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        msg = json.loads(line)
        if "look" not in msg:
            continue
        shown = view(msg["look"], msg["grid"])
        try:
            reply = model.complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": shown}])
        except Exception as e:  # noqa: BLE001 - a failed call keeps the current setting, and is logged
            reply = f"(no answer: {e})"
        picks = parse_reply(reply, msg["grid"])
        log.write(json.dumps({"seed": seed, "t": msg["look"]["t"], "shown": shown, "reply": reply, "picks": picks}) + "\n")
        log.flush()
        p.stdin.write(json.dumps({"settings": [s for s, _ in picks]}) + "\n")
        p.stdin.flush()
    p.wait()
    if p.returncode:
        raise RuntimeError(f"fabsim supervise ended with {p.returncode}")
    return json.loads(Path(out).read_text())


TOY = {"shop": ROOT / "data" / "supervisor" / "toy.fab.txt", "kinds": {"clock": ROOT / "data" / "supervisor" / "clock.json", "wear": ROOT / "data" / "supervisor" / "wear.json"},
       "caps": [None, 10, 15, 20, 25, 30], "warmup": 2, "window": 10, "copies": 3, "train": range(100, 105), "test": range(0, 10), "every": [24, 48]}
SMT = {"shop": ROOT / "data" / "smt2020" / "hvlm", "kinds": {"clock": None, "wear": ROOT / "data" / "supervisor" / "smt-wear.json"},
       "caps": [None, 1800, 2100, 2400, 2700, 3000], "warmup": 130, "window": 10, "copies": 2, "train": range(100, 102), "test": range(0, 2), "every": [24]}


def plan(cfg, every):
    return {"warmup": cfg["warmup"], "window": cfg["window"], "every": every, "horizon": every + 24, "copies": cfg["copies"]}


def name(s):
    return f"{s[0]}:{'none' if s[1] is None else s[1]}"


def experiment(cfg, out, ask=None, workers=4):
    """A, B (trained), C at each look interval, and D when `ask` holds a model; every run's result kept in `out`."""
    from concurrent.futures import ThreadPoolExecutor
    out = Path(out)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    grid = [[r, c] for r in ["today", "fifo", "spt", "cr"] for c in cfg["caps"]]
    p24 = plan(cfg, cfg["every"][0])

    def job(kind, seed, arm, p, tag):
        f = out / "runs" / f"{kind}-{tag}-{seed}.json"
        if not f.is_file():
            run_arm(cfg["shop"], seed, p, cfg["caps"], cfg["kinds"][kind], arm, f)
        return json.loads(f.read_text())

    res = {}
    with ThreadPoolExecutor(workers) as pool:
        for kind in cfg["kinds"]:
            # B: the best fixed setting on the training seeds
            futs = {name(s): [pool.submit(job, kind, sd, f"fixed:{s[0]}:{'none' if s[1] is None else s[1]}", p24, "train-" + name(s).replace(":", "_")) for sd in cfg["train"]] for s in grid}
            train = {k: sum(f.result()["value"] for f in v) / len(v) for k, v in futs.items()}
            best = max(train, key=train.get)
            res[kind] = {"best_fixed": best, "train": train, "arms": {}}
            arms = {"today": ("today", p24), "best-fixed": ("fixed:" + best, p24)}
            for ev in cfg["every"]:
                arms[f"sim-{ev}h"] = ("sim", plan(cfg, ev))
            for a, (arm, p) in arms.items():
                fs = [pool.submit(job, kind, sd, arm, p, a) for sd in cfg["test"]]
                res[kind]["arms"][a] = [f.result() for f in fs]
    if ask is not None:
        model, log = ask
        for kind in cfg["kinds"]:
            for ev in cfg["every"]:
                rs = []
                for sd in cfg["test"]:
                    f = out / "runs" / f"{kind}-model-{ev}h-{sd}.json"
                    rs.append(json.loads(f.read_text()) if f.is_file() else run_ask(cfg["shop"], sd, plan(cfg, ev), cfg["caps"], cfg["kinds"][kind], f, model, log))
                res[kind]["arms"][f"model-{ev}h"] = rs
    return res


def summarise(res):
    """Paired differences against today and against the best fixed setting, and the thesis: the simulator arm's gain over
    the best fixed setting under wear, less the same under clock."""
    out = {}
    for kind, r in res.items():
        a = r["arms"]
        base, fixed = a["today"], a["best-fixed"]
        rows = {}
        for arm, runs in a.items():
            row = {"wafers_per_day": sum(x["wafers_per_day"] for x in runs) / len(runs), "cycle_days": sum(x["cycle_days"] for x in runs) / len(runs)}
            if arm != "today":
                row["vs_today"] = paired([x["wafers_per_day"] for x in runs], [x["wafers_per_day"] for x in base])
            if arm not in ("today", "best-fixed"):
                row["vs_best_fixed"] = paired([x["wafers_per_day"] for x in runs], [x["wafers_per_day"] for x in fixed])
                row["choices"] = sorted({tuple(l["chosen"]) for x in runs for l in x["looks"]}, key=str)
            rows[arm] = row
        out[kind] = {"best_fixed": r["best_fixed"], "arms": rows}
    if "clock" in res and "wear" in res:
        th = {}
        for arm in res["wear"]["arms"]:
            if arm.startswith(("sim", "model")) and arm in res["clock"]["arms"]:
                g = lambda k: [x["wafers_per_day"] - y["wafers_per_day"] for x, y in zip(res[k]["arms"][arm], res[k]["arms"]["best-fixed"])]
                th[arm] = paired(g("wear"), g("clock"))
        out["thesis_gain_wear_minus_clock"] = th
    return out


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("which", choices=["toy", "smt2020"])
    a.add_argument("--out", required=True)
    a.add_argument("--ask", action="store_true", help="add the model's arm (spends, capped)")
    a.add_argument("--cap-usd", type=float, default=1.0)
    o = a.parse_args(argv)
    cfg = TOY if o.which == "toy" else SMT
    ask = None
    if o.ask:
        from agent import spend
        from agent.fabgym_agent import HttpModel
        from agent.helper import PRESETS
        p = PRESETS["meta"]
        meter = spend.Meter(spend.price("meta", p["model"]), cap_usd=o.cap_usd, path=Path(o.out) / "spend.json")
        model = HttpModel(p["base_url"], p["model"], key_file=p["key_file"], max_tokens=2000, reasoning_effort="low", meter=meter, timeout=120)
        Path(o.out).mkdir(parents=True, exist_ok=True)
        ask = (model, open(Path(o.out) / "model-log.jsonl", "a"))
    res = experiment(cfg, o.out, ask)
    summary = summarise(res)
    Path(o.out, "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1)[:6000])
    if ask:
        print("model spend:", ask[0].meter.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
