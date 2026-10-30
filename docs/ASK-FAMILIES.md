# Ask the fab, with two families

Written 28 October 2026, before the code. Extends `docs/ASK.md` and `docs/TWO-FAMILIES.md`. From the SMT2020 testbed,
with a layout of our own design; not a real fab, not real data. Agents propose, the simulator scores, a person
signs.

## What a person does

On the floor page, a person types a question ("Prototype orders double next quarter. Do we give them their own wing
or put them first in line?"). The page shows the scenario the model wrote, each value marked said (in the question)
or assumed (with its range), then the simulator's answer with intervals, then plays the chosen setup on the floor
with family B's lots in their own colour.

Decided by quiz on 28 October (`~/HACKATHON-README.md`): the question is turned into a scenario by **Muse Spark Open
on Baseten**; a **helper on this Mac** holds the key, asks the model, checks the answer, runs the simulator
natively and serves the page. Until the founder's key is in `~/.config/fab-gym/baseten.key`, the helper answers
from recorded example answers written by us, marked "example answer, not from a model", and a person can edit the
scenario text by hand and run it.

## 1. The scenario text gains two families (`crates/fabsim/src/scenario.rs`)

New records, off unless present (every `fabgym-scenario 1` file written before parses and scores as before):

    family      share   <x>                          said|assumed
    candidate   <name>  floor    share|wing|copies
    candidate   <name>  policy   today|bfirst|cap|reserve|qualify

- `family share x` turns the scenario into a two-family question: family B is SMT2020's engineering lots at x
  times the published 20 lots a release (`twofam::EngLots`), 0.25 ≤ x ≤ 16.
- Today's fab in a two-family question is the yardstick: floor `share`, policy `today`. A candidate's `floor` and
  `policy` default to those. `floor` and `policy` are refused in a scenario without `family`.
- Floors are those of `docs/TWO-FAMILIES-SWEEP.md`: copies of the 3 most contested groups, one tool each, in a wing
  on pad P3 or in the halls. Policies are P0 to P4 with the sweep's cap and policy groups.
- Shocks and the other candidate kinds (rule, cap, spare, demand) apply as before, after the floor and policy.
- A sweep may also run over `family share` (field `value`) when the share is assumed.

## 2. The scorer, for two families (`crates/fabsim/src/score.rs`)

- Protocol for a two-family question: 120 days of warm-up, a 120-day window (days 120 to 240), seeds 0 to 9 unless
  given, every arm on the same seeds; family B's lots drawn with seed 1, the same for every arm.
- Floors are laid out by the optimiser at its full setting (`layout::Config::realistic()`), once per share and floor,
  and cached on disk by the hash of the shop text and the floor (`--layout-cache DIR`).
- Measures, each with its paired interval and verdict, Bonferroni over the candidates: **money a day** at the
  central prices (`money::PriceGrid`), family A's wafers out a day, family B's lots out, family B's mean cycle time
  (days from scheduled arrival), and the measures the scorer already reports. The best candidate is the one with
  the highest money lower bound among those better than today; if none is better, today stands.
- The JSON report gains, per arm, the shop it ran (as `fabgym-shop 1` text) and the extra areas for copies (the
  original group's area in the halls; `P3 wing` for a wing), so the page can play that arm.

## 3. The question to a scenario (`agent/ask.py`)

- The model gets: what the fab is (plain words, no claim of a real fab), the record types above and those of
  `docs/ASK.md`, the tool groups by plain name with their ids, the five policies and three floors in a sentence each,
  and the rule that every value is said or assumed with a range. It answers with JSON only.
- The JSON is checked before anything runs: known records only; known groups only; values in their ranges; at most
  six candidates; every assumed value has a range that holds it; no `floor` or `policy` without `family`. A refused
  answer is shown with its reasons and nothing runs.
- The checked JSON becomes scenario text; the text is also shown and can be edited and run by hand.
- Recorded example answers (`agent/examples/ask/*.json`), each marked `"example": true`, stand in for the model
  until the key is in place. Nothing shown as a model's answer comes from them.

## 4. The helper (`agent/helper.py`)

- `python3 -m agent.helper [--port 8766] [--smt2020 DIR]` serves `web/` and an API on 127.0.0.1 only.
- `POST /api/ask {question}` and `POST /api/run {scenario}` start a job; `GET /api/job/ID` gives its stage (asking,
  checking, laying out, simulating, done or failed), the scenario, the checks and, when done, the report.
- One job at a time; the simulator runs as `fabsim score` with 4 threads, niced. The key is read from its file,
  never logged, never sent to the page.
- With no key: `ask` answers from the example whose question matches exactly, else says that no model is
  connected and offers the examples and the editor.

## 5. The page (`web/`)

- An Ask panel: a question box, the examples, the stage, the scenario (said and assumed values in two styles), the
  result card (each candidate against today: money a day, family A wafers, family B cycle time, each with its
  interval and verdict), and "Show on the floor" for any arm.
- The floor plays the chosen arm: its shop loaded into the page's simulator, family B's lots drawn in their own
  colour, copies as groups in their halls, a wing as a hall of its own, P1 as a choice in the page's simulator.
- Every card says "from the SMT2020 testbed" and "Real-fab effect: cannot say".

## Tests

- `crates/fabsim/tests/ask_families.rs`: old scenarios unchanged (parse, text, score on the toy); the new records
  round-trip; refusals (floor without family, share out of range, said share swept); arms of a two-family scenario
  build the expected shops (copies, wing place, cap, quals); scoring a small two-family scenario is deterministic,
  carries money and the arm's shop text; the best candidate rule.
- `agent/tests/test_ask.py`: the checker refuses each listed fault; each example becomes the expected scenario text;
  the helper with no key answers an example question and refuses another, never exposes the key file's contents,
  and runs a hand-edited scenario end to end with a small protocol.
- `web/tests/ask.test.mjs`: the page's result card and said/assumed rendering from a recorded report; family B
  colour by route; a wing hall appears when the arm has one.

## Changes

- 28 Oct, found in the browser: a laid-out shop marks the hoist's start as "no bay" with the largest 64-bit number,
  which the page's 32-bit WebAssembly could not read. A bay too large for the platform now reads as "no bay"
  (`shop::read_bay`); what a 64-bit build reads and writes is unchanged. Test added before the fix.

