# The run referee: Lean checks every scored run (build step 4)

Written 31 October 2026, before the tests and the code. Decided by quiz the same day (`~/HACKATHON-README.md`): all
five checks plus soundness theorems, the proofs checked on the Mac mini against its Mathlib, every final scored run
checked. Explainer for a newcomer (private).

From the SMT2020 testbed; not a real fab, not real data. Agents propose, the simulator scores, a person signs.

## The problem

A score is only as good as the run behind it. The simulator writes a **receipt** for a run; a separate program in
Lean, the **referee**, reads it and answers yes or no, naming the first rule broken. A Lean theorem states that a yes
means the five rules below hold for every job in the receipt.

What a yes proves: that run obeyed the testbed's five rules, and the breach counts reported with it are the true
counts for it. What it does not prove: that the testbed behaves like a real fab (cannot say), that the policy was
good (the score answers that), or that the random draws were fair.

## The five rules, as the engine keeps them

Read from `crates/fabsim/src/engine.rs` on 31 Oct; each is the engine's own rule, so a valid run passes.

1. **One job at a time.** A tool starts work only when it is not busy and not down; it is busy until the job ends.
   A batch is one job: its lots start and end together. A step whose wafers pass one after another (`interval`) is
   one job too. So on any tool, any two jobs' processing intervals `[start, end)` do not overlap.
2. **Routes.** A lot's next job after step `k` is at step `k+1`, or the step its rework sends it back to; from there
   it may pass over steps that sample (a `sample` step is skipped by a draw). A lot's first job is at its listed
   starting step (0 for a released lot), again possibly past sampled steps. Each job runs on a tool of the group its
   step names. A lot arrives at a step no earlier than its previous job ended, and starts no earlier than it arrived.
3. **Batches.** All lots in one job are at the same step of the same route. At a batch step the job's wafers are at
   most the step's maximum. At any other step a job holds exactly one lot. (A batch may start below its minimum once
   its oldest lot has waited the batch wait, so the minimum is not a rule.)
4. **Nothing on a down tool.** A down that falls due during a job starts when the job ends. So no job's interval
   overlaps a period when its tool is down: scheduled down (maintenance, a fixed down window) or unscheduled down
   (breakdown, a defect hold). A setup (the engine logs it as scheduled down with the reason `setup`) is not a down.
5. **Breaches.** A step with a queue-time limit `(to, L)` starts a clock when it ends. When the lot later begins step
   `to`, it breaches if `begin - end > L`, where `end` is the latest end of that earlier step so far (rework can
   repeat it). Each such pair counts once. The receipt claims the run's total and the count in the scored window
   (breaches whose late step begins in `(from, to]`, as the score counts them); the referee recounts both.

## The receipt (`fabgym-receipt 1`)

Plain text, one record a line, fields separated by single spaces, ids dense from 0. Written by
`fabsim receipt` from a run with `record` on (logging only; the run is the same run).

```
fabgym-receipt 1
run SHOP_SHA256 SEED POLICY UNTIL FROM TO
group G NAME
tool T G
route R NSTEPS
step R K G BATCHMAX SAMPLE REWORK CQT_TO CQT_LIMIT      (BATCHMAX, REWORK, CQT_* are - when absent; SAMPLE 0 or 1)
lot L R SIZE FIRSTSTEP
S T TIME STATE                                          (STATE: 0 working, 1 idle, 2 setup, 3 scheduled down, 4 unscheduled down)
J T START END N  LOT STEP ARRIVE  [LOT STEP ARRIVE ...]  (one line per job; N lots)
end JOBS STATES BREACHES_TOTAL BREACHES_WINDOW
```

- **Order.** Header lines (`run`, then `group`, `tool`, `route`, `step`, `lot`) before any event. Events in
  nondecreasing time; at equal times every `S` before any `J`; `S` lines in the engine's log order; `J` lines in
  the engine's start order. The referee rejects a receipt out of this order.
- **Exact times.** Every time and limit is the engine's `f64`, written exactly: `M` (an integer) or `M/E`, meaning
  M ÷ 2^E. Nothing is rounded. The referee compares and adds exact numbers. Where the engine's own `f64`
  subtraction rounds a breach the other way (a gap within one unit in the last place of the limit), the counts
  disagree and the receipt is rejected; that is reported, never hidden.
- `end` repeats the counts, so a cut-off receipt is rejected.

## The referee and the theorem

