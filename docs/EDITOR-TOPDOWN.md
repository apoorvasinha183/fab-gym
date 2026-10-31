# The editor, top down

Written 31 October 2026, before the tests and the code. The founder the same day: "go completely top down instead of
2.5D", "the buttons are not properly engraved", "Factorio tiles but let us not write the text on top of it, it is
distracting"; from the options page (private), tiles B (icons
engraved into the tiles) and buttons B (raised keys). From the SMT2020 testbed and a teaching fab of our own; not a
real fab.

## What changes

1. **Straight down.** The map is drawn from above: tiles are squares on a visible grid, x across and y down. Nothing
   stands up, so nothing hides the floor behind it (in the tilted view, free floor behind tall machines could not be
   clicked).
2. **Factorio tiles.** A machine group is a flat tile in its area's colour with a darker rim and a lit top edge;
   storage, wafers in and wafers out are tiles of their own colours. Vehicles are flat tokens on the track.
3. **Engraved icons.** Each tile's icon is cut into it: drawn in a dark shade of the tile's colour, with a light line
   along its lower edge (`FabEditor.engrave(colour)` gives the two).
4. **No text on the map.** No name pills, no "×3", no "+N". A group's name, machines and line show in the hover card
   when it is pointed at. Lots waiting show as up to eight pods inside the tile's lower edge, a ninth in amber when
   there are more.
5. **Raised keys.** The toolbar's and the palette's buttons are keycaps: raised with a shadow under them, pressed down
   (sunk, inset shadow, lit) while held or while chosen.

Everything else (picking, the ghost, the box, paste, zoom and pan, the checks, the run) works as before.

## Tests (written before the code), `web/tests/editortop.test.mjs`

In Node:
- **D1** `engrave(colour)` gives a cut darker than the colour and a light line that is a see-through white.

In headless Chrome with a helper of its own (skipped without Google Chrome):
- **D2** the map is straight down: one tile to the right moves the screen point only across, one tile down only down,
  by the same distance.
- **D3** no text is drawn on the map while it plays, other than the one-line notice of a rerun.
- **D4** in challenge 1, a free 3 × 4 patch can now be pointed at (in the tilted view there was none).
- **D5** pointing at a machine tile shows its hover card with its name.
- **D6** the palette's buttons are raised (a shadow under them, none inset) and the chosen one is pressed (an inset
  shadow); the toolbar's play button is raised too.

## The map fits the window

Added 31 October 2026, before the code. The founder on the top-down map: "make the figure compact, it is too big"
(square tiles made it 643 px tall in a 913 px window, its bottom below the fold). The map is now sized to the smaller
of the column's width and the window's height below the map's top, never under 360 px tall, with the floor centred
across. Square tiles, picking, zoom and pan are unchanged.

- **D7** on a 1440 x 900 screen the map ends inside the window, the whole floor sits inside the map, and tiles stay
  square.
- **D8** in a 1440 x 640 window the map is still at least 360 px tall and the floor at least 300 px.

## Changes

- 31 Oct, while writing the code: a leftover rule dimmed every palette button but Select while the run played (from
  the Run and Build modes, cut in docs/SITE-CUTS.md); it went, which is likely part of what looked "not engraved".
  The old pods-under-a-label drawing went with the labels.
- 31 Oct, results: D1 to D6 pass, and all 139 page tests (the earlier editor tests click by tile and pass straight
  down too). The map is taller than before, since square tiles take more height than the tilted view; zoom and pan
  reach all of it.
- 31 Oct, fitting the window: sizing the map by the window's height made it depend on where the map starts, and the
  page moved under it after loading (the earlier "map shifts about 4 px after load"): the score cards appeared after
  the first run (+63 px), and the web font, loaded with `display=swap`, changed line heights twice (+3.5 and +5.5 px),
  so B2's "F fits again" failed. Fixed: the three score cards wait in place before the first run, the controls whose
  `font` shorthand reset their line height now have a fixed one (1.3), and the fit keeps its height until the room
  changes by 8 px or more (a resize recomputes it). Left: under half a pixel when the font arrives.
- 31 Oct, results: D1 to D8 pass, and all 51 tests in the seven files that open the editor. At 1440 x 900 the map is
  about 467 px tall, its bottom inside the window.
