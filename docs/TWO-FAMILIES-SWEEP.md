# Two families: which policy, which floor, at what share?

Pre-registered 28 October 2026, before any run of this design. Results are added below the line once the runs are
done; nothing above the line changes after that. On the SMT2020 model, with a layout of our own design; not a real
fab, not real data. Agents propose, the simulator scores, a person signs.

## The question

A fab runs family A (SMT2020's volume products, parts 3 and 4) and takes in family B (SMT2020's engineering lots,
rebuilt from their published facts on product 3's route; `docs/TWO-FAMILIES.md`). As family B's share grows, which
operating policy and which 2D layout strategy make the most money a day, and at what share does the answer change?

## Design

- **Model:** the SMT2020 high-volume model as `fabsim::smt2020::load` reads it, plus family B
  (`twofam::two_family_shop`, route `part_E3` copying `part_3`). No fab-wide WIP cap (today's fab). Family A keeps
  today's dispatch rule except under P1.
- **Run:** 300 simulated days from SMT2020's lots in progress. **Warm-up:** days 0 to 120 discarded. **Window:**
  days 120 to 300 (the windows of `docs/LEAN-LONG.md`).
- **Share of family B** (`EngLots.scale`): 1, 2, 4, 8 times the published 20 lots a release. At 1 that is about 5.7
  lots and 31 wafers a day.
- **Layout strategies** (`twofam::lay_out`, `layout::Config::realistic()`, optimiser seed 1, laid out once per
  share because the flows change with it):
  - **D1 share:** no copies.
  - **D2 wing:** one-tool copies of the 3 most contested groups family B visits, on a third phase (pad P3).
  - **D3 copies:** the same copies, in the two halls, placed by family B's flow.
- **Policies.** "The policy groups" are the 3 groups family B still shares with family A after the layout, ranked
  by `twofam::contested` (copies, `@B`, excluded):
  - **P0 today:** no family rules.
  - **P1 family B first:** at every decision a family-B candidate is taken before any family-A one; within a family,
    today's order (the first candidate of that family in the decision's list, or today's pick when it is of that
    family).
  - **P2 family cap:** `famcap B` = ⌈1.5 × family B's lots a day × product 3's raw processing days⌉, which lets B's
    average load through and holds its release bursts.
  - **P3 reservation:** in each policy group, the first tool takes family B's lots first (`qual` all tools,
    `reserve` 1).
  - **P4 qualification:** in each policy group, family B is qualified on the first half of the tools (rounded up)
    only.
- **Seeds:** 2000 to 2009, every cell on the same seeds (paired). None of these seeds has been run on this design.
- **Scores over the window, per run:**
  - family A's wafers out a day;
  - family B's lots and wafers out, and its mean cycle time in days from scheduled arrival (holding counts);
  - money a day (`fabsim::money`) at every point of the price grid below.
- **Prices** (all assumed; family A's margin is 1 per wafer, so every price is in wafers of family-A margin):
  - family B's price per wafer `price0`: 10, 20, 40;
  - free days 30; price lost per day after: 1/30 or 1/10 of `price0`;
  - an added tool per day: 0, 20, 100; an added metre per day: 0, 2;
  - **central point:** price0 20, loss 1/30 a day, tool 20 a day, metre 2 a day.
  - Qualification costs nothing in this grid; for P4 the break-even qualification cost per tool a day is reported
    (the money P4 loses against P0, over the tools it leaves unqualified).
- **Differences:** every (strategy, policy) cell against (D1, P0) at the same share, per seed.
- **Intervals:** paired t, Bonferroni over the 56 cells (14 per share, 4 shares; each at level 0.05/56), so all 56
  intervals on a score cover at once with probability at least 95% (exact if the differences are normal,
  asymptotic otherwise).
- **Verdicts:** better, worse or no clear effect (`uq::verdict`). **Crossover:** for each cell, `uq::crossover` over
  share on money at the central prices.
- **Reported:** every cell, whatever it shows, at the central prices; the full price grid in the files; the best
  cell per share named with its interval only.
- **Compute:** at most 4 threads, niced; results do not depend on the thread count. A heavy job: it runs only when
  nothing else heavy runs.
- Every result says "on the SMT2020 model"; real-fab effect: cannot say.

## Code

- `fabsim::twofam`: `Policy`, `policy_groups`, `apply_policy`, `b_first` (P1's choice).
- `fabsim::money`: `PriceGrid` with the central point first.
- `fabsim two-families`: runs this design and writes `results/two-families/`.
- Tests first: `crates/fabsim/tests/two_families_sweep.rs`.

---

## Results

Not run yet.
