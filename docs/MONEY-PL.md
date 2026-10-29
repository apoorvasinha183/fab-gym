# Money with full business logic: a profit and loss in dollars

Written 29 October 2026, before the code. Decided by quiz the same day (`~/HACKATHON-README.md`): a full profit and
loss with payback, in US dollars, every figure assumed, labelled and swept over a range. On the SMT2020 model, a
published research model of a wafer fab. No real fab's prices or data are used. Agents propose, the simulator
scores, a person signs.

## Why

"Money a day" (`fabsim::money`, `docs/TWO-FAMILIES.md`) is a score in volume-wafer margins: a family A wafer earns
1, a prototype wafer earns 20 if it is out within 30 days and less after, an added tool costs 20 a day and a metre
of wall 2 a day. It has no purchase price for a tool, no building for a wing, no qualification, no running costs and
no payback. A reader cannot tell what it means. The founder: "when you open a building or buy new equipment it
incurs cost, where is that accounted for? You should employ full business logic."

## The price sheet (all assumed)

Every number below is an assumption of ours, chosen to be of a plausible order for a front-end wafer fab. None is
a quote, a published price or a real fab's figure. Each has a low and a high value, and the results report what
happens at both.

| Item | Central | Low | High |
| --- | --- | --- | --- |
| Volume wafer (family A) sale price | $8,000 | $4,000 | $15,000 |
| Prototype wafer (family B) price, out within 30 days | $60,000 | $30,000 | $120,000 |
| Prototype price lost per day after 30 days | 1/30 of it | 1/30 | 1/10 |
| Materials per wafer out, both families | $1,800 | $900 | $3,000 |
| A new lithography tool | $40M | $20M | $80M |
| A new tool in any other area | $6M | $3M | $12M |
| Qualifying a new tool for production (one-off) | $0.5M | $0.2M | $1M |
| Upkeep of an added tool (service, parts, power), a year | 10% of its price | 6% | 15% |
| Cleanroom floor an added tool needs, with its service space | 40 m² | 25 m² | 80 m² |
| A new wing (building shell and cleanroom fit-out) | $15,000 per m² | $8,000 | $30,000 |
| Fitting out spare space in the existing halls | $5,000 per m² | $2,500 | $10,000 |
| The overhead track bridge to a wing | $3M | $1.5M | $6M |
| Running today's fab (staff, power, upkeep of its 1,043 tools, overhead), a day | $3M | $2M | $4.5M |
| Depreciation of today's fab, a day | $2.5M | $1.5M | $4M |
| Life of a tool / a building / the bridge | 5 / 20 / 10 years | | |
| Horizon and discount rate for net present value | 5 years at 10% a year | 8% | 12% |

Two further assumptions, stated wherever money is shown:

- Today's tools already run family B's route (it copies product 3's route), so only new tools need qualifying.
  Restricting prototypes to half the tools (P4) costs nothing to set up.
- The existing halls have spare space for copies placed in them (D3). A wing (D2) is a new building.

## The profit and loss of one run

Over the scored window (days 120 to 300 in the two-family sweep), per day:

- **Revenue** = family A wafers out × A's price + Σ over family B lots out of wafers × B's price at that lot's
  cycle time (from its scheduled arrival, as in `fabsim::money`).
- **Materials** = all wafers out × materials per wafer.
- **Running costs** = today's fab a day + Σ added tools × price × upkeep rate / 365.
- **Operating cash a day** = revenue − materials − running costs.
- **Depreciation a day** = today's fab's + Σ each added item's purchase price / (its life × 365).
- **Operating profit a day** = operating cash a day − depreciation a day.

**Capital spent** on a change, once, at its start: Σ added tools × (price by area + qualification) + floor area ×
the wing's or the halls' price per m² + the bridge if there is a wing. Floor area = added tools × floor per tool.

## A change against today

For each change, on the same seeds: the change in operating profit a day and in operating cash a day, the capital
spent, and

- **Payback** = capital ÷ the change in operating cash a day, in days, when that change is above zero. Otherwise
  the change never pays back.
- **Net present value over 5 years** = − capital + the change in operating cash a day × Σ over days d = 1 … 1,825
  of (1 + r)^(−d/365), with r the yearly rate. What is left of the purchases' book value at 5 years is not counted.

Intervals are paired t intervals over seeds, Bonferroni over the sweep's 56 cells (each at level 0.05/56), as in
`docs/TWO-FAMILIES-SWEEP.md`. Capital is the same on every seed, so the intervals on the net present value and on
payback follow from the interval on the change in operating cash. Payback's interval is reported as "never" at
the end where the change in cash can be zero or below. Verdicts are better, worse or no clear effect.

## No rerun for the sweep

The sweep's `results/two-families/runs.tsv` holds, for every run, family A's wafers out a day, family B's lots,
wafers and mean cycle time, and money a day at all 36 points of the old price grid. Family B's revenue at the
grid's prices is money a day at a point with tools and metres free, less family A's wafers out a day (A's margin is
1 there). Revenue is proportional to the prototype price, so B's revenue in dollars is that figure × the dollar
price ÷ the grid's price. The grid has the decays 1/30 and 1/10 and a free period of 30 days, which is why the sheet
offers only those. What each cell adds (which groups are copied, so the area each tool belongs to) is found again
by `twofam::contested`, which needs no layout. So the profit and loss of every run is computed from the saved runs.
The same code scores the ask box's two-family questions from fresh runs.

## What is shown

- The floor page's numbers view: "Operating profit a day" in dollars replaces "Money a day". Each change shows its
  capital, payback and net present value. A "How money is counted" panel lists the whole price sheet, each marked
  assumed.
- The ask box's answers: the same three measures, and the capital each candidate spends.
- For the best change at each share of prototype orders: whether its verdict holds at each item's low and high
  value, one item at a time.

## Deliverables, in order

1. This spec and its tests, committed before any code.
2. `fabsim::pl`: the price sheet with its ranges, capital of a change, the profit and loss of a run, a change
   against today with payback and net present value.
3. `fabsim pl`: the profit and loss of the saved two-family sweep, with intervals, verdicts and the one-at-a-time
   check, written to `results/two-families/pl.json`.
4. The ask box scores two-family questions with `fabsim::pl`.
5. The floor page shows dollars, capital, payback and net present value, and the price sheet.

## Tests (`crates/fabsim/tests/pl.rs`, `web/tests/ui.test.mjs`)

1. Every item on the price sheet has low ≤ central ≤ high and is marked assumed.
2. A run's profit and loss adds up: operating profit = revenue − materials − running costs − depreciation, and
   operating cash = operating profit + depreciation.
3. Capital: the shared floor with any policy spends nothing. A wing spends its tools by area, their qualification,
   the wing's floor and the bridge. Copies in the halls spend their tools, their qualification and the halls'
   fit-out. Doubling the added tools doubles every part but the bridge.
4. Depreciation a day of an added item is its price ÷ (life × 365). Running costs grow by each added tool's upkeep.
5. Payback is capital ÷ the change in cash a day when that is above zero, and never otherwise. The net present
   value matches a day-by-day sum within $1, and falls as the rate rises.
6. Family B's revenue recovered from a saved run's price grid equals the revenue computed from the run's own lots,
   on a small two-family run, within 1e-6 per day.
7. `fabsim pl` on the saved sweep gives one row per run and, per share, every cell against the shared floor with
   today's order, with intervals at level 0.05/56 and a verdict. The shared floor with today's order has no capital.
8. The page's money measure is "Operating profit a day" in dollars, and the price sheet it shows carries every item
   with the word "assumed".

## Changes
