# The referee's sixth rule: a finished lot did every step

Written 1 November 2026, before the tests and the code. The founder asked whether "our lean checker [is] checking that
... the full correct manufacturing process is completed in full and in order"; the answer was: in order, yes (rule 2,
`docs/LEAN-CHECK.md`); in full, no, since nothing ties a lot counted as finished to its route's last step; and Build's
runs are never refereed. The founder: "yes add the lean rule, go". On a teaching fab of our own and the SMT2020
testbed; not a real fab.

## What changes

1. **The receipt says which lots finished** (`fabgym-receipt 2`). After the events, one line per finished lot,
   `F LOT TIME`, with the engine's exact finish time; the `end` line adds the number of finished lots and the number
   finished in the scored window: `end JOBS STATES BREACHES_TOTAL BREACHES_WINDOW FINISHED FINISHED_WINDOW`.
2. **Rule 6, finished in full.** For every `F` line: the lot is finished once; it had a job; its last job was at its
   route's last step, or at a step after which every remaining step samples (a sampled inspection a lot may skip, as
   rule 2 already allows); that job ended no later than the finish. With rule 2 (each job at the next step, or where
   rework sends it), this means a finished lot did every step of its route, in order, ending at the last. The
   referee recounts the finished lots, in all and in the window, against the `end` line.
3. **Version 1 receipts still pass** under the five rules, with no rule 6, so earlier checks stay as they were.
4. **The proof.** `check_sound` stays as it is; a new `checkAll_sound` says that `checkAll` succeeding means the five
   rules and rule 6 (`FinishedInFull`) hold, and the finished counts are the true counts. No `sorry`, only Lean's
   standard axioms.
5. **Build's runs can be refereed.** `fabsim receipt` reads Build's breakdown settings (`--overrides`), so a
   challenge's run gives a receipt; each challenge's starting layout and its three-star fix are refereed.

## Tests (written before the code)

Rust, `crates/fabsim/tests/receipt.rs`:
- **R7** a receipt has an `F` line for every lot the run finished, with its exact finish time, and none for any other;
  the `end` line's finished counts equal the run's (in the window, the score's lots finished).
- **R8** tampered copies for rule 6 differ from the original in one record: `early` (a finish before its lot's last
  job ends), `unfinished` (an `F` line for a lot whose last job is not at its last step) and `count` (one too many
  finished claimed).
- **R9** with `--overrides`, a challenge's receipt run is Build's run: the same jobs as `fabsim moods` reports for the
  same layout, seed and days.

Lean, `lean/tests/` (hand-made receipts, with `expected.txt`):
- **L6** a version 2 receipt with finished lots passes; one is rejected and rule 6 named for each of: a finish before
  the last job ends, a lot finished whose last job is not at its last step, a lot finished after skipping an
  unsampled last step, a lot finished twice, a lot finished with no job, the finished count one too high, the count in
  the window one too low. A finish after a sampled last step it skipped passes.
- **L7** every version 1 receipt in `lean/tests/` gives the same verdict as before.
- **L8** `checkAll_sound` is proved with no `sorry` and only the standard axioms (`lean/run.sh prove`).
- **L9** the four challenges' runs, at their starting layout and with their fix, give receipts the referee accepts,
  and their tampered copies (R8) are rejected with rule 6 named (`lean/run.sh challenges`).

## Changes
- 1 Nov, while writing the code: R7 first read the window score from a run without probes at the window's ends; it now
  runs the toy fab with them (`window::with_probes`). R1 (`docs/LEAN-CHECK.md`) is updated: receipts are version 2,
  and the finished lots' `F` lines come after every event.
- 1 Nov, while writing the code: the "unfinished" tampered copy first kept its line's finish time, which was often
  before the relabelled lot's last job ended, so the referee rejected it as early rather than as unfinished; it now
  finishes no earlier than that job ends, so only the steps still to do are wrong. In `lean/run.sh challenges`, the
  shared `expect` helper set a variable the loop also used, so the tampered copies were first skipped; the loop's
  variable is renamed.
- 1 Nov, results:
  - R1 to R9 pass, and the engine's whole suite passes.
  - L6 and L7: the seven new hand-made receipts give their expected verdicts, as do all 22 version 1 receipts; the toy
    runs' receipts pass and every tampered copy is rejected with its rule named (`lean/run.sh test`).
  - L8: `checkAll_sound` and `check_sound` are proved with no `sorry`, each on Lean's three standard axioms only.
  - L9: the eight challenge runs (four challenges, at their start and with their fix; seed 1, two days, as Build
    scores them) pass, from 832 to 1,467 jobs and 25 to 65 finished lots, and each one's three tampered copies are
    rejected under rule 6.
