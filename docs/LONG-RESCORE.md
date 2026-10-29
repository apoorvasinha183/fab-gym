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
  - the harness's built-in player was missing an import.
