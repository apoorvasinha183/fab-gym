# The agent loop: rules the model writes, scored by the simulator

Written 27 Oct 2026, before the code (tests in `crates/fabrule/tests/` and `agent/tests/`).
Everything here runs on the SMT2020 model of a fab. Agents propose, the simulator scores, a person signs.

## A rule

A rule is one Rust function the model writes:

```rust
pub fn key(c: &Cand, x: &Ctx) -> f64 { ... }
```

Whenever a free tool could start work, the simulator hands every candidate (a lot, or a batch of lots) to
`key`, and the tool starts the candidate with the smallest key. Ties keep the engine's own pick (today's
rule), and a NaN key counts as the largest.

`Cand` (one candidate, every field an `f64`): `is_batch`, `lots`, `priority`, `size_wafers`, `step`,
`steps_left`, `waited_minutes`, `setup_change` (1 or 0), `proc_minutes`, `work_left_minutes`,
`age_minutes` (now minus release), `cqt_slack_minutes` (minutes before a queue-time limit is breached,
1e9 when none runs), `is_default` (1 for the engine's own pick), `family` (0 when the shop names no family;
otherwise 1, 2, ... in the order the shop's `family` records first name them: in the two-family shop of
`docs/TWO-FAMILIES.md`, 1 is volume and 2 is engineering lots).

`Ctx` (the decision): `t` (minutes since the start), `queue` (how many candidates), `working`, `idle`,
`down` (the deciding tool group's tools), `lots_waiting`, `lots_finished`.

The model writes only the function, and may use `f64` arithmetic and the standard library's maths.
The source is refused before compiling if it holds `unsafe`, `extern`, an attribute, a file, network,
process, environment, thread or time path, `static mut`, or a macro that reads files or the environment
(`include!`, `include_str!`, `include_bytes!`, `env!`, `option_env!`, `asm!`, `global_asm!`).

## The sandbox

- The function is wrapped in a fixed harness and compiled with `rustc` to `wasm32-unknown-unknown`
  (no dependencies, so no build scripts or procedural macros run). Compiled modules are cached by
  the source's hash.
- `wasmtime` (36.0.19, the long-term-support line) loads the module only if it imports nothing and asks
  for at most 64 MiB of memory. It has no files, network, clock or randomness.
- Each decision has a fuel budget. A rule that runs out of fuel, traps or returns an index out of range
  falls back to today's pick for that decision, and the fault is counted.
- A rule whose faults exceed 1% of its decisions is not eligible to be chosen.

## Scoring

- The protocol of `docs/PROBLEM.md`: 24 hours of warm-up, a 3-day window, paired seeds, 95% intervals.
- Arms: today's rule, first in first out, shortest processing first, critical ratio, and the rule.
- The report gives the rule against today on the seven measures, the rule against each baseline on
  reward, the faults and decisions, and whether the rule is eligible.
- Seeds: training seeds are 100 and up. The held-out seeds are exactly 0 to 9, and only the final
  scoring uses them. The scorer refuses a training run that names a seed below 100.

## The loop

1. The question (and a scenario, when one is given) and the baselines' training scores go to the model.
2. Each generation the model writes rules. Each is checked, compiled and scored on training seeds;
   the model reads the scores, faults and compiler messages and writes the next generation.
3. The best eligible rules by training reward go to the final scoring, once, on the held-out seeds.
   Nothing scored on held-out seeds is ever sent to the model.
4. The result card quotes only the scorer's numbers, with each rule's source hash, the model's name
   and the seeds. It stays unsigned until a person signs it with `agent sign`, which refuses a card
   whose numbers no longer match its scorer output, and a card already signed.

The model is reached through an OpenAI-compatible chat endpoint (Baseten, or Meta's API). The key is read
from `~/.config/fab-gym/baseten.key` and is never printed or written anywhere. A stand-in model that
returns written rules in order runs the loop for tests.

Not in this step: the red-team role, the critic, the Lean certificate on the chosen run, and voice.
