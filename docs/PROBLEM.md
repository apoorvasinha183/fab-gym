# Fab Gym: the problem statement

## The problem

Factories do not yet let AI agents make operating decisions, because nobody can say in advance whether a proposed decision is any good. An agent can read a shift report and write code, but an operations head has no way to test its proposal before it reaches production.

A wafer fab is the hardest case in manufacturing. A lot of 25 wafers visits more than 500 steps over weeks and returns to the same machines dozens of times. It waits for batches, pays for setup changes, and must clear some pairs of steps within a time limit or risk scrap. About a thousand machines break down and go into maintenance underneath all of this.

The questions an operations head asks are answered from experience, with no error bars: what to do when a tool group goes down, what hot lots cost everyone else, whether running lean is worth it.

## What Fab Gym does

Fab Gym answers such questions on the SMT2020 testbed with tested options and intervals.

1. A person types a question or speaks a shift handover (Muse Voice Transcribe).
2. Muse Spark Open turns it into a scenario that must pass a versioned schema. Each value is tagged as said by the person or assumed; values the question leaves open get a range.
3. Muse Spark Open proposes candidates: dispatch rules as small Rust functions, WIP caps, spare tools, release plans.
4. Rules are compiled to WebAssembly and run in a sandbox with a fuel limit. The model reads scores on training seeds and rewrites them over generations. A red-team role tries to game the score, and a critic reviews every winner.
5. Finalists are scored once on held-out seeds against today's rules.
6. A result card quotes only the scorer's numbers, a decision certificate records the scenario, scores, Lean check and signer, and a person signs.

## Demo questions

- "Group 79 is down tomorrow, what do we do?"
- "20 lots are hot for a customer, what does it cost the rest?"
- "Is running lean worth it here?"

## Scoring protocol (fixed before any result)

- 24 hours of warm-up, then a 3-day window.
- Evaluation seeds 0 to 9; training seeds 100 and up, never mixed. During search, clearly losing rules drop out early on training seeds. Every final claim uses the same 10 held-out seeds.
- Baselines: today's rule (highest priority, then no setup change, then oldest), first in first out, shortest processing first, critical ratio (due dates assumed at release plus 3 times raw processing time) and seeded random.
- Each option's paired difference from today's rule, with a 95% t-interval. Better only if the interval excludes zero.
- Measures: moves, wait per step, lot-hours waiting, queue-time breaches, lots finished, lots in the fab, reward (lots finished minus 0.01 per lot-hour waiting).

## Uncertainty

| Layer | What we do | What the card says |
| --- | --- | --- |
| Randomness in a run | Paired seeds, 95% intervals | The difference and its interval |
| Searching too hard | Pick on training seeds, score once on held-out seeds, widen intervals when options are compared together | Scored once on held-out seeds |
| What the question leaves open | Sweep the open range and find where the best option changes | "B wins if the outage runs past N hours. How long will it be?" |
| The gap to a real fab | Say so | Real-fab effect: cannot say |

Redrawing the SMT2020 testbed's own breakdown and repair numbers comes later.

## Checks

- The simulator reproduces the reference engine's event log exactly on the same seeds, and raw processing time per product matches the published reference within 1%.
- Acceptance tests: exact incumbent, choices matter, invalid actions change nothing, determinism, conservation, no leakage of the future, faithful world, full report, probes change nothing, the WIP cap holds, shocks do what they declare, Little's law holds exactly, the frontier repeats.
- Every scored run gets a certificate that a Lean checker confirms. This proves runs obey the model's rules; it says nothing about how closely the model matches a real fab.

## What we never claim

A real fab, TSMC or real plant data; that the agent runs a fab; any result before it happens.
