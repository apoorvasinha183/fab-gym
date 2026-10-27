# What the cross aisles cost the fab

On the SMT2020 model. A layout of our own design. Not a real fab.

The question: Taken as service corridors, the chases need a door into the fab area within 75 ft of every point (IBC 415.11.3.3); where tools line a chase end to end, a cross aisle at mid-depth makes room for it. What do the cross aisles cost the fab?

Cross aisle 0.0 m before, 1.6 m after; chases 1.6 m. Bays 39 before, 42 after; buildings [232.5, 157.1] m before, [255.8, 182.4] m after. Hoist travel a day at the release rates: 2183 km before, 2260 km after (+3.5%).

10 paired seeds, 150 days, measured over days 60 to 150; each interval at level 0.010 (Bonferroni over five, so all cover at once with probability at least 95%).

| measure | before | after | after minus before (95%) | verdict |
|---|---|---|---|---|
| transport minutes a move | 4.613 | 4.635 | +0.022 (+0.022 to +0.022) | worse |
| cycle time, days | 50.126 | 49.823 | -0.302 (-0.775 to +0.170) | no clear effect |
| wafers out a day | 1307.111 | 1309.889 | +2.778 (-6.085 to +11.640) | no clear effect |
| mean WIP, lots | 2620.778 | 2610.481 | -10.297 (-30.690 to +10.097) | no clear effect |
| hot-lot cycle time, days | 23.802 | 23.819 | +0.017 (-0.069 to +0.103) | no clear effect |
