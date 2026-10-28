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
