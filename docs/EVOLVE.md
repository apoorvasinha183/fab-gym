# Floor and rules, evolved together (E2)

Written 28 October 2026, before the code. On the SMT2020 model, with a layout of our own design; not a real fab, not
real data. Agents propose, the simulator scores, a person signs.

## The question

The two-family sweep (`docs/TWO-FAMILIES-SWEEP.md`) tests 15 layout-and-policy pairs we wrote down. Can a search
that breeds floors and dispatch rules together find a pair that makes more money a day than the best of those 15?

Decided by quiz on 28 October (`~/HACKATHON-README.md`): joint evolutionary search (E2 of
`docs/two-wafers/two-wafers.tex`), ant colony search for the floor and genetic programming for the rules, run on the
Linux server after the sweep. Language-model proposals (E4) come later. The method follows the idea of a hybrid of ant
colony search for layout and genetic programming for dispatching rules (Xu and Wan, IEEE Access 2024, as cited in the
two-wafers note); nothing here claims to reproduce that paper.

## What is searched (one individual)

- **Floor (ant colony).** For each of the `k` groups family B loads most (`twofam::contested`, `k` = 12), how many
  one-group copies serving family B to add: 0 to 3 tools, at most 8 tools in all. Where the copies go: in the two
  halls (as D3) or in a wing on pad P3 (as D2).
- **Cap (ant colony).** Family B's cap: none, or 0.75, 1, 1.5 or 2 times family B's average load (lots a day × product
  3's raw processing days).
- **Rule (genetic programming).** A dispatch key: an expression over a candidate's fields, the same 14 numbers a rule in
  the sandbox reads (`fabrule::CAND_FIELDS`), with constants. The candidate with the smallest key starts; ties keep
  today's pick, and a key that is not a number counts as the largest (the sandbox's convention). Functions: `+`, `-`,
  `*`, protected division (`a / b`, 1 when `|b| < 1e-9`), `min`, `max`, and `if a > b then c else d`. Depth at most 5.
  Every rule prints as a sandbox rule (`pub fn key(c: &Cand, _x: &Ctx) -> f64`), so the winner can be scored by the
  same scorer as any rule Meta's model writes.

## The search (one run of `fabsim evolve`)

- **Population** 16, **generations** 12, **training seeds** 3000 to 3002, **runs** of 240 days scored on days 120 to
  240, **share** of family B a parameter (first run: ×4).
- **Fitness:** money a day at the central prices (`money::PriceGrid`, first point), mean over the training seeds.
- **Floors** are laid out by the optimiser at 20,000 moves and one restart during the search, cached by floor; the
  winner is laid out again at the full setting for the held-out score.
- **Ant colony (MAX-MIN):** a choice's chance is proportional to its pheromone times its heuristic (the group's load
  for any copy, 1 for none); groups are visited in a random order and a choice that would pass 8 tools becomes 0.
  After each generation every pheromone evaporates by 20% and the best 4 individuals deposit 0.4, 0.3, 0.2 and
  0.1 on their choices; pheromone stays between 0.05 and 5.
- **Genetic programming:** the best individual is kept whole (floor, cap and rule); the other rules come from
  tournaments of 3, with subtree crossover (chance 0.7) and subtree mutation (chance 0.2), never deeper than 5. The
  first generation's rules are random trees of depth 2 to 4, with today's rule (`is_default`) and first-in-first-out
  (`-waited_minutes`) among them.
- **Pairing:** individual `i` of a generation is the `i`-th floor the ants build with the `i`-th rule of the new
  population (the kept individual is first).
- Every draw comes from string-seeded streams, so a search with the same seed gives the same individuals and the same
  fitness on any number of threads.

## The claim (scored once)

- The **three best individuals** of the search by training fitness, each laid out at the full setting, run as the
  sweep runs (300 days, window 120 to 300, seeds 2000 to 2009, same family-B lots) against two references at the
  same share, also rerun on those seeds: the yardstick (D1, P0) and the sweep's best cell at that share.
- Paired differences in money a day at the central prices, Bonferroni over the 6 comparisons (each at level
  0.05/6). Verdicts better, worse or no clear effect. The winning rules are printed in full.
- Reported whatever it shows. "On the SMT2020 model"; real-fab effect: cannot say.

## Code

- `fabsim::gp`: expression trees (random, evaluate, print as a sandbox rule, crossover, mutation).
- `fabsim::evolve`: the genome, the ant colony, the loop, the held-out claim.
- `fabsim evolve --share S --threads T --out O`.

## Tests (`crates/fabsim/tests/evolve.rs`, `crates/fabrule/tests/evolved.rs`)

1. **Trees:** today's rule as a tree runs to the same log as no chooser; first-in-first-out as a tree runs to the
   same log as `Policy::Fifo`; protected division and the depth limit hold; random trees, crossover and mutation are
   deterministic by seed and never exceed depth 5.
2. **Printed rules:** a random tree printed as a sandbox rule, compiled and run in the sandbox, gives the same log as
   the tree run in the simulator.
3. **Ants:** a built floor never passes 8 tools and copies only candidate groups; evaporation and deposit follow the
   stated rule exactly; pheromone stays within its bounds; the same seed builds the same floors.
