# A gym for reinforcement learning, with defects in the fab

Written 29 October 2026, before the code. Decided by quiz the same day (`~/HACKATHON-README.md`): reinforcement
learning plus defects; defects as holds and rework; training on the Linux server after E2. From the SMT2020 testbed, a published set of a fab's tool groups, routes and times; no real fab and no real data. Agents propose, the simulator scores, a person signs.

## The question

Fab Gym already trains two kinds of learner on the simulator: Muse Spark Open writing dispatch rules as code, and
E2's evolutionary search. Can a third kind, a policy trained by reinforcement learning one dispatch decision at a
time, beat today's rule on seeds it never saw, when inspections find defects that put tools and lots on hold? And
how does it compare with the other two learners on the same seeds?

## Defects in the fab: holds on top of rework

The SMT2020 testbed already sends a lot back to an earlier step at its rework steps (`RWKSTEP`, with the published
probability; `engine.rs`). With defects switched on, each rework is also a **finding** against the tool that just
did the step:

1. **The tool is held.** It goes down for `hold_tool_minutes`, starting when its current work ends (as a calendar
   down does). Its state is `unscheduled down`, so the floor and the scorer count it as down.
2. **The lots it touched are held.** Every other lot that finished this step on the same tool within the last
   `lookback_minutes`, and has not yet started another step, is held for `hold_lot_minutes`: it stays in its
   queue but cannot be chosen until the hold ends. Its waiting time keeps counting.
3. Nothing else changes: the reworked lot goes back as before, and no draw is added or moved, so every random
   stream stays as it was.

A shop switches defects on with one record (all three numbers assumed, and labelled so wherever they are shown):

```
defects	hold_tool_minutes	lookback_minutes	hold_lot_minutes
defects	120	240	60
```

Without the record nothing differs from today: every golden log and every committed result stays the same. Yield
and scrap stay out of the model, so a defect's cost is measured in moves, waiting and lots finished.

## The environment: one decision at a time

`fabsim env SHOP --seed N [--warmup DAYS] [--window DAYS] [--defects H,L,R] [--auto]` runs one episode and speaks JSON lines on standard input
and output, so any language can drive it without a build step:

- `SHOP` is a shop file or the SMT2020 folder. `--defects 120,240,60` adds the `defects` record to a shop that has
  none. `--auto` answers every decision with the engine's pick and prints only the last line (for checks).
- Today's rule decides during the warm-up (default 1 day). In the window (default 3 days), at every decision with
  **two or more candidates**, the environment writes one observation and waits for one action. A decision with one
  candidate is taken without asking.
