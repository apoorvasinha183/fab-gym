# Is a WIP cap free? Long runs for wafers out

Pre-registered 27 October 2026, before any run of this design. Results are added below the line
once the runs are done; nothing above the line changes after that.

## The question

A WIP cap (CONWIP) holds new lots back while the fab holds a set number of lots. A low cap
shortens cycle time (Little's law) and can starve the busiest tools; breakdowns make the fab
need more lots on hand to keep those tools fed. So a cap that costs no wafers on a calm fab may
cost wafers when breakdowns rise. From the SMT2020 testbed, at which cap and which breakdown rate
does that happen?

## What exploration showed (14-day runs, uncommitted scripts, seeds 0 to 29)

- In 14 days a cap moves no wafers out: lots take about 40 to 65 days to cross the fab.
- Without a cap the fab does not settle: one 240-day run (seed 10) took WIP from 2,269 to
  3,504 lots and cycle time from about 42 to about 65 days, levelling after about day 130.
- A flip in spoiled lots seen on seeds 0 to 9 vanished on seeds 10 to 29.

Seeds 0 to 29 are therefore not used below.

## Design

- **Model:** the SMT2020 high-volume model as loaded by `fabsim::smt2020::load`, today's
  dispatch rule.
- **Run:** 300 simulated days from SMT2020's lots in progress. **Warm-up:** days 0 to 120 are
  discarded. **Window:** days 120 to 300.
- **Breakdown rate** k (mean time to failure divided by k; repair time unchanged): 1, 1.5, 2.
- **Cap** (lots in the fab): 1,800; 2,100; 2,400; 2,700; 3,000; none.
- **Seeds:** 1000 to 1009, every cell of the grid on the same seeds (paired).
- **Scores over the window:**
  - wafers out a day (lots finished in the window times their size, over 180 days);
  - cycle time in days by Little's law (lot-minutes in the fab over lots finished, in the
    window);
  - hot-lot cycle time: the mean over lots released during the run with a priority above the
    lowest, finished in the window, of finish minus release.
- **Differences:** each cap against no cap at the same k, per seed.
- **Intervals:** paired t, Bonferroni over the 15 cap-by-k cells (each at level 0.05/15), so
  all 15 intervals on a score cover at once with probability at least 95% (exact if the
  differences are normal, asymptotic otherwise).
- **Verdict per cell:** better, worse or no clear effect (`uq::verdict`). **Flip:** for each
  cap, `uq::crossover` over k on wafers out. A cap is "free" at k when its wafers-out verdict
  is not worse.
- **Compute:** at most 4 threads, niced; results do not depend on the thread count.
- **Reported:** every cell, whatever it shows. "From the SMT2020 testbed" on every result;
  real-fab effect: cannot say.

## Code

- `fabsim::dials`: breakdown rate, repair time, demand, hot-lot share, rework, cap and one
  outage, applied to a copy of a shop.
- `fabsim::window`: scores over a window from probes and lot records.
- `fabsim::sweep`: a grid of dials on paired seeds over threads, and paired intervals.
- `fabsim lean-long`: runs this design and writes `results/lean-long/`.

---

## Results

Run 27 October 2026 with `fabsim lean-long --threads 4` (513 s on the M1, niced), exactly the
design above. The loader then read two metrology groups' first maintenance (given in days) as
minutes, as the reference compile does; `fabsim lean-long --reference` reproduces these results.
A rerun with the units read correctly is reported after the tables. Every run is in `results/lean-long/runs.tsv`; the intervals in `summary.json`.

**What it shows, from the SMT2020 testbed:**

- **The flip.** A cap of 1,800 lots is free on today's fab (wafers out −0.5 a day, 95%
  −8.8 to +7.8) and costs wafers when breakdowns double (−33.8 a day, −48.8 to −18.7, about
  2.8%). At 1.5 times the breakdown rate there is no clear effect (−16.0, −36.4 to +4.4), so
  the flip lies between 1 and 2 times today's rate.
- **Cycle time.** Every cap shortens it at every breakdown rate: from 66 days without a cap,
  by 8 days (cap 3,000) to 31 days (cap 1,800); with breakdowns doubled, from 80 days, by 19 to
  42 days.
- **Not expected.** Caps of 2,100 to 2,700 lots give more wafers out than no cap on today's
  fab (+24 to +34 a day, about 2 to 3%). Why has not been traced yet; it is reported as found.
- **Hot lots** take about 25 days whatever the cap (no difference larger than 0.1 day).
- `uq::crossover` labels cap 1,800 "worse at some rates, no clear effect at the others"
  because the calm end is "no clear effect" rather than "better"; in the terms of the question
  (free means not worse) that is the flip.

