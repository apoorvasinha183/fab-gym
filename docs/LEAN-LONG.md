# Is a WIP cap free? Long runs for wafers out

Pre-registered 27 October 2026, before any run of this design. Results are added below the line
once the runs are done; nothing above the line changes after that.

## The question

A WIP cap (CONWIP) holds new lots back while the fab holds a set number of lots. A low cap
shortens cycle time (Little's law) and can starve the busiest tools; breakdowns make the fab
need more lots on hand to keep those tools fed. So a cap that costs no wafers on a calm fab may
cost wafers when breakdowns rise. On the SMT2020 model, at which cap and which breakdown rate
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
- **Reported:** every cell, whatever it shows. "On the SMT2020 model" on every result;
  real-fab effect: cannot say.

## Code

- `fabsim::dials`: breakdown rate, repair time, demand, hot-lot share, rework, cap and one
  outage, applied to a copy of a shop.
- `fabsim::window`: scores over a window from probes and lot records.
- `fabsim::sweep`: a grid of dials on paired seeds over threads, and paired intervals.
- `fabsim lean-long`: runs this design and writes `results/lean-long/`.

---

## Results

(added after the runs)