- An **observation** is `{"t", "group", "tools": {working, idle, down}, "totals": {finished, waiting,
  wait_lot_minutes}, "cands": [...], "default", "reward"}`. `cands` holds at most 8 candidates in the engine's order
  (the engine's own pick first, then the rest as the engine lists them), each with the fields a written rule sees
  (`docs/AGENT.md`), plus `held_tools` for the group (tools of the group on a defect hold now).
- An **action** is `{"action": k}`: the index of a listed candidate. An index out of range, or a line that is not
  an action, takes the engine's own pick and is counted in `fallbacks`.
- **Reward** for each step is the change in the scorer's reward since the previous observation: lots finished
  minus 0.01 per lot-hour waiting (`docs/PROBLEM.md`). The last line, `{"done": true, "score": {...}, "reward",
  "decisions", "fallbacks"}`, carries the window's score from the same code `fabsim score` uses and the last
  step's reward, so **an episode's rewards sum to the window's reward exactly**.

`agent/fabgym_env.py` wraps it as a Gymnasium environment (`FabGymEnv`): the observation is a fixed vector (8
candidates by their fields, scaled, a mask of real candidates, and the group's tools and totals), the action
space is `Discrete(8)`, and an action on an empty slot is masked to the engine's pick.

## The learner and the contest

- **PPO** (stable-baselines3) trains on seeds 100 to 199 of today's shop with defects on. It runs on the Linux
  server after E2 ends, niced, with at most 4 workers. The download (Gymnasium, stable-baselines3, CPU PyTorch,
  from PyPI into the repository's environment) is asked with its sizes before it happens.
- **The contest** is scored once, on held-out seeds 0 to 9, with defects on, on today's floor: today's rule, the
  best rule Muse Spark Open writes in the agent loop, E2's best rule, and the PPO policy. Each contestant runs
  through the same environment, so the four are scored by one piece of code. Each is reported against today's
  rule as a paired difference with a 95% interval (Bonferroni over the three), with a verdict of better, worse or
  no clear effect, and the same card again with defects off.
- What a policy learned is described only from what it does (for example, how often it picks a lot other than the
  engine's own pick, and in which groups), never as a claim about real fabs.

## Deliverables, in order

1. This spec and its tests, committed before any code.
2. Defect holds in the engine, behind the `defects` record.
3. `fabsim env`, the JSON-lines environment.
4. `agent/fabgym_env.py`, the Gymnasium wrapper (after the download is approved).
5. PPO training on the server, after E2.
6. The contest card, on the floor page's numbers view and in `results/rl-defects/`.

## Tests (`crates/fabsim/tests/defects.rs`, `crates/fabsim/tests/env.rs`, `agent/tests/test_env.py`)

1. Without a `defects` record, a run's event log is byte for byte the same as before (the golden files pass).
2. With defects on, every rework puts the tool that did the step into `unscheduled down` for `hold_tool_minutes`
   (starting after its current work), and no lot is started on it before then.
3. With defects on, a lot that finished the same step on the same tool within `lookback_minutes` before a finding
   is never a candidate until `hold_lot_minutes` after the finding; lots outside the lookback are never held.
4. With defects on, every lot's random draws are the same as with defects off (the reworks happen at the same
   lots and steps when the order of work is the same; checked on a shop where holds cannot reorder work).
5. `fabsim env` answered with the engine's own pick at every step gives exactly the window score `fabsim score`
   gives today's rule on the same seed, with defects on and off.
6. The rewards of an episode sum to the window's reward within 1e-9.
7. Only decisions in the window with two or more candidates are asked; an out-of-range action or a bad line falls
   back to the engine's pick and is counted.
8. `FabGymEnv` returns observations of a fixed shape, masks empty slots, and an episode of engine picks scores the
   same as test 5.
9. `fabrule env RULE.rs SHOP` plays a written rule (an E2 winner, or a rule Muse Spark Open writes) through the
   same episode code as `fabsim env` (`fabsim::gym`); today's rule written out scores exactly as the engine's own
   pick, with no faults.

## Changes

- 29 Oct, test 2 before its code passed: it found reworks from each lot's next started step, which misses a
  rework near the run's end whose lot has not started again. It now checks that every rework the trace shows
  has a hold, that every hold's lot did that step on that tool at that moment and did not move on, and that
  there is one hold per tool and moment. The rule tested is unchanged.
- 29 Oct, before the contest's code: written rules (E2's winners now, the model's when its key is in) enter the
  contest through `fabrule env`, which shares the episode loop with `fabsim env` (moved into `fabsim::gym`), so
  every contestant is still scored by one piece of code. Test 9 added. E2's rules were bred for money a day with
  two families at ×4; here they play today's single-family fab with defects, which the card says.
- 29 Oct, after the contest, at the founder's question on how the defect rates are justified: how often a finding
  happens follows SMT2020's published rework rates; the three hold lengths are ours and assumed. Decided by quiz: a
  Defect holds dial (off, ×0.5, ×1, ×2 of the three lengths) on the page's Try a change, and the held-out contest
  rerun at ×0.5 (60, 120, 30) and ×2 (240, 480, 120) so the card says whether PPO's verdict holds. Test in
  `crates/fabsim/tests/dials.rs`, before the code.
