# The size book: how big things are in the realistic fab

Every dimension the realistic views use, for the gigafab-style layout of our
own design on the SMT2020 model. Each row is **cited** (a source opened on
27 Oct 2026, with where in it) or **assumed** (our own value, chosen to look
right; no source opened). A row marked *secondary* comes from a listing or a
third party, not the maker. Tests read the machine-readable copy of these
tables (`viz/look/sizes.json`) and hold every model to them within 5%.

Width (W) runs along the bay aisle, depth (D) into the bay from the aisle,
height (H) up from the raised floor. Metres unless stated.

## Carriers and the hoist

| item | value | source |
|---|---|---|
| wafers in a lot | 25 | cited: SMT2020 `order.txt`, column PIECES, every row |
| carrier (FOUP), outside W × D × H | 0.426 × 0.355 × 0.338 | cited: Entegris, *A300 FOUPs* datasheet (1220-7309ENT-0621), p. 2, 25-capacity |
| carrier mass with 25 wafers | 8.2 kg | cited: same, p. 2 |
| wafer pitch in the carrier | 10 mm | cited: same, p. 2 |
| hoist vehicle, L × W × H | 0.90 × 0.60 × 0.80 | assumed |
| hoist rail, underside above raised floor | 4.20 | assumed |
| load port: carrier seat above raised floor | 0.90 | assumed |
| load ports per tool | 2 (metrology 1, scanner and track 4, stocker 0) | assumed |
| hoist effective speed | 150 m/min | assumed (unchanged from FAB-LAYOUT.md) |

## The building

| item | value | source |
|---|---|---|
| floors | support floor, cleanroom, air space | assumed |
| support floor clear height | 6.0 | assumed |
| waffle slab thickness | 0.9 | assumed |
| raised floor above the slab | 0.6 | assumed |
| raised floor panel | 0.600 × 0.600, 38 mm thick, 38% open | cited: DKC, raised floor plate PFP3860ST-BL-P38, product page |
| cleanroom, raised floor to filter ceiling | 5.5 | assumed |
| fan filter unit | 1.200 × 0.600, H14 filter | cited: item, *Filter Fan Unit 1200x600* (71642), product page |
| share of the bay ceiling under filters | 100% in bays, 0% over chases | assumed |
| air space above the filters | 4.0 | assumed |
| roof and plant on it | 1.5 slab, plant 4.0 | assumed |
| column grid | 12.0 × 12.0 (the spine and aisles avoid columns) | assumed |
| lithography light | blocks below 500 nm, passes above 540 nm (yellow) | cited: MicroChemicals, *Lithoprotect Yellowlight* product page |
| other bays' light | white, 5,000 K | assumed |

## Tools, by kind

Each SMT2020 tool group maps to one kind by its name. `Delay_32` is a timed
hold in a stocker and takes no floor space.

| kind | groups | W × D × H | source |
|---|---|---|---|
| scanner | `Litho_*` | 4.5 × 11.0 × 2.9 | assumed |
| coat and develop track | `LithoTrack_*` | 3.5 × 7.0 × 2.5 | assumed |
| metrology | `LithoMet_*`, `Litho_REG_*`, `TF_Met_*` | 1.8 × 2.8 × 2.2 | assumed |
| inspection | `DefMet_*`, `DefMEt_*` | 2.2 × 3.4 × 2.3 | assumed |
| etch cluster tool | `DE_*` | 3.5 × 5.5 × 2.6 | assumed |
| deposition cluster tool | `Dielectric_*`, `TF_*` (not `TF_Met`) | 3.5 × 5.5 × 2.7 | assumed |
| epitaxy | `EPI_*` | 4.0 × 6.0 × 2.8 | assumed |
| vertical furnace | `Diffusion_*` | 1.5 × 2.0 × 3.2 (3.0 m² a tube) | cited footprint: Koyo Thermo Systems comparison table as reproduced by Kiel University, *Electronic Materials*, ch. 6 illustration 6.2.4, VF5300 "Footprint / tube 3.0 m² (grey room)" (*secondary*); height assumed |
| ion implanter | `Implant_*` | 3.6 × 8.1 × 3.1 | cited: used Purion M listing, "Mainframe dim (cm): 360 x 810 x 310", labelled an estimate, axes not named (*secondary*) |
| polisher (CMP) | `Planar_*` | 3.0 × 6.0 × 2.6 | assumed |
| wet bench | `WE_*` | 2.5 × 10.0 × 2.8 | assumed |
| stocker | AMHS stockers, `Delay_32` | 3.0 × 12.0 × 5.0 | assumed |
| status light | every tool | 0.6 tall, on the aisle face | assumed |

A bay is two rows of tools facing an aisle: bay width = 2 × (deepest tool
in the bay + 1.5 m chase) + 3.5 m aisle (FAB-LAYOUT.md).

## The phase rule (settled 27 Oct)

Each tool group goes in the phase that sends it most of its lots (by the
flows of FAB-LAYOUT.md), instead of by its name. Phase 1 starts as the front
end and Phase 2 as the back end by name; a group moves when the other phase
sends it more lots. `LithoTrack_FE_95` (78% of its lots from back-end groups)
is the case that raised it.

## Sources opened

- Entegris, *A300 FOUPs* datasheet, 2021,
  https://www.entegris.com/content/dam/product-assets/a300foups/datasheet-a300foups.pdf
- DKC, raised floor plate 600×600, steel, 38 mm, perforation 38%,
  https://www.dkc.ru/en/catalog/1669/pfp3860st-bl-p38/
- item, Filter Fan Unit 1200x600,
  https://www.item24.com/en-us/filter-fan-unit-1200x600-71642
- MicroChemicals, Lithoprotect Yellowlight,
  https://microchemicals.com/products/yellowlight_uv_filter.html
- Kiel University, *Electronic Materials* illustration 6.2.4 (table from
  Koyo Thermo Systems),
  https://www.tf.uni-kiel.de/matwis/amat/elmat_en/kap_6/illustr/i6_2_4.html
- Used Axcelis Purion M listing,
  https://www.openbare-verkopen.be/lot/651562
- SMT2020 high-volume testbed, `order.txt` (Kopp, Hassoun, Kalir and Mönch,
  2020)

Searched for and not found open: scanner, track, CMP, wet bench and etch tool
sizes from their makers; SEMI E72 (equipment footprint) and E47.1 (FOUP) are
paid; fab floor heights. Those rows stay assumed.
