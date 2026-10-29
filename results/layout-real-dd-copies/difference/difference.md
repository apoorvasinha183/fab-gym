# What the copies change

On the SMT2020 model, a published research model of a wafer fab: a gigafab-style layout of our own design, not a real fab. Prices and placements assumed. NOT FOR CONSTRUCTION.

The decision: one copy of each of the three tool groups prototype orders load most, each placed right after its original in today's plan. Everything below comes from the same pipeline that draws today's fab.

| copy | area | tools |
|---|---|---|
| TF_FE_103@B | TF | 1 |
| Planar_FE_79@B | Planar | 1 |
| LithoMet_BE_18@B | Litho_Met | 1 |

- Tools: 1043 today, 1046 with the copies; 18 tools moved within their bay to make room, none changed bay block.
- Bays 42 and 42; hall lengths [255.8, 182.4] m and [255.8, 182.4] m; fab footprint 64,708 and 64,708 m2.
- Hoist travel at the two-family flows: 4,073.9 km a day today, 4,079.5 km with the copies (+0.14%). Exact for the stated flows.
- Capital from the central price sheet: $20.10M once (tools $18.00M, qualifying $1.50M, floor $0.60M); $15,699 a day in depreciation and upkeep.

## Code checks rerun

- Design development: 279 checks today, 279 for the variant; 0 verdicts change, 1 reasons change.
  - service.corridor_travel (P2; IBC 415.11.3.3): met to met. Today: chase_travel_ft 67.3 (computed along each chase to its open ends and doors) <= 75. Variant: chase_travel_ft 70.3 (computed along each chase to its open ends and doors) <= 75.
- Construction documents: 292 checks today, 292 for the variant; 0 verdicts change, 1 reasons change.
  - service.corridor_travel (P2; IBC 415.11.3.3): met to met. Today: chase_travel_ft 67.3 (computed along each chase to its open ends and doors) <= 75. Variant: chase_travel_ft 70.3 (computed along each chase to its open ends and doors) <= 75.

## Bill of materials, lines that change

| section | item | size | unit | today | variant | change |
|---|---|---|---|---|---|---|
| architecture | raised floor pedestals | pedestal | each | 176611.0 | 176610.0 | -1.0 |
| mechanical | exhaust_general_m3h | 500×600 mm | m | 48.0 | 96.0 | +48.0 |
| mechanical | exhaust_general_m3h | Ø500 mm | m | 48.0 | 0 | -48.0 |
| piping | drain_slurry_lpm | Ø50 mm | m | 314.6 | 0 | -314.6 |
| piping | drain_slurry_lpm | Ø65 mm | m | 241.2 | 555.8 | +314.6 |
| piping | pcw_lpm | Ø100 mm | m | 528.0 | 480.0 | -48.0 |
| piping | pcw_lpm | Ø125 mm | m | 192.0 | 240.0 | +48.0 |
| piping | tool drop | Ø400 mm | m | 1722.1 | 1727.2 | +5.1 |
| fire | gassensor | device | each | 637.0 | 638.0 | +1.0 |
| process equipment | deposition | tool | each | 149.0 | 150.0 | +1.0 |
| process equipment | metrology | tool | each | 57.0 | 58.0 | +1.0 |
| process equipment | polisher | tool | each | 34.0 | 35.0 | +1.0 |

## Sheets that change

- Design development: 14 of 37: A-301, E-601, E-602, FA-101, FP-201, G-101, G-102, M-101, M-201, M-401, M-601, M-602, PP-101, PP-301.
- Construction documents: 18 of 73: A-112, A-122, A-301, E-110, E-601, E-602, FA-101, FP-201, G-101, G-102, M-101, M-201, M-401, M-601, M-602, PP-101, PP-110, PP-301.

A sheet counts as changed when anything on it differs other than the source file named in its title block.
