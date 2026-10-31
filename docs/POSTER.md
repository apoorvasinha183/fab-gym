# The three-star poster

Written 31 October 2026, before the tests and the code. Step 2 of "Five Meta features for the 2D gym"; the founder: "go on with the poster". Cap $1 (by quiz).
On a teaching fab of our own; not a real fab.

## What changes

1. **A button at three stars.** When a run earns three stars, the Challenge met card offers "Make a poster". It never
   shows below three stars, and not for the AI's games (their stars are not the player's).
2. **Muse Image redraws your map.** The page sends a picture of the map; the helper asks Muse Image (`muse-image-1.0`,
   `/v1/images/edits`) to redraw it as a bright cartoon poster, keeping the layout's shapes and places, with the
   challenge's name at the top and the wafers a day and three stars at the bottom. The words on the poster are built
   by the helper from the run's numbers; the page cannot add other text.
3. **Saved on your Mac.** The poster shows in the card with a Download button, and is saved under
   `data/ask/posters/` (ignored by git). The card says which model made it and what it cost.
4. **Counted and capped.** $0.01 a poster (Meta's price sheet), on the poster's own $1 meter under the helper's $5 total.
   With `--stand-in DIR`, the helper answers with `DIR/poster.png` and spends nothing.

## Tests (written before the code)

`agent/tests/test_poster.py` (Python, no model called):
- **PO1** the prompt carries the challenge's name, the wafers a day and the stars; a name longer than 60 characters is
  cut; wafers that are not a whole number, or stars outside 0 to 3, are refused.
- **PO2** only a PNG data URL under 8 MB is taken as the map's picture.
- **PO3** with a stand-in, the poster is the recorded picture, marked "stand-in", costing nothing, and saved.
- **PO4** live against a fake Meta endpoint: `/images/edits` is sent `muse-image-1.0` and the map's picture as the
  image; the reply's picture is saved and returned, and $0.01 is counted on the poster meter.
- **PO5** a poster meter at its $1 cap refuses and sends nothing; so does the helper's total.
- **PO8** a WebP reply is saved as `.webp` and handed back as `image/webp` (added after the first live poster; see
  Changes).

`web/tests/poster.test.mjs` (headless Chrome, a helper with a stand-in):
- **PO6** at one star the card has no poster button; at three stars it has one.
- **PO7** pressing it shows the poster in the card, with "stand-in", $0.00 and where it was saved, and a Download
  button.

## Changes