Real-fab effect: cannot say.

From the SMT2020 testbed. 10 seeds (1000..1009), 300 days, window days 120 to 300. Each cap minus no cap at the same breakdown rate, paired; intervals Bonferroni over 15 cells (each at level 0.0033), so all cover at once with probability at least 95%. Real-fab effect: cannot say.

### wafers out a day

| breakdowns | no cap (mean) | cap 1800 | cap 2100 | cap 2400 | cap 2700 | cap 3000 |
|---|---|---|---|---|---|---|
| x1 | 1258.53 | -0.47 (-8.77 to +7.83) unclear | +33.85 (+22.03 to +45.67) better | +34.28 (+18.88 to +49.68) better | +23.94 (+13.38 to +34.51) better | +8.11 (-7.65 to +23.88) unclear |
| x1.5 | 1239.29 | -16.01 (-36.42 to +4.39) unclear | +20.83 (+2.49 to +39.18) better | +27.65 (+1.97 to +53.33) better | +10.71 (-4.38 to +25.79) unclear | +5.32 (-8.06 to +18.70) unclear |
| x2 | 1211.11 | -33.78 (-48.84 to -18.72) worse | +4.90 (-8.92 to +18.73) unclear | +29.31 (+12.98 to +45.64) better | +17.39 (-0.28 to +35.06) unclear | +10.01 (-7.46 to +27.49) unclear |

### cycle time, days

| breakdowns | no cap (mean) | cap 1800 | cap 2100 | cap 2400 | cap 2700 | cap 3000 |
|---|---|---|---|---|---|---|
| x1 | 66.37 | -30.60 (-31.96 to -29.23) better | -25.74 (-27.32 to -24.17) better | -19.95 (-21.76 to -18.15) better | -13.74 (-15.25 to -12.23) better | -7.77 (-9.37 to -6.16) better |
| x1.5 | 72.60 | -35.81 (-38.68 to -32.93) better | -30.93 (-33.58 to -28.27) better | -25.23 (-27.85 to -22.61) better | -18.59 (-20.85 to -16.32) better | -12.42 (-14.66 to -10.19) better |
| x2 | 80.16 | -41.94 (-43.10 to -40.78) better | -36.99 (-38.06 to -35.91) better | -31.79 (-32.73 to -30.85) better | -25.21 (-26.48 to -23.95) better | -18.74 (-20.14 to -17.34) better |

### hot-lot cycle time, days

| breakdowns | no cap (mean) | cap 1800 | cap 2100 | cap 2400 | cap 2700 | cap 3000 |
|---|---|---|---|---|---|---|
| x1 | 24.62 | -0.02 (-0.12 to +0.08) unclear | +0.00 (-0.07 to +0.08) unclear | +0.02 (-0.04 to +0.09) unclear | +0.05 (-0.02 to +0.12) unclear | +0.04 (-0.04 to +0.12) unclear |
| x1.5 | 24.78 | -0.10 (-0.18 to -0.03) better | -0.04 (-0.13 to +0.04) unclear | +0.03 (-0.04 to +0.10) unclear | +0.03 (-0.06 to +0.12) unclear | +0.04 (-0.02 to +0.09) unclear |
| x2 | 24.92 | -0.06 (-0.15 to +0.04) unclear | +0.01 (-0.08 to +0.11) unclear | +0.01 (-0.11 to +0.12) unclear | +0.02 (-0.06 to +0.10) unclear | +0.04 (-0.07 to +0.16) unclear |

### Where each cap stops being free (wafers out, over breakdown rate)

- cap 1800: x1: free, x1.5: free, x2: costs wafers — worse from the SMT2020 testbed at some rates, no clear effect at the others
- cap 2100: x1: free, x1.5: free, x2: free — better from the SMT2020 testbed at some rates, no clear effect at the others
- cap 2400: x1: free, x1.5: free, x2: free — same verdict at every rate: better from the SMT2020 testbed
- cap 2700: x1: free, x1.5: free, x2: free — better from the SMT2020 testbed at some rates, no clear effect at the others
- cap 3000: x1: free, x1.5: free, x2: free — no clear effect at any rate


### Rerun with the units read correctly

Run 27 October 2026 with `fabsim lean-long --threads 4` after the loader fix (7a3ceb2), the same
design and seeds (503 s). The findings hold:

- **The flip.** Cap 1,800 is free on today's fab (−2.4 wafers a day, 95% −18.3 to +13.6) and
  costs 44.9 a day (21.9 to 67.8) when breakdowns double; at 1.5 times, no clear effect
  (−14.9, −35.3 to +5.5).