- `lean/FabCheck/Core.lean` (plain Lean 4, no Mathlib): the receipt's types, the exact dyadic numbers, the parser,
  one pure `step : State → Event → Except Fault State` and `check : Fab → List Event → Claims → Except Fault Unit`
  (a fold of `step` and the final count checks).
- `lean/Main.lean`: the program. It reads the header, then streams the events from a file or stdin, applying the
  same `step` to each line as it is read (memory: per tool and per lot, never all jobs), and prints `yes` or `no`
  with the rule, the line and the record.
- `lean/FabCheck/Proofs.lean` (imports Mathlib): the five rules as plain statements over the list of events, with
  times as rationals, and
  ```lean
  theorem check_sound (f : Fab) (es : List Event) (c : Claims) :
      check f es c = .ok () →
        OneJobAtATime es ∧ FollowsRoutes f es ∧ BatchesFit f es ∧
        NothingOnDown es ∧ BreachesCounted f es c
  ```
  plus `#print axioms check_sound` showing only Lean's standard axioms (`propext`, `Classical.choice`,
  `Quot.sound`) and no `sorry`.
- **What is trusted, not proved:** the parser (text to records), the program's read loop (it applies `step` line by
  line; a few lines, reviewed), the receipt writer (a wrong receipt of a valid run is rejected, never accepted as a
  different valid run, unless the writer and the engine are wrong the same way), and Lean's compiler and kernel.
- **Where it runs.** The mini has Lean `v4.35.0-rc3` and a built Mathlib in `~/lean-check`, shared with the
  learners' proof worker and left alone. The referee is its own Lake project in `~/fab-gym-lean` on the same
  toolchain with no dependencies (no download). The proofs are checked with `~/lean-check`'s environment, read only,
  with `~/fab-gym-lean`'s built files added to the search path. Receipts are streamed over ssh, compressed, straight
  into the referee: nothing is stored on the mini (17 GB free) or kept on the laptop.

## Which runs

Every final scored run, the long-v1 table (`docs/LONG-RESCORE.md`): days 130 to 190 of 190, seeds 0 to 9.
- Defects off: today, FIFO, shortest first, critical ratio, random and PPO, replayed exactly from the picks each
  scored run wrote (`results/long-rescore/regret-b/picks/`, 60 files). E2's three evolved rules play today's pick at
  every decision, so their runs are today's runs.
- Defects on: the five built-in rules, played again by the same episode code. PPO with defects on wrote no picks;
  checking it needs the Python contest rerun with `--picks` (about 70 CPU-minutes, measured from long-v1's 0.84 ms a
  decision), asked of the founder separately.

## Tests (written before the code)

Rust, `crates/fabsim/tests/receipt.rs` (toy shops; the SMT2020 test skips when the files are absent):
- R1 a receipt lists every started step of the run and every state change: its `J` lots equal the run's trace, its
  `S` lines its state log; events in nondecreasing time with `S` before `J` at equal times.
- R2 every time read back from the receipt is the engine's `f64` exactly.
- R3 the claimed breach counts equal the engine's (total, and in the window).
- R4 writing a receipt changes nothing: the run with `record` gives the same picks and window score as the scored
  episode, and the same receipt twice gives the same bytes.
- R5 `fabsim receipt-tamper KIND` makes one broken copy per rule (`overlap`, `skip`, `overfill`, `into-down`,
  `breach`), each differing from the original in one record.
- R6 a replayed run (`--picks`) gives the receipt of the run that wrote the picks (SMT2020, a short window).

Lean, `lean/tests/` (receipts written by hand, each a few lines, with `expected.txt`):
- L1 small valid receipts pass: a batch, a rework loop, a sampled skip, a lot starting mid-route, a setup, a
  breach counted.
- L2 one broken receipt per rule is rejected and the rule named: overlap, overlap inside a batch tool, wrong group,
  skipped unsampled step, start before arrival, overfilled batch, mixed-step batch, two lots at a non-batch step,
  a job inside a breakdown, a down starting inside a job, a breach count one too high, one too low.
- L3 a receipt out of order, cut off, or naming an unknown tool or lot is rejected.
- L4 the toy runs' receipts pass and their tampered copies (R5) are rejected with the rule named.
- L5 `check_sound` is proved with no `sorry` and only the standard axioms.

## Costs, measured before the scored runs

Measured 31 Oct on the M1, one core: the full fab, 190 days, 4.8 s with totals only and 5.3 s with the full record;
about 4.1 million jobs started. The referee's time and the receipt's size are measured on one run (seed 0, today,
defects off) and written here before the other runs start.

## Changes

(none yet)
