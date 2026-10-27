# What a wider chase costs the fab

On the SMT2020 model. A layout of our own design. Not a real fab.

The question: If the 1.5 m chases are service corridors, IBC 415.11.3.4 asks at least 5 ft (1.524 m). What does a 1.6 m chase cost the fab?

Chase 1.5 m before, 1.6 m after. Hoist travel a day at the release rates: 2181 km before, 2183 km after (+0.1%).

10 paired seeds, 150 days, measured over days 60 to 150; each interval at level 0.010 (Bonferroni over five, so all cover at once with probability at least 95%).

| measure | before | after | after minus before (95%) | verdict |
|---|---|---|---|---|
| transport minutes a move | 4.612 | 4.613 | +0.001 (+0.001 to +0.001) | worse |
| cycle time, days | 49.756 | 50.126 | +0.370 (-0.302 to +1.042) | no clear effect |
| wafers out a day | 1311.833 | 1307.111 | -4.722 (-16.780 to +7.336) | no clear effect |
| mean WIP, lots | 2610.827 | 2620.778 | +9.951 (-9.034 to +28.936) | no clear effect |
| hot-lot cycle time, days | 23.834 | 23.802 | -0.033 (-0.152 to +0.086) | no clear effect |