- **Gains.** Caps of 2,100 to 2,700 give 16 to 29 more wafers a day on today's fab; still not
  traced.
- **Cycle time** falls by 7 to 30 days on today's fab and by 19 to 42 days with breakdowns
  doubled; hot lots unchanged.

The page shows this run. Files: `results/lean-long-units/`.

From the SMT2020 testbed. 10 seeds (1000..1009), 300 days, window days 120 to 300. Each cap minus no cap at the same breakdown rate, paired; intervals Bonferroni over 15 cells (each at level 0.0033), so all cover at once with probability at least 95%. Real-fab effect: cannot say. Files read with their units.

### wafers out a day

| breakdowns | no cap (mean) | cap 1800 | cap 2100 | cap 2400 | cap 2700 | cap 3000 |
|---|---|---|---|---|---|---|
| x1 | 1264.07 | -2.35 (-18.28 to +13.59) unclear | +25.08 (+11.90 to +38.26) better | +28.69 (+14.12 to +43.27) better | +16.29 (+4.19 to +28.39) better | +7.18 (-5.24 to +19.60) unclear |
| x1.5 | 1237.04 | -14.88 (-35.26 to +5.51) unclear | +24.29 (+10.68 to +37.90) better | +26.60 (+3.25 to +49.95) better | +14.83 (-8.16 to +37.83) unclear | +6.61 (-12.11 to +25.33) unclear |
| x2 | 1216.79 | -44.89 (-67.82 to -21.95) worse | -1.71 (-18.14 to +14.73) unclear | +26.07 (+9.01 to +43.12) better | +16.76 (-1.60 to +35.12) unclear | +10.99 (-6.75 to +28.72) unclear |

### cycle time, days

| breakdowns | no cap (mean) | cap 1800 | cap 2100 | cap 2400 | cap 2700 | cap 3000 |
|---|---|---|---|---|---|---|
| x1 | 65.76 | -30.10 (-31.16 to -29.03) better | -25.04 (-26.16 to -23.92) better | -19.35 (-20.57 to -18.13) better | -13.05 (-14.28 to -11.81) better | -7.40 (-8.50 to -6.29) better |
| x1.5 | 72.54 | -35.72 (-37.68 to -33.76) better | -30.91 (-32.53 to -29.30) better | -25.05 (-26.47 to -23.63) better | -18.61 (-19.92 to -17.30) better | -12.34 (-13.60 to -11.08) better |
| x2 | 80.00 | -41.60 (-43.45 to -39.75) better | -36.79 (-38.59 to -34.99) better | -31.72 (-33.38 to -30.05) better | -25.27 (-27.17 to -23.38) better | -18.91 (-20.72 to -17.10) better |

### hot-lot cycle time, days

| breakdowns | no cap (mean) | cap 1800 | cap 2100 | cap 2400 | cap 2700 | cap 3000 |
|---|---|---|---|---|---|---|
| x1 | 24.63 | -0.00 (-0.07 to +0.06) unclear | -0.00 (-0.06 to +0.06) unclear | +0.02 (-0.02 to +0.06) unclear | +0.05 (-0.02 to +0.13) unclear | -0.00 (-0.06 to +0.06) unclear |
| x1.5 | 24.76 | -0.05 (-0.11 to +0.01) unclear | -0.03 (-0.10 to +0.03) unclear | +0.06 (-0.01 to +0.12) unclear | +0.05 (-0.01 to +0.12) unclear | +0.05 (-0.02 to +0.12) unclear |
| x2 | 24.95 | -0.08 (-0.17 to +0.00) unclear | -0.03 (-0.14 to +0.07) unclear | -0.02 (-0.08 to +0.04) unclear | +0.03 (-0.09 to +0.15) unclear | +0.07 (-0.04 to +0.18) unclear |

### Where each cap stops being free (wafers out, over breakdown rate)

- cap 1800: x1: free, x1.5: free, x2: costs wafers — worse from the SMT2020 testbed at some rates, no clear effect at the others
- cap 2100: x1: free, x1.5: free, x2: free — better from the SMT2020 testbed at some rates, no clear effect at the others
- cap 2400: x1: free, x1.5: free, x2: free — same verdict at every rate: better from the SMT2020 testbed
- cap 2700: x1: free, x1.5: free, x2: free — better from the SMT2020 testbed at some rates, no clear effect at the others
- cap 3000: x1: free, x1.5: free, x2: free — no clear effect at any rate
