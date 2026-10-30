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

## Results (30 Oct; `results/uq-inputs/`, `fabsim uq-inputs`)

All ten draws ran (3 to 8.5 minutes each on the laptop, 4 threads). Overall mean difference against the comparison,
99% t-interval over the 10 draws (95% over the five comparisons together), the share of draws whose mean points the
same way, and the share whose own interval is clear that way:

| Comparison | Published inputs (long-v1 or lean-long) | With input doubt | Same way | Clear | Survives |
| --- | --- | --- | --- | --- | --- |
| Critical ratio against today, wafers a day | −205 | **+105 (−27 to +236)** | 90% (higher) | 80% | **No**: the sign flips and the interval holds zero |
| Shortest first against today | −595 | −271 (−474 to −67) | 100% | 90% | Yes |
| FIFO against today | −668 | −336 (−581 to −92) | 90% | 80% | Yes |
| Cap 1,800 against none, k = 1 | −2.4, no clear effect | +38 (−26 to +102) | 70% | 50% | Yes (still no clear effect) |
| Cap 1,800 against none, k = 2 | −44.9 (cap loses) | +28 (−32 to +87) | 70% | 50% | **No** |

- Cycle time and reward agree with wafers out for shortest first and FIFO (both clearly worse); for critical ratio
  both intervals hold zero.
- **The input doubt is nearly all the uncertainty**: of the variance between the draws' means, 98 to 100% is the
  input doubt and the rest the luck inside a draw's five-seed mean (`summary.json`, `between_var` against
  `within_var_of_mean`). Layer-1 intervals,
  which hold the luck only, are far too narrow for any claim about a fab whose numbers are estimated.

### Exploratory, after the pre-registered analysis (`fabsim uq-inputs --ceilings`, `ceilings.json`)

- **Every draw lowered the capacity ceiling**: 873 to 1,204 wafers a day against the published 1,302, with the
  bottleneck moving to thin film, lithography or the back-end polishers. Each group's factors average 1, but the
  ceiling is set by the slowest of 105 groups, and with every group redrawn at least one usually comes out slower.
  Releases stay at 1,430 a day, so every redrawn fab is more overloaded than the published one.
- In that heavier overload, critical ratio's 60-day output exceeds its draw's expected ceiling by up to 25% (draw 2:
  1,333 against 1,153). Over a long run nothing passes the bottleneck faster than its capacity, so this points to
  critical ratio emptying lots already past the bottleneck in the window, a transient; today's rule stays at or near
  the ceiling (0.83 to 1.06 of it).
- So the study, as designed, mixes two things: doubt about the numbers, and a fab pushed further into overload. Two
  checks would separate them: redraws with releases scaled to each draw's ceiling (the same load as published), and a
  longer window to see whether critical ratio's edge is a drain.

---

## Follow-up, pre-registered 30 Oct after the exploratory finding (decided by quiz: one follow-up run, then the supervisor)

Results go below this section's own line; nothing above it changes.

**Question.** Is critical ratio's edge over today's rule, and the cap's change at k = 2, a matter of doubt about the
numbers, or of the redrawn fabs being more overloaded? And is critical ratio's edge a drain that fades?

**Equal load.** For each draw, every release rate is multiplied by the draw's ceiling over the published ceiling
(1,301.9), so each redrawn fab releases the same multiple of its own capacity as the published fab does (1.098).
`fabsim::inputs::equal_load`.

**Runs** (the same 10 draws and σ = 0.2):

- F1, equal load, long-v1 (window days 130 to 190): today's rule against critical ratio, shortest first and FIFO,
  seeds 0 to 4. Wafers out a day.
- F2, the first study's load, window days 130 to 250: today's rule against critical ratio, seeds 0 to 4. Wafers out a
  day over days 130 to 190 and over days 190 to 250, from the same runs' daily output.
- F3, equal load, the cap: 1,800 against none at k = 1 and k = 2, 300 days, window days 120 to 300, seeds 1000 to 1004.

**Analysis.** As above (t over the 10 draws' means). Seven comparisons (three in F1, two in F2, two in F3):
Bonferroni, each at 1 − 0.05/7.

**Reading it.** If critical ratio's edge vanishes at equal load (F1), the flip came from the overload. If its edge in
F2 is smaller over days 190 to 250 than over 130 to 190, it drains.

**Tests first.** `crates/fabsim/tests/inputs.rs`: at equal load, each draw's release-to-ceiling ratio equals the
published one; at σ = 0 equal load is the published shop.

---

### Follow-up results (30 Oct; `results/uq-inputs/follow-up/`, `fabsim uq-inputs --follow-up`)

All ten draws ran (4.5 to 13 minutes each). Mean difference, 99.29% t-interval over the 10 draws (95% over the
seven together), the share of draws pointing the same way as the mean, and the share clear that way:

| Comparison | Today's rule (or no cap) | Difference | Same way | Clear |
| --- | --- | --- | --- | --- |
| F1 critical ratio against today, equal load | 1,008 | −27 (−242 to +187) | 60% | 60% |
| F1 shortest first against today, equal load | 1,008 | −265 (−481 to −48) | 90% | 80% |
| F1 FIFO against today, equal load | 1,008 | −257 (−519 to +5) | 80% | 80% |
| F2 critical ratio against today, days 130 to 190 | 978 | +105 (−36 to +245) | 90% | 80% |
| F2 critical ratio against today, days 190 to 250 | 972 | −88 (−300 to +125) | 70% | 50% |
| F3 cap 1,800 against none, k = 1, equal load | 1,009 | +6 (−39 to +51) | 40% | 20% |
| F3 cap 1,800 against none, k = 2, equal load | 955 | +9 (−46 to +64) | 50% | 20% |

- **Critical ratio's flip came from the overload, and it drains.** At equal load its edge is gone (−27, no clear
  effect). At the first study's load it leads over days 130 to 190 (+105, the same runs as before: the first study
  gave +104.57 too) and falls behind over days 190 to 250 (−88): it empties lots already in the fab, then pays for it.
- **Shortest first stays clearly worse** at equal load. FIFO is worse in 8 of 10 draws, but at the seven-way level its
  interval just touches zero.
- **The cap's cost at doubled breakdowns does not survive input doubt**, at either load (+9, no clear effect). The
  published-number result (−44.9 wafers a day, `docs/LEAN-LONG.md`) holds for SMT2020's own numbers only.
- Input doubt is again 98 to 100% of the variance between draws.

**What changes in what we claim.** On the SMT2020 model with its published numbers, the earlier results stand as
measured. For a fab whose numbers are estimates about 20% off: shortest first is worse than today's rule; FIFO is
probably worse; today's rule against critical ratio is not settled once loads are matched, and critical ratio's
short-window wins are a drain; the cap's cost under doubled breakdowns cannot be claimed.
