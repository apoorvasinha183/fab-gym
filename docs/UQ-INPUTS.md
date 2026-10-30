# Do the verdicts survive doubt about the inputs? (uncertainty layer 4)

Pre-registered 30 October 2026, before any run of this design; decided by quiz the same day (a study first, then the
supervisor). Results go below the line once the runs are done; nothing above the line changes after that. On the
SMT2020 model, a published research model of a wafer fab; no real fab's data.

## The question

Every interval so far (layer 1, `docs/UNCERTAINTY.md`) covers the luck inside a run: breakdowns, process times. It
trusts SMT2020's published input numbers. A real fab estimates those numbers from data, and an estimate can be off.
If each tool group's processing time, time between failures, repair time and maintenance length were off by about
20%, would the headline verdicts still hold?

## The input doubt (assumed)

- For each tool group, four factors, each drawn independently: processing time (every step at the group, and the
  per-piece interval), mean time to failure, mean time to repair, and preventive maintenance length (both ends of its
  range).
- Each factor is lognormal with mean 1: exp(σZ − σ²/2), Z standard normal, **σ = 0.2** (assumed: "a fab's estimates
  off by about 20%").
- Everything else is as published: tool counts, routes, batches, setups, sampling, rework, queue-time limits,
  maintenance intervals, releases, lots in progress.
- Draw d (1 to 10) seeds its own generator from the text `inputs/<d>`, apart from the run's seed. Draw 0 is the
  published numbers.

## Design

- **10 draws** (1 to 10) × **5 run seeds** each. Within a draw, every option runs on the same 5 seeds (paired).
- **Claim 1, the policies** (protocol long-v1, `docs/LONG-RESCORE.md`): warm-up days 0 to 130 under today's rule,
  window days 130 to 190, defect holds off; today's rule against critical ratio, shortest processing first and FIFO.
  Seeds 0 to 4. Measures: wafers out a day (primary), cycle time, reward.
- **Claim 2, the WIP cap** (`docs/LEAN-LONG.md`): 300 days, window days 120 to 300, today's rule; cap 1,800 against
  no cap, at breakdown rate k = 1 and k = 2. Seeds 1000 to 1004. Measure: wafers out a day.
- Run with 4 threads, niced, one heavy job.

## Analysis

For each comparison, per draw: the paired difference averaged over its 5 seeds, d̄_p.

- **Overall:** the mean of the 10 draw means, with a 95% t-interval over them (9 degrees of freedom). Its spread
  holds both the luck (within a draw) and the input doubt (between draws), so it is the interval with layer 4 in.
  Five comparisons (three in claim 1, two in claim 2): Bonferroni, each at 99%.
- **Split:** the variance of the draw means against the within-draw variance divided by 5; the input doubt's share.
- **Robustness:** the share of draws whose own paired interval (t over 5 seeds, 95%) is clear in the published
  direction, and the share whose mean points that way.
- **The verdict survives** when the overall interval excludes zero in the same direction as on the published
  numbers. For claim 2 at k = 1 (published: no clear effect), it survives when the interval still includes zero.

Guarantee: probable, at the stated levels, for the input doubt as modelled (lognormal, σ = 0.2, independent by group
and by factor). It says nothing about doubt of another shape, or about the model's structure (layer 5).

## Tests (written before the code)

- `crates/fabsim/tests/inputs.rs`: σ = 0 gives the published shop exactly; the same draw gives the same shop and
  another draw a different one; only the four kinds of number change; every step at a group scales by the group's
  factor; over many draws the factors average 1 and their logs spread by σ.
- `crates/fabsim/tests/uq.rs`: the nested interval on hand-made numbers (mean of draw means, t over draws, the split,
  the shares).

---

## Results

(to come)