4. **Genome to shop:** the copies, their place and the cap appear in the shop exactly as the genome says; a genome of
   no copies and no cap leaves the shop's records unchanged.
5. **The loop:** on a toy shop, the same seed gives the same history on 1 and 3 threads; the best training fitness
   never falls from one generation to the next (the best is kept whole).

## Changes

- 28 Oct, test 3: the test expected the best choice's pheromone to reach the ceiling of 5 after many updates by the
  best floor alone. Under the stated rule it settles where evaporation equals the deposit, 0.4 / 0.2 = 2 (the
  ceiling binds only when the four depositors agree, 1.0 / 0.2 = 5). The test now checks the fixed point.
- 28 Oct, test 5: on the toy shop many individuals tie (spare capacity, so every floor without copies earns the same).
  The search ranks ties by position, earlier first; the test took the last of the tied and now takes the first.

---

## Results

Run 28 to 29 October 2026 on ProdLinuxSever (Linux x86_64, 4 threads, niced) with `fabsim evolve --share 4`, exactly
the design above, from commit bf03497 (10,405 s). Every individual of every generation: `results/evolve-x4/history.tsv`;
the winning rules: `results/evolve-x4/rules/`.

**What it shows, on the SMT2020 model, at x4:** the search lost. All three evolved pairs are worse than the
yardstick (-93 to -130 a day) and far worse than the sweep's best cell, family B first (-844 to -881). Their rules
collapsed to a constant (every lot gets the same key, so today's rule decides), and their floors copy four or five
groups with a cap at family B's average load: volume wafers rise from 834 to about 1,200 a day, prototypes take
about 240 days and earn nothing, and the copied tools cost money. Training money climbed from 985 to 1,117 over the
12 generations without ever finding a rule that puts prototypes first, which the sweep shows is worth about +750 a
day here. At this size (16 pairs, 12 generations, 3 training seeds) a blind search did worse than one written-down
policy. Real-fab effect: cannot say.

### The claim as written by the run

On the SMT2020 model, with a layout of our own design; not a real fab. Family B at x4. Search: population 16, 12 generations, training seeds 3000..3002, 240 days scored from day 120; layouts at 20000 optimiser moves. Claim: the three best distinct individuals laid out at the full setting, 10 held-out seeds (2000..2009), 300 days, window days 120 to 300; paired, Bonferroni over 6 comparisons (each at level 0.0083). Money a day at the central prices, in wafers of family-A margin; every price assumed. Run on linux x86_64. Real-fab effect: cannot say.

| arm | money a day | family A wafers a day | family B cycle days | copies | cap | wing |
|---|---|---|---|---|---|---|
| yardstick: D1 share, P0 today | 1210.63 | 834.33 | 103.92 | as the cell | as the cell | - |
| sweep's best: D1 share P1 family B first | 1961.17 | 171.76 | 37.96 | as the cell | as the cell | - |
| evolved #1 | 1080.36 | 1183.96 | 247.30 | TF_FE_103×1, DE_FE_62×1, LithoMet_BE_18×1, Planar_FE_77×1 | 1× load | false |
| evolved #2 | 1117.19 | 1220.79 | 235.70 | TF_FE_113×1, LithoMet_BE_18×1, Planar_FE_77×1, DE_FE_51×1 | 1× load | false |
| evolved #3 | 1083.04 | 1213.64 | 234.13 | TF_FE_103×1, TF_FE_113×1, LithoMet_BE_18×1, Planar_FE_77×1, DE_FE_51×1 | 1× load | false |

### Each evolved individual minus each reference (money a day)

- evolved #1 minus yardstick: D1 share, P0 today: -130.27 (-148.18 to -112.37), worse
- evolved #1 minus sweep's best: D1 share P1 family B first: -880.81 (-897.39 to -864.23), worse
- evolved #2 minus yardstick: D1 share, P0 today: -93.44 (-110.10 to -76.78), worse
- evolved #2 minus sweep's best: D1 share P1 family B first: -843.98 (-866.08 to -821.88), worse
- evolved #3 minus yardstick: D1 share, P0 today: -127.59 (-143.35 to -111.84), worse
- evolved #3 minus sweep's best: D1 share P1 family B first: -878.13 (-898.29 to -857.98), worse

### The evolved rules

evolved #1 (training money 1116.54 a day):

```rust
pub fn key(c: &Cand, _x: &Ctx) -> f64 {
    60.0
}
```

evolved #2 (training money 1100.91 a day):

```rust
pub fn key(c: &Cand, _x: &Ctx) -> f64 {
    ((60.0).max(1440.0)).max((1.0 * 60.0))
}
```

evolved #3 (training money 1090.58 a day):

```rust
pub fn key(c: &Cand, _x: &Ctx) -> f64 {
    ((60.0).max(1440.0)).max((1.0 * 60.0))
}
```

Best training money by generation: 984.8, 996.5, 1004.3, 1022.1, 1055.5, 1055.5, 1055.5, 1055.5, 1090.6, 1116.5, 1116.5, 1116.5

