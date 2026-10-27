A gigafab-style layout of our own design on the SMT2020 model (docs/FAB-LAYOUT.md); every placement number is assumed. Not a real fab.

Realistic campus (docs/FAB-LOOK.md): tools at true size by kind from the size book, each tool group in the phase that sends it most of its lots.

Optimiser: simulated annealing, 200000 moves x 4 restarts, seed 1, 13.9 s. A heuristic; the metres are exact for the stated flows.

Moves a day at the release rates: 22782.9; crossing the bridge: 629.3 a day.

| plan | OHT metres a day | metres a move | P1 length (north / south) | P2 length (north / south) |
|---|---|---|---|---|
| plain | 3074837 | 135.0 | 256 (256 / 203) | 157 (153 / 157) |
| optimised | 2183035 | 95.8 | 232 (232 / 226) | 157 (157 / 152) |

The optimised plan carries 29.0% fewer metres a day.
