# The Live view on the real building

Decided by quiz on 29 Oct 2026. The founder: "Is there a way to modify the live view like look in rails, it looks
not 1 to 1. I like the 2.5D look ... I also want the rails to show the movement of the individual wafers". Chosen:
the Live view becomes the real building, running the browser simulator with the fleet, over a Rails lens drawn in
2.5D. On the SMT2020 model, a gigafab-style layout of our own design; not a real fab.

## What changes

1. **The browser simulator runs today's US building with its fleet.**
   - Its shop is the design-development layout with tool ports, bay rails and 160 vehicles (`web/data/shop-real.txt`,
     written by `web/build.sh` from `data/layout-real-dd/optimised.shop.txt`).
   - `fg_run` keeps every vehicle's stretches and hoists as two flat arrays for the page (`fabweb::fleet_arrays`).
2. **The floor is the building, in metres, north up, in the same 2.5D look.**
   - It shows the halls, the bays, every tool at its place coloured by its state, the drawn rails and the stockers
     (`web/data/building.json`, written from the scene and the simulator's track).
   - The tilt, zoom, pan, labels, ticker, hover cards and time bar are the page's own, unchanged.
3. **Lots on the rails.**
   - Each vehicle rides the rails as the simulator moved it, carrying its lot (a pod of 25 wafers) between the two
     hoists.
   - Lots waiting at a tool group show as its queue, as today.
4. **Wafers at a tool.** Zoomed in, a tool working on a lot shows its 25 wafers, filled one by one from the step's
   start to its end. The order and pace inside the step are drawn; the start and end are the run's.
5. **The lenses on the building.**
   - Waiting heat glows each group's tools by the lots waiting.
   - Prototype lots are drawn pink on the rails and in the queues.
   - Flows replays one wafer's route along the rails it rode.
   - The Rails lens is retired: Live is the rails now.
6. **Shops that do not fit the building keep the old floor.** An arm from the ask box with extra copies (`G@B`) is
   played on the earlier abstract floor, said so on the page.

## Tests (written before the code)

- `crates/fabweb/tests/fleet.rs`:
  - a run of the real shop gives flat fleet arrays of whole records, every hoist on a node of the track;
  - a shop without a fleet gives none.
- `web/tests/building.test.mjs`:
  - engine tools map to their drawn boxes by group and order;
  - vehicles at a moment come from the flat arrays, with the lot each carries;
  - wafers done in a step;
  - which shops fit the building;
  - the page loads both data files, draws the building in the Live view, and has no Rails lens;
  - the build writes both files.
