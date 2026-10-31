# The editor's basics: undo, zoom and pan, a preview, a run that keeps playing

Written 31 October 2026, before the tests and the code. Decided by quiz the same day (`~/HACKATHON-README.md`), from the
review "The first five minutes": direction A, speed
first (done, `docs/FLOOR-SPEED.md`), then these. From the SMT2020 testbed and a teaching fab of our own; not a real fab.

## The problem

Builders arrive with the habits of factory-builder and transit-puzzle games in their hands. Today's editor (`web/editor.js`) has no undo, a
fixed view, no preview before placing, and stops the run whenever anything is edited (Build mode pauses; an edit marks
the run stale until "Run again" is pressed), although a rerun takes about 0.3 s.

## What changes

1. **Undo and redo.** ⌘Z or Ctrl+Z undoes; ⇧⌘Z, Ctrl+Shift+Z or Ctrl+Y redoes; two toolbar buttons do the same and are
   disabled when there is nothing to undo or redo. One gesture is one step: a whole track drag, a whole erase drag, a
   move, a placement, a count change. A new edit clears the redo list. Loading a challenge clears both.
2. **Zoom and pan.** Scroll (or pinch) zooms about the pointer: the floor point under it stays under it. Dragging
   empty floor with Select pans, as do the middle button and Space-drag with any tool, and W, A, S, D or the arrow
   keys. F fits the whole fab again. Zoom is limited to between a quarter and four times the fitted size.
3. **A preview before placing.** With a machine, wafers in or out, or storage in hand, the footprint under the pointer
   is drawn as a ghost: teal where it fits, red where it does not, with the reason in the status line. Nothing is
   placed until a click.
4. **A run that keeps playing.** Choosing a tool or editing no longer pauses the clock. The floor keeps playing the
   last run; about 0.6 s after the last edit, if the checks find no error, the editor reruns by itself and swaps the
   new run in at the same clock time, with the score cards showing the change against the last run. "Run again with my
   changes" stays for anyone who wants it.

The logic that can be tested without a browser lives in `web/editor-core.js`: `History`, `zoomAt`, `panBy`, `isFree`
and `ghost`. `window.FabEditorPage` (for page tests) gains read-only `view()`, `ghost()`, `rails()`, `runs()`,
`clock()`, `canUndo()`, `canRedo()` and `firstFree(w, h)`.

## Tests (written before the code), `web/tests/editorbasics.test.mjs`

In Node, on `editor-core.js`:
- **C1** history: undo returns the state before the last step and redo the one after; a new step clears redo; undo
  with nothing to undo returns nothing; at most 200 steps are kept.
- **C2** zoom about a point keeps that point fixed on screen, and stays between a quarter and four times; pan moves
  the view by exactly the drag.
- **C3** a free spot is free; a spot overlapping a machine or track, or off the floor, is not, with a reason; the
  ghost reports the footprint and whether it fits.

In headless Chrome with a helper of its own (skipped without Google Chrome):
- **B1** ⌃Z removes a placed storage block and ⌃⇧Z puts it back; a four-cell track drag is undone in one step; the
  undo button is disabled at load and enabled after an edit.
- **B2** a scroll over the map keeps the cell under the pointer within 2 px of where it was; dragging empty floor with
  Select moves the view by the drag (within 1 px); F gives back the fitted view.
- **B3** with storage in hand over a free spot, the ghost fits and nothing is placed until a click; over a machine it
  does not fit.
- **B4** during a challenge's run, an edit leaves the clock moving, a new run arrives by itself within 3 s, and the
  clock does not go back.

## Changes

- 31 Oct, while writing the code: `FabEditorPage.firstFree(w, h)` returns the first spot that is free and can be
  pointed at, every cell's middle picking that cell. Free on the floor alone was not enough: in B1 the storage block
  placed first is tall, and in the tilted view it covers the next free cells, so a click there picks the block, as it
  would for a person.
- 31 Oct, B2: the cell under the pointer is measured on the map itself. Measured on the page, it moved 4.2 px in one
  run because the panels above the map settle just after the first run and push the map down a few pixels; the zoom
  itself keeps the cell within 0.2 px. That small shift is a layout bug of its own, noted for the polish list.
- 31 Oct, results: C1 to C3 and B1 to B4 pass (twice in a row), and all 115 page tests. An erase drag is one undo step
  too. Space alone still plays and pauses; Space held while dragging pans instead.

