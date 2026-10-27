A gigafab-style layout of our own design on the SMT2020 model (docs/FAB-LAYOUT.md); every placement number is assumed. Not a real fab.

Realistic campus (docs/FAB-LOOK.md): tools at true size by kind from the size book, each tool group in the phase that sends it most of its lots.

Optimiser: simulated annealing, 200000 moves x 4 restarts, seed 1, 13.4 s. A heuristic; the metres are exact for the stated flows.

Moves a day at the release rates: 22782.9; crossing the bridge: 629.3 a day.

| plan | OHT metres a day | metres a move | P1 length (north / south) | P2 length (north / south) |
|---|---|---|---|---|
| plain | 3226371 | 141.6 | 267 (267 / 220) | 179 (179 / 177) |
| optimised | 2260196 | 99.2 | 256 (256 / 231) | 182 (174 / 182) |

The optimised plan carries 29.9% fewer metres a day.
