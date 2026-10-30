# Two families: which policy, which floor, at what share?

Pre-registered 28 October 2026, before any run of this design. Results are added below the line once the runs are
done; nothing above the line changes after that. From the SMT2020 testbed, with a layout of our own design; not a real
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
- Every result says "from the SMT2020 testbed"; real-fab effect: cannot say.

## Code

- `fabsim::twofam`: `Policy`, `policy_groups`, `apply_policy`, `b_first` (P1's choice).
- `fabsim::money`: `PriceGrid` with the central point first.
- `fabsim two-families`: runs this design and writes `results/two-families/`.
- Tests first: `crates/fabsim/tests/two_families_sweep.rs`.

---

## Results

Run 28 October 2026 on ProdLinuxSever (Linux x86_64, 4 threads, niced) with `fabsim two-families`, exactly the design
above, from commit 6029c41 (11,955 s). The layouts are reproducible on Linux x86_64; the layout optimiser's plans
differ by platform. Every run and every price point: `results/two-families/runs.tsv` and `prices.tsv`; the intervals:
`summary.json`.

**What it shows, from the SMT2020 testbed, at the central prices:**

- **Prototypes take about 100 days.** On today's fab family B's lots take 96 to 108 days from scheduled arrival to
  finish at every share (product 3's raw processing is about 25 days; the model's release rate runs above
  capacity). At the central prices a prototype wafer is worth nothing after 60 days, so in most cells family B
  earns nothing and money a day follows family A's wafers.
- **Family B first** is the best cell at x2 (+179 a day, 95% +122 to +237) and x4 (+751, +721 to +780): prototypes
  then take about 38 days and earn, while family A falls from 834 to 172 wafers a day at x4. At x8 it is worse
  (-566): family A's wafers out fall to zero and prototypes still take about 97 days. The verdict flips between x4
  and x8.
- **The family cap** is the best cell at x1 (+106, +71 to +141), and better at x2 (+22), worse from x4. It wins by
  holding prototypes out: at x1, on 3 of the 10 seeds no family-B lot finished in the window, which is also why its
  family-B cycle time has no interval at x1. Family A gains 135 to 511 wafers a day under the cap at every share.
- **The wing (D2) is worse at every share and policy**, and **copies in the halls (D3)** are no better at x1 and
  worse from x2. Each copy has one tool and family B may no longer use the original group, so at x8 family-B lots
  finished in the window fall from about 3,580 to about 1,280; the shorter cycle time of the copies counts only the
  lots that got through.
- **Reservation (P3)** never shows a clear gain in money; **qualification (P4)** loses money at x8 (-82) and is
  otherwise unclear.
- **Other prices.** With added tools and floor free, copies plus the cap become the best cell at x1 and x2 (+130 to
  +190), and copies alone still lose money at x8 at every price. With prototypes worth 40 a wafer, family B first
  gains +639 at x2 and +2,164 at x4.

Reading: on this model the question is less which floor than whether prototypes get through at all. A layout that
gives them one tool per copied group starves them as their share grows, and a cap pays only because late
prototypes are assumed worthless. Real-fab effect: cannot say.

### The scorer's tables

From the SMT2020 testbed, with a layout of our own design; not a real fab. 10 seeds (2000..2009), 300 days, window days 120 to 300; family B's lots drawn with seed 1 (the same lots on every seed). Each cell minus (D1 share, P0 today) at the same share, paired; intervals Bonferroni over 56 cells (each at level 0.00089), so all cover at once with probability at least 95%. Every price assumed. Real-fab effect: cannot say.

### money a day (central prices, wafers of family-A margin)

| share | strategy | P0 today | P1 family B first | P2 family cap | P3 reservation | P4 qualification |
|---|---|---|---|---|---|---|
| x1 | D1 share | 1139.13 (mean) | +23.46 (+5.68 to +41.24) better | +105.79 (+70.67 to +140.91) better | -1.84 (-18.77 to +15.08) no clear effect | -3.60 (-30.17 to +22.98) no clear effect |
| x1 | D2 wing | -117.83 (-137.68 to -97.97) worse | -154.03 (-190.30 to -117.76) worse | -69.49 (-98.39 to -40.59) worse | -119.16 (-140.88 to -97.45) worse | -115.25 (-139.21 to -91.29) worse |
| x1 | D3 copies | +0.31 (-22.39 to +23.00) no clear effect | -31.26 (-77.50 to +14.98) no clear effect | +53.11 (+25.48 to +80.73) better | +1.72 (-18.81 to +22.26) no clear effect | +2.65 (-23.34 to +28.64) no clear effect |
| x2 | D1 share | 1145.58 (mean) | +179.47 (+122.22 to +236.71) better | +22.10 (+6.87 to +37.33) better | -26.16 (-41.38 to -10.94) worse | -1.03 (-9.86 to +7.81) no clear effect |
| x2 | D2 wing | -193.68 (-213.92 to -173.45) worse | -322.14 (-361.24 to -283.05) worse | -141.91 (-161.73 to -122.10) worse | -204.94 (-223.12 to -186.76) worse | -197.60 (-222.14 to -173.06) worse |
| x2 | D3 copies | -73.14 (-94.03 to -52.25) worse | -211.61 (-248.78 to -174.44) worse | -14.94 (-41.23 to +11.34) no clear effect | -78.92 (-90.37 to -67.47) worse | -79.33 (-98.92 to -59.74) worse |
| x4 | D1 share | 1210.63 (mean) | +750.54 (+720.60 to +780.47) better | -127.01 (-140.97 to -113.04) worse | +5.20 (-17.89 to +28.28) no clear effect | -10.81 (-31.49 to +9.87) no clear effect |
| x4 | D2 wing | -279.92 (-298.41 to -261.42) worse | -700.78 (-733.17 to -668.40) worse | -313.08 (-328.24 to -297.91) worse | -278.28 (-307.85 to -248.72) worse | -282.81 (-308.24 to -257.39) worse |
| x4 | D3 copies | -160.70 (-174.52 to -146.87) worse | -588.98 (-614.37 to -563.59) worse | -195.38 (-207.50 to -183.27) worse | -159.20 (-175.56 to -142.84) worse | -163.74 (-185.41 to -142.06) worse |
| x8 | D1 share | 1452.18 (mean) | -566.41 (-603.94 to -528.89) worse | -504.17 (-532.67 to -475.67) worse | +3.20 (-24.90 to +31.31) no clear effect | -82.23 (-103.42 to -61.04) worse |
| x8 | D2 wing | -1092.80 (-1116.07 to -1069.53) worse | -1648.62 (-1666.24 to -1631.01) worse | -581.37 (-615.62 to -547.11) worse | -1092.16 (-1113.70 to -1070.62) worse | -968.62 (-991.65 to -945.59) worse |
| x8 | D3 copies | -970.54 (-991.31 to -949.78) worse | -1528.61 (-1544.40 to -1512.81) worse | -460.87 (-493.89 to -427.84) worse | -971.20 (-993.48 to -948.92) worse | -848.06 (-875.69 to -820.42) worse |

### family A wafers out a day

| share | strategy | P0 today | P1 family B first | P2 family cap | P3 reservation | P4 qualification |
|---|---|---|---|---|---|---|
| x1 | D1 share | 1109.54 (mean) | -41.61 (-56.90 to -26.32) worse | +135.38 (+104.67 to +166.08) better | -22.00 (-43.19 to -0.81) worse | -0.76 (-18.31 to +16.79) no clear effect |
| x1 | D2 wing | +93.31 (+71.17 to +115.44) better | +5.71 (-25.71 to +37.13) no clear effect | +159.10 (+130.07 to +188.13) better | +90.79 (+68.20 to +113.39) better | +96.00 (+78.02 to +113.98) better |
| x1 | D3 copies | +89.56 (+68.70 to +110.41) better | +8.00 (-27.21 to +43.21) no clear effect | +161.69 (+133.27 to +190.12) better | +92.36 (+70.72 to +114.00) better | +91.86 (+70.51 to +113.22) better |
| x2 | D1 share | 1009.42 (mean) | -280.15 (-308.15 to -252.16) worse | +158.26 (+144.20 to +172.33) better | -46.43 (-61.67 to -31.19) worse | +1.79 (-8.72 to +12.31) no clear effect |
| x2 | D2 wing | +53.90 (+37.64 to +70.16) better | -120.21 (-158.87 to -81.55) worse | +190.85 (+172.38 to +209.31) better | +44.64 (+27.40 to +61.87) better | +52.92 (+37.60 to +68.23) better |
| x2 | D3 copies | +56.29 (+41.57 to +71.01) better | -126.72 (-151.34 to -102.10) worse | +197.82 (+174.87 to +220.77) better | +43.61 (+31.80 to +55.43) better | +50.58 (+35.05 to +66.11) better |
| x4 | D1 share | 834.33 (mean) | -662.57 (-675.55 to -649.59) worse | +249.29 (+234.47 to +264.11) better | -2.29 (-10.55 to +5.96) no clear effect | -3.78 (-13.94 to +6.39) no clear effect |
| x4 | D2 wing | +2.78 (-6.21 to +11.76) no clear effect | -505.17 (-526.94 to -483.39) worse | +264.22 (+246.89 to +281.55) better | -1.49 (-12.45 to +9.48) no clear effect | +0.99 (-8.03 to +10.00) no clear effect |
| x4 | D3 copies | +0.67 (-5.74 to +7.07) no clear effect | -507.81 (-523.42 to -492.19) worse | +261.92 (+244.89 to +278.95) better | -0.67 (-8.18 to +6.85) no clear effect | +1.42 (-8.55 to +11.38) no clear effect |
| x8 | D1 share | 561.43 (mean) | -561.43 (-570.62 to -552.24) worse | +386.58 (+374.61 to +398.56) better | +1.17 (-8.33 to +10.67) no clear effect | -0.62 (-8.98 to +7.73) no clear effect |
| x8 | D2 wing | -1.60 (-9.08 to +5.89) no clear effect | -560.21 (-570.76 to -549.65) worse | +510.39 (+489.80 to +530.98) better | -1.10 (-10.26 to +8.07) no clear effect | +122.71 (+108.69 to +136.73) better |
| x8 | D3 copies | +0.15 (-8.23 to +8.53) no clear effect | -560.43 (-569.14 to -551.72) worse | +510.89 (+491.79 to +529.99) better | -0.21 (-7.42 to +7.00) no clear effect | +123.17 (+110.24 to +136.09) better |

### family B cycle time, days from scheduled arrival

| share | strategy | P0 today | P1 family B first | P2 family cap | P3 reservation | P4 qualification |
|---|---|---|---|---|---|---|
| x1 | D1 share | 105.34 (mean) | -45.01 (-48.49 to -41.52) better | NaN (NaN to NaN) no clear effect | -33.16 (-38.07 to -28.25) better | +1.14 (-3.08 to +5.36) no clear effect |
| x1 | D2 wing | -12.22 (-17.12 to -7.32) better | -40.05 (-44.48 to -35.62) better | NaN (NaN to NaN) no clear effect | -14.61 (-18.41 to -10.81) better | -13.01 (-17.31 to -8.70) better |
| x1 | D3 copies | -13.12 (-17.85 to -8.39) better | -39.23 (-45.02 to -33.44) better | NaN (NaN to NaN) no clear effect | -12.50 (-17.78 to -7.23) better | -13.58 (-19.30 to -7.87) better |
| x2 | D1 share | 97.47 (mean) | -53.58 (-54.97 to -52.19) better | +58.66 (+51.97 to +65.35) worse | -25.67 (-27.78 to -23.55) better | +1.45 (-0.61 to +3.51) no clear effect |
| x2 | D2 wing | -20.10 (-24.67 to -15.53) better | -25.38 (-30.85 to -19.90) better | +65.21 (+59.39 to +71.03) worse | -20.63 (-24.10 to -17.16) better | -20.18 (-27.74 to -12.61) better |
| x2 | D3 copies | -20.73 (-26.05 to -15.40) better | -27.24 (-34.22 to -20.26) better | +65.10 (+61.90 to +68.30) worse | -20.03 (-27.19 to -12.87) better | -20.41 (-25.78 to -15.04) better |
| x4 | D1 share | 103.92 (mean) | -65.96 (-67.06 to -64.85) better | +44.48 (+41.93 to +47.03) worse | -0.50 (-2.03 to +1.03) no clear effect | +1.18 (-0.19 to +2.54) no clear effect |
| x4 | D2 wing | -15.69 (-19.34 to -12.04) better | -24.95 (-28.74 to -21.16) better | +54.40 (+51.24 to +57.55) worse | -16.37 (-20.11 to -12.64) better | -16.97 (-19.80 to -14.14) better |
| x4 | D3 copies | -16.81 (-20.20 to -13.41) better | -24.43 (-28.82 to -20.03) better | +54.47 (+51.73 to +57.20) worse | -15.75 (-17.81 to -13.70) better | -16.56 (-21.62 to -11.49) better |
| x8 | D1 share | 105.34 (mean) | -6.79 (-11.39 to -2.18) better | +48.27 (+46.21 to +50.33) worse | -0.58 (-2.43 to +1.27) no clear effect | -11.62 (-13.78 to -9.47) better |
| x8 | D2 wing | -21.55 (-27.12 to -15.98) better | -26.13 (-31.69 to -20.57) better | +94.20 (+90.03 to +98.36) worse | -21.78 (-26.59 to -16.96) better | -20.76 (-26.38 to -15.14) better |
| x8 | D3 copies | -21.91 (-28.56 to -15.26) better | -26.07 (-30.98 to -21.16) better | +93.98 (+89.67 to +98.30) worse | -21.52 (-27.36 to -15.67) better | -21.38 (-27.81 to -14.96) better |

### Best cell per share (central prices)

- x1: x1 D1 share P2 family cap (1244.92 a day), against D1 P0 +105.79 (+70.67 to +140.91) better
- x2: x2 D1 share P1 family B first (1325.04 a day), against D1 P0 +179.47 (+122.22 to +236.71) better
- x4: x4 D1 share P1 family B first (1961.17 a day), against D1 P0 +750.54 (+720.60 to +780.47) better
- x8: x8 D1 share P3 reservation (1455.39 a day), against D1 P0 +3.20 (-24.90 to +31.31) no clear effect

### Where each cell's money verdict changes, over share

- D1 share P1 family B first: flips between x4 and x8 (unclear at [])
- D1 share P2 family cap: flips between x2 and x4 (unclear at [])
- D1 share P3 reservation: worse from the SMT2020 testbed at some shares, no clear effect at the others
- D1 share P4 qualification: worse from the SMT2020 testbed at some shares, no clear effect at the others
- D2 wing P0 today: same verdict at every share: worse from the SMT2020 testbed
- D2 wing P1 family B first: same verdict at every share: worse from the SMT2020 testbed
- D2 wing P2 family cap: same verdict at every share: worse from the SMT2020 testbed
- D2 wing P3 reservation: same verdict at every share: worse from the SMT2020 testbed
- D2 wing P4 qualification: same verdict at every share: worse from the SMT2020 testbed
- D3 copies P0 today: worse from the SMT2020 testbed at some shares, no clear effect at the others
- D3 copies P1 family B first: worse from the SMT2020 testbed at some shares, no clear effect at the others
- D3 copies P2 family cap: flips between x1 and x4 (unclear at [2.0])
- D3 copies P3 reservation: worse from the SMT2020 testbed at some shares, no clear effect at the others
- D3 copies P4 qualification: worse from the SMT2020 testbed at some shares, no clear effect at the others

### P4: break-even qualification cost per unqualified tool a day (central prices)

- x1 D1 share: P4 loses 3.60 a day against P0 with 5 tools unqualified: it pays when qualifying one tool costs more than 0.72 a day
- x1 D2 wing: P4 loses -2.58 a day against P0 with 19 tools unqualified: it pays when qualifying one tool costs more than -0.14 a day
- x1 D3 copies: P4 loses -2.35 a day against P0 with 19 tools unqualified: it pays when qualifying one tool costs more than -0.12 a day
- x2 D1 share: P4 loses 1.03 a day against P0 with 10 tools unqualified: it pays when qualifying one tool costs more than 0.10 a day
- x2 D2 wing: P4 loses 3.92 a day against P0 with 6 tools unqualified: it pays when qualifying one tool costs more than 0.65 a day
- x2 D3 copies: P4 loses 6.19 a day against P0 with 6 tools unqualified: it pays when qualifying one tool costs more than 1.03 a day
- x4 D1 share: P4 loses 10.81 a day against P0 with 4 tools unqualified: it pays when qualifying one tool costs more than 2.70 a day
- x4 D2 wing: P4 loses 2.90 a day against P0 with 13 tools unqualified: it pays when qualifying one tool costs more than 0.22 a day
- x4 D3 copies: P4 loses 3.04 a day against P0 with 13 tools unqualified: it pays when qualifying one tool costs more than 0.23 a day
- x8 D1 share: P4 loses 82.23 a day against P0 with 4 tools unqualified: it pays when qualifying one tool costs more than 20.56 a day
- x8 D2 wing: P4 loses -124.19 a day against P0 with 20 tools unqualified: it pays when qualifying one tool costs more than -6.21 a day
- x8 D3 copies: P4 loses -122.49 a day against P0 with 20 tools unqualified: it pays when qualifying one tool costs more than -6.12 a day
