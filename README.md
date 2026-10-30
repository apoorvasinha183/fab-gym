<p align="center"><img src="docs/img/fabgym-hero.jpg" width="820" alt="Cartoon of a cleanroom boot camp: a wafer in a red headband yells &quot;You call that planar?&quot; at a sweating CMP robot holding a spirit level, while engineers in bunny suits lift dumbbells and the etch tool naps."></p>

# Fab Gym

Ask a simulated wafer fab a question in plain words, and get back tested options that a person signs.

Fab Gym runs on the published **SMT2020 research model** of a wafer fab: 1,043 tools in 105 groups, two products with routes of 583 and 343 steps. Meta's open model, Muse Spark Open, turns each question into experiments. The simulator scores them against the rules fabs use today, on the same random draws, with 95% intervals. A person signs the answer.

Every number Fab Gym reports is on the SMT2020 model. Fab Gym uses no real fab's data and makes no claim about any real plant.

Our entry to the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon), Startups track, theme Push the Frontier. By Chetnova.

## What is new in this hackathon

**Everything in this repository was built during the hackathon, starting after the 12:00 PM ET kickoff on 26 October 2026.** The git history is the record.

Built before the hackathon, and kept outside this repository:

- A Python reference engine for the SMT2020 model, written earlier in Chetnova's private repository. The Rust simulator here is written new and is checked against event logs recorded from that engine (the golden files in `golden/`). None of its code is copied here.
- Earlier results on the SMT2020 model (a learned dispatch rule, a WIP-cap study). They are quoted only where labelled "pre-existing".

## How it works

1. **Ask.** A person types a question or speaks a shift handover.
2. **Scenario.** Muse Spark Open turns it into a scenario that must pass a schema. Each value is tagged as said by the person or assumed.
3. **Candidates.** The model proposes answers: dispatch rules written as small Rust functions, WIP caps, spare tools or release plans.
4. **Search.** Rules are compiled to WebAssembly and run in a sandbox. The model reads their scores on training seeds and rewrites them. A red-team role tries to game the score.
5. **Score.** Finalists are scored once on held-out seeds against today's rules, with paired 95% intervals.
6. **Sign.** A result card quotes only the scorer's numbers. A person signs.

The model proposes, the simulator scores, a person signs.

## Layout

| Path | What |
| --- | --- |
| `crates/fabsim/` | The simulator, in Rust |
| `agent/` | The loop that asks Muse Spark Open and scores its answers |
| `viewer/` | The Godot replay |
| `lean/` | The Lean checker for scored runs |
| `golden/` | Event logs recorded from the reference engine, which the simulator must match |
| `docs/` | The problem statement |

## Status

Skeleton only. Next: the acceptance tests, written and committed before any simulator code.

## Credits

The SMT2020 testbed: Kopp, Hassoun, Kalir and Mönch, *SMT2020: A Semiconductor Manufacturing Testbed*, IEEE Transactions on Semiconductor Manufacturing, 2020. See `NOTICE.md`.
