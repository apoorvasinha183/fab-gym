# Stages: what each hall does to the silicon

Written 27 Oct 2026, before the code (tests in `web/tests/stages.test.mjs`).
Everything here is on the SMT2020 model of a fab (Kopp, Hassoun, Kalir, Mönch 2020), a published model, not a
real fab. The model holds steps, tool groups, times, batches and breakdowns; it holds no chemistry. The
drawings are generic textbook steps of our own, marked "Illustration, not to scale", and every number beside
them comes from the page's own data (`web/data/shop.txt`, `web/data/areas.tsv`).

Decided by quiz (27 Oct): option A plus hall cards, flat cross-sections, the route strip inside the panel.
Ideas page: a private plan page (private).

## Stages

Ten stages cover the model's twelve areas, one stage for each hall on the floor:

| Stage key | Name | Areas | Hall |
| --- | --- | --- | --- |
| `diff` | Diffusion | Diffusion | Diffusion |
| `diel` | Dielectric | Dielectric | Dielectric |
| `litho` | Lithography | Litho | Lithography |
| `dry` | Dry etch | Dry_Etch | Dry etch |
| `imp` | Implant | Implant | Implant |
| `wet` | Wet etch and clean | Wet_Etch | Wet etch |
| `tf` | Thin film (metal) | TF | Thin film |
| `cmp` | Polishing (CMP) | Planar | Polishing |
| `chk` | Checks | Litho_Met, Def_Met, TF_Met | Checks |
| `hold` | Holding | Delay_32 | Holding |

The loop drawn around the wafer is eight stages in this order: diffusion, dielectric, lithography, dry etch,
implant, wet etch, thin film, polishing, then back to diffusion. Checks and cleaning are named in the centre,
since they come between most steps. The loop is simplified; the strip shows the real order.

## Pieces

1. `web/stages.js`, plain script, no dependencies. In the page it defines `window.FabStages`; under Node
   `module.exports`. It holds:
   - `STAGES`: key, name, areas, hall, what (one or two sentences), why (one or two sentences), a note on how
     the model holds the stage (no number in it), and the materials its drawing shows;
   - `LOOP`, the eight loop keys in order;
   - `stageOfArea(area)`, `byKey(key)`;
   - `visits(steps, areaOf)`: steps per stage on one route, where `steps` is the route's tool-group names and
     `areaOf` maps a group to its area;
   - `groupsPerStage(areaOf)`: tool groups per stage;
   - `strip(steps, areaOf)`: one cell per step (`i`, `group`, `area`, `stage`);
   - `crossSection(key, id)`: one self-contained SVG (viewBox 0 0 240 150, `role="img"`, an `aria-label`,
     its own `<defs>` with ids prefixed by `id`), or `null` for holding, which changes nothing on the wafer.
     The nine drawings tell one story: oxide grows, an insulating film is laid down, resist is patterned
     through a mask, a plasma cuts a trench, ions dope the silicon, a bath strips the resist, metal coats the
     wafer, polishing leaves metal only in the trench, and a check measures without changing anything.
2. `web/index.html`: a "How a chip is made" button in the title card, and a panel (`section#stages`, a
   dialog, hidden at first) holding the loop, the chosen stage's cross-section, what, why, its steps on each
   product's route and its tool groups, a "Show its hall" button, and the strip of the chosen product's route
   with the chosen stage lit. The panel says "on the SMT2020 model", "not a real fab" and "Illustration, not to
   scale". `stages.js` loads before `app.js`.
3. `web/app.js`: opens and closes the panel (the button, a close button, Escape); fills it from the routes the
   simulator returns and the areas file; "Show its hall" closes the panel and calls `flyToHall(i)`, which
   moves the view so the hall fills the middle of the floor and outlines it for a few seconds; the hall
   tooltip shows the group's stage, its cross-section and its one-line what.

## Checks

- Every area in `areas.tsv` belongs to exactly one stage, and the stages' halls are the floor's halls.
- Steps per stage on each route, counted from the page's data, equal the counts from the SMT2020 route
  files (product 3: 583 steps, product 4: 343), and tool groups per stage add up to 106: the model's 105
  tool groups and the holding group.
- Each of the nine drawings is one SVG whose every `url(#…)` points to an id defined inside it.
- No stage text names a company; every stage has a what and a why.
- The page wiring is in place (static checks of `index.html` and `app.js`); the look is checked by eye in a
  browser, in the floor page at 127.0.0.1:8765.

## Changes

- 27 Oct, before the code passed: the tool-group total is 106 (105 tool groups and the holding group); the
  test had asked for 105 against its own per-stage table, which sums to 106. The run command names the test
  file, since Node 22 does not take a folder.
