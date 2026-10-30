# The floor in the editor's look

Written 31 Oct 2026, before the code. The founder: "I want the floor to have the same icons and look as the editor".
Chosen by quiz: every tool becomes an editor-style raised box with its area's colour on top and a small state light;
each of the floor's tool groups gets the editor's icon, label, mood badge and row of lots waiting, and the character
card on hover; labels and badges show from the first zoom step, so the whole-fab view stays readable. The moods are the
editor's ten, from the same Rust code: the browser build exports them for its last run. On the SMT2020 model, a
published model of a fab; never a real fab.

## Pieces

- `web/look.js` (`window.FabLook`): the icons, area colours and names, the ten moods with their badges, `areaOf`,
  `label` and `groupMood`, shared by the editor and the floor. Neither page keeps its own icon table.
- `fabsim::moods::frames_json(shop, run, until, every)`: the moods frames `fabsim moods` writes, now in the library;
  the command line's output is unchanged.
- `fg_moods(every)` in the browser build: the same frames for its last run, read like `fg_run`'s summary.
- The floor (`web/app.js`): tools drawn as the editor's boxes; per group, at its centre, the icon, label, mood badge
  and pods; the hover card shows the group's cast art in its mood with the counts the tip shows today; the legend
  lists the moods.

## Tests (written before the code)

`crates/fabweb/tests/moods.rs` (the library's frames are the moods at each frame; the browser export equals them for
the same run; no moods before a run), `web/tests/look.test.mjs` (every area's icon, colour, names and cast art; the ten
moods in the simulator's order; every SMT2020 area mapped; labels; the group mood equals the editor's; both pages load
the shared look; the floor asks the browser build for moods; the command line's moods keep their shape).

## Changes

- 31 Oct, while building: the group-mood test expected "hurt" for group B in its second frame, whose tools are "work"
  and "physio"; the tie goes to "physio", and "hurt" is group A's. The test now checks both.
