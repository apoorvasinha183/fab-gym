A gigafab-style layout of our own design on the SMT2020 model (docs/FAB-LAYOUT.md); every placement number is assumed. Not a real fab.

Realistic campus (docs/FAB-LOOK.md): tools at true size by kind from the size book, each tool group in the phase that sends it most of its lots.

Optimiser: simulated annealing, 200000 moves x 4 restarts, seed 1, 13.1 s. A heuristic; the metres are exact for the stated flows.

Moves a day at the release rates: 22782.9; crossing the bridge: 629.3 a day.

| plan | OHT metres a day | metres a move | P1 length (north / south) | P2 length (north / south) |
|---|---|---|---|---|
| plain | 3054667 | 134.1 | 253 (201 / 253) | 156 (151 / 156) |
| optimised | 2180617 | 95.7 | 239 (215 / 239) | 155 (155 / 151) |

The optimised plan carries 28.6% fewer metres a day.
