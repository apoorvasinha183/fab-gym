# lean: the run referee

Checks a scored run's receipt against the testbed's five rules: no tool runs two jobs at once, every lot follows
its route, batches stay within size, nothing runs on a tool that is down, and the breach counts are right. A Lean
theorem (`FabCheck/Proofs.lean`, `check_sound`) proves that when the referee says yes, the rules hold for every job.
It proves a run obeys the model's rules and says nothing about how closely the model matches a real fab.

- `FabCheck/Core.lean`: the referee (plain Lean 4, no libraries).
- `Main.lean`: the program, `referee FILE` or `referee -`.
- `FabCheck/Proofs.lean`: the rules stated plainly, and the proof (Mathlib).
- `tests/`: hand-made receipts and their expected verdicts (`make.py` writes them).
- `run.sh`: `build`, `test`, `prove`, `check -- CMD` on the Mac mini.

The spec, the receipt format and the measured costs are in `docs/LEAN-CHECK.md`.
