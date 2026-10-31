# Build after review

Written 31 October 2026, before the tests and the code. Argon reviewed Build; plan page ("Build Layout Plan", private); the founder: "lgtm" (all eight, in
order). Names on the machine tiles show once a tile is large enough to hold them (my call, reversible). On a teaching
fab of our own and the SMT2020 testbed; not a real fab.

Measured before: at 1,440 x 1,000 (a 913-pixel window) the page is 1,047 pixels tall, so the time slider is below the
fold; the map's canvas fills to the window's bottom, so anything under it falls off.

## What changes

1. **Stars that say whose they are.** A tab shows the best stars kept in this browser as "best ★★☆", filled and hollow;
   a challenge never met shows none.
2. **Layout, not "Checks".** The card is called Layout; its all-clear reads "Complete and connected: every machine is on
   the track, and wafers can get from the way in to every machine and out again", its badge "complete". It never says
   "Looks good". The run's own trouble stays on the advice line.
3. **One playback bar, one clock.** Play, speed, the clock, the time slider, the run's number and New run sit in one
   bar under the map; the slider's own time label goes. The toolbar above keeps the editing tools (undo, redo, the photo,
   Jams, Run again, the template). Moving the slider moves the clock.
4. **Names on the machines.** A machine tile draws its area's short name (from the cast's names: Litho, Litho Met, Dry
   etch, Wet etch, Diffusion, Dielectric, Thin film, TF Met, Implant, CMP, Defect) and storage, wafers in and wafers out
   theirs, when the tile is at least 40 pixels across.
5. **Keys that look like keys.** A tool's key (V, B, E and the hotbar's 4 to 9) is a keycap, and the button's title says
   which key picks it.
6. **The whole editor in one window.** The score cards become one compact row of figures, each keeping its change since
   the last run; the note at the foot moves behind an "About the sim" disclosure; the map's height leaves room for the
   playback bar and the status line. At 1,440 x 900 and 1,280 x 800 the page does not scroll.
7. **Rush hour says what to do.** Its goal ends "Hint: click the broken track and set When it stops to Cars go around
   it; the bay's own loop carries them."
8. **Build from a photo.** The sketch button reads "Build from a photo", with a picture icon; New run's title says it
   plays another random run of the same layout, since edits rerun on their own.

## Tests (written before the code)

`web/tests/buildreview.test.mjs` (headless Chrome, a helper of its own; nothing is spent):
- **BR1** with best stars 2 on Rush hour kept in the browser, its tab reads best with two filled and one hollow star; a
  tab never met shows no stars.
- **BR2** the card's title is Layout, its badge complete, its all-clear says complete and connected and never Looks good.
- **BR3** one clock: no slider label; play, speed, the clock, the slider, the run's number and New run are inside one
  bar under the map; moving the slider changes the clock.
- **BR4** every machine, storage, wafers-in and wafers-out tile on Rush hour's map draws its name.
- **BR5** every key on the palette is a keycap (a bordered box) and its button's title names the key.
- **BR6** at 1,440 x 900 and 1,280 x 800 the page does not scroll and the playback bar is in view; after an edit each
  score figure shows its change since the last run.
- **BR7** Rush hour's goal names the click and the setting.
- **BR8** the sketch button reads Build from a photo with an icon; New run's title says another random run.
- `web/tests/editortop.test.mjs` **D3** (no text on the map) changes with item 4: the tiles' names are allowed, nothing
  else. **D8** (a map of at least 360 pixels in a short window) stands: below 360 the page scrolls.

## Changes

- 31 Oct, while writing the code:
  - **The map's height.** The canvas filled to the window's bottom, so the playback bar fell off. A first fix allowed a
    fixed margin and missed the page's padding (33 px over at 1,280 x 800). A second measured everything below the map
    in the page, which counts the side column too and fed back on itself, and its new variable shadowed the map's
    "resize only on an 8 px change" memory, so every redraw threw and Build's sketch and Race the AI broke (caught by their
    tests). The map now measures only what sits under it in its own column plus the page's fixed padding, and fits the
    window when that leaves it 360 px or more; in a shorter window it keeps the old 430 px and the page scrolls (D8).
  - **Names on the tiles.** Drawn on top of the icons they crowded them, and a trouble badge clipped some ("Wet e"). A
    named tile keeps its name left-aligned along its top edge, short of the badge, with its icon a little lower and
    smaller; a tall, narrow tile (wafers in and out) takes its name sideways. At 1,280 x 800 the tiles are about 35 px, so
    the names show from 1,440 x 900 up or once zoomed in.
- 31 Oct, results: BR1 to BR8 pass, and the page suite (229 tests, the paused floor coach's three left out) passes run one
  file at a time; at 1,440 x 900 and 1,280 x 800 Build does not scroll.
- 31 Oct, the founder: "still doesn't fit the page". BR6 had checked 1,440 x 900, the screen; the page a laptop's
  browser gets is about 760 to 790 px tall, where Build ran 76 to 146 px over (measured). BR6 now checks 1,440 x 760 and
  1,280 x 720 as well, and the space above and below the map shrinks: the advice line joins the toolbar's row, and the
  status line becomes an overlay inside the map.
  The map fits the window when that leaves it 330 px or more (it was 360): 1,280 x 720 leaves about 350.
