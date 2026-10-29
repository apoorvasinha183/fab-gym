# Every policy, scored long (protocol long-v1)

Decided 29 Oct 2026. The founder asked how any result can be meaningful when a lot takes about 50 days and the
scored windows are 3 days. The answer: short windows measure flow (moves, waits, breaches) in a fab that starts full,
and they cannot measure cycle time or output from lots started in the window. PPO and the evolved rules were trained
and scored on 1 day of warm-up and a 3-day window, starting from SMT2020's lots in progress, before the fab settles
(about day 130). So every policy is scored again over a long window, and every measure is kept for comparison with
any later policy, Meta's agent included. On the SMT2020 model, a published model of a fab; not a real fab.

## The protocol, long-v1

- The shop: SMT2020's high-volume model as published (`data/smt2020/hvlm`), flat transport, as PPO was trained.
- Days 0 to 130: today's rule decides, whatever is scored. The fab fills from SMT2020's lots in progress and
  settles (WIP and cycle time level off after about day 130).
- Days 130 to 190: the policy decides every real choice (two or more lots a tool could take). Scored over this
  window.
- Seeds 0 to 9 (held out: no policy was trained or selected on them); each policy against today's rule on the same
  seed, with paired 95% intervals, Bonferroni over the policies.
- Twice: defect holds off (the published model), and on at PPO's training setting (120, 240, 60 minutes).
- Policies:
  - the built-in rules: today, FIFO, shortest processing first, critical ratio, random;
  - PPO (`results/rl-defects/ppo/policy.zip`);
  - E2's three evolved rules (`results/evolve-x4/rules/evolved-1..3.rs`).

## What is kept, per policy and seed (`runs.tsv`; registry `policies.json`)

- **Fast measures:**
  - reward (lots finished minus 0.01 per lot-hour waiting, the training reward);
  - moves, lots finished, lot-hours waiting, queue-time breaches.
- **Slow measures:**
  - cycle time in days (Little's law over the window);
  - wafers out a day, mean lots in the fab;
  - hot-lot cycle time.
- **Speed:**
  - decisions made;
  - wall seconds per decision, the simulation included;
  - milliseconds inside the policy's own code (Python players).

A new policy is scored by adding it to the same command with the same protocol name; nothing else changes.

## Tests (written before the code)

- `crates/fabsim/tests/env.rs`:
  - a built-in rule plays the window with today's rule in the warm-up, scoring as a run built that way by hand;
  - `fabsim env --auto NAME` reports the slow measures.
- `agent/tests/test_rl.py`: built-in, written and fixed players go through one harness, with every measure, the time
  per decision and the registry kept.
- **Changes while building:**
  - the first engine test used an empty window, which the scorer refuses, so it now builds the run by hand;
  - the harness's built-in player was missing an import;
  - E2's evolved rules 2 and 3 failed rustc (E0689, a method on a bare float literal): the rule exporter now writes
    every constant as f64 (`gp.rs`, test `a_rule_of_constants_alone_names_its_number_type`), and the three rule files
    were rewritten the same way. All three are constant keys, which never beat the default pick, so each plays
    today's rule exactly (e2-2 checked on seed 0: 523,444 decisions, none picked otherwise, the same moves). e2-2 and
    e2-3 are therefore not run again; e2-1 stands for all three;
  - a contest now picks up the runs it already kept and records a policy that cannot play, then goes on.

## Regret, decided 29 Oct by quiz: A, B, C and D, in that order (C and A first, then B and D)

- **C, the capacity ceiling** (`fabsim::bound`, `fabsim bound`; tests `crates/fabsim/tests/bound.rs`). SMT2020's
  high-volume model:
  - **expected ceiling 1,301.9 wafers a day**, set by Planar_FE_77 (2.17 tool-minutes a wafer, 2,824 tool-minutes
    a day after expected time down), with Planar_FE_79 at 1,311.8 and TF_FE_103 at 1,385.9 close behind;
  - **strict ceiling** (no time down) **1,429.9**, set by what is released.
  - Today's rule gets 1,246 out on seed 0 over days 130 to 190: about 56 below the expected ceiling.
  - The expected ceiling uses expected time down, so a run with less time down than expected can pass it. The
    earlier layout runs averaged 1,311.8 over days 60 to 150. A ceiling for each run from its own time down is the
    strict per-run version, to come with the runs' downtime. Saved: `results/long-rescore/ceiling.json`.

## Results, long-v1 (29 to 30 Oct; `results/long-rescore/`)

Means over seeds 0 to 9, days 130 to 190. Defects off; defects on differ by less than 1% in every measure.

| policy | wafers a day | cycle time, days | reward | queue-time breaches |
| --- | ---: | ---: | ---: | ---: |
| today | 1,263 | 59.6 | -23,860 | 15,444 |
| E2's evolved rules (= today) | 1,263 | 59.6 | -23,860 | 15,444 |
| critical ratio | 1,058 | 76.1 | -33,944 | 2,747 |
| shortest first | 668 | 130.2 | -39,892 | 3,475 |
| PPO | 660 | 141.2 | -42,361 | 3,554 |
| FIFO | 595 | 153.8 | -42,780 | 2,247 |
| random | 587 | 156.3 | -43,051 | 2,037 |

- Every policy but the evolved rules is worse than today's on every seed, by intervals far from zero.
- PPO, trained on 3-day windows, loses about half the output over a long window: it was never scored where its
  picks come back as cycle time.
- Today's rule trades queue-time breaches for output: about six times the breaches of the others.
- **Regret A** (best of this library on each seed, minus the policy's reward; `regret-ac.json`, `regret_ac.py`):
  today's rule is the best on every seed, so its A is 0 and A only ranks the rest: critical ratio 10,085 (95% 9,685 to
  10,485), shortest first 16,033, PPO 18,501, FIFO 18,921, random 19,191.
- **Regret C** (expected ceiling 1,301.9 minus wafers a day): today's rule 38.9 (95% 17.8 to 59.9) with defects off,
  33.6 (11.3 to 55.9) on; critical ratio 243.6; PPO 641.4. One run with defects off, two on, got more out than the
  expected ceiling (less time down than expected on those seeds), so C is a bound on average only. A ceiling for
  each run from its own time down is still to come.
- **Speed** (wall seconds per decision, the simulation included): built-in rules 0.27 to 0.47 ms, the sandboxed
  evolved rule 0.05 ms (its run counts every decision with today's rule), PPO 0.84 ms. The decision's own cost is a
  small part of these, except PPO's network.

