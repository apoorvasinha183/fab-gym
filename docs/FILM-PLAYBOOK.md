# Film playbook: from a story to a drawn film

The steps for making a hand-drawn (cel) film with Meta's models in the loop, as Sand to Chip was made, for any agent
or person picking it up. Each step says what to run, what to check, and where the founder decides. The details live in
`docs/DRAWN-FILM.md` (spec and checks D1 to D19, M1 to M7, V1 to V3) and `docs/ART-DIRECTION.md` (the look's rules).

**Standing rules:**
- Muse Image paints every picture and Muse Spark writes the music. We write the direction and the code.
- Every call is metered (`data/drawn/ledger.jsonl`) under a cap.
- Decisions are a quiz, recommendation first. A timed-out quiz means stop and wait.
- One heavy job at a time, niced.

## 1. Story, shots and voice

- **Write:** `film/drawn/shots.json` (each shot's time, place, action, Grain's form and the caption) and `film/drawn/voice.json` (narrator and character lines with times; `VOICE-SCRIPT.md` is the readable copy).
- **Make:** `python3 -m viz.drawn.reel boards` has Muse Image draw one rough board per shot; `python3 -m viz.drawn.reel reel` holds each board for its shot over the score.
- **Check:** the reel reads as a story with no picture beyond rough boards.
- **Founder:** watches the reel.

## 2. The score

- **Make:** `python3 -m viz.drawn.music spot`, then `compose`, then `render`:
  1. Muse Spark spots the film (the big moments).
  2. It writes each cue for the orchestra.
  3. `score.check` keeps every part in its range and every hit on a beat.
  4. MuseScore 4 engraves the score and plays it (`data/drawn/score.pdf`, `score.mp3`).
- **Check:** M1 to M7 pass.

## 3. Choose the look (before any final picture)

- **Make:**
  1. Write the candidate looks into `film/drawn/looks.json`: how backgrounds are painted, how cels are drawn, and the colour script's light for each scene.
  2. Run `python3 -m viz.drawn.artdir SHOT LOOK LOOK ...`. It paints one shot in each look, with Grain drawn from the same model sheet, beside the shot as it is now.
- **Show:** an illustrated page with:
  - the looks;
  - the colour script as colour strips;
  - the roll-out;
  - the animation options, with clips of today's motion and a live sketch of the same move with and without weight.

  Then quiz the founder.
- **Record:**
  - the chosen look as `chosen` in `looks.json`;
  - its style pictures in `film/drawn/looks/`;
  - the rules in `docs/ART-DIRECTION.md`;
  - the decision in `DRAWN-FILM.md`'s Changes.
- **Trap:** Muse Spark's reading of a picture's scale proved unreliable. The look, the sizes and the staging are decided by people, not by a model reading frames.

## 4. Model sheets in the look

- **Make:** `python3 -m viz.drawn.scene sheets` redraws every first model sheet in the look, from the sheet and the look's example cel. The line-up is in `data/drawn/<look>/sheets.jpg`.
- **Check:** each form against the model standard in `ART-DIRECTION.md` (eyes, mouth shapes, hands, line, one shadow, no gloss). Redraw any that fail by deleting the file and running again.
- **Founder:** approves the line-up.

## 5. Direction, scene by scene (written by hand)

- **Write:** each scene in `film/drawn/scenes/<n>.json`:
  - backgrounds, with painted variants only for flicker (fire, plasma, glow);
  - every drawing: keys from a model sheet, `next` drawings made from the cycle's first drawing, and `between` drawings made from the two drawings either side;
  - each shot's exposure sheet: which drawing is on screen for how many frames, where the feet stand, the height in pixels and the camera.

  The direction is shared by every look.
- **Acting:** key moments (listed in `ART-DIRECTION.md`) get 6 to 12 drawings, with anticipation, squash and stretch, arcs and follow-through. Elsewhere, hold strong poses.
- **Sizes:** each shot's height is set against what is in its background (the crystal as tall as the person beside it). A close-up is cut to, never scaled into.
- **Traps:**
  - Muse Image's filter refuses some words (fear, grabbing, hugging, holding close); write poses plainly.
  - Two identical requests return one cached picture, so each variant's prompt carries its number.
  - A thing that hangs (a box on a rail) is pegged by its top, with `"anchor": "top"`.

## 6. The cohesion test (a gate)

- **Make:** `python3 -m viz.drawn.scene test 2-1 4-4 7-1` draws those scenes and renders only those shots. It writes `data/drawn/<look>/shots/cohesion-test.jpg`, the three middle frames side by side.
- **Check:** Grain and the rooms look drawn for the same film in paused frames, and Grain is recognisable in all three forms.
- **Founder:** passes or sends back. Nothing else is repainted until it passes.

## 7. Draw, review, render every scene

- **Make:**
  1. `python3 -m viz.drawn.scene draw N` paints every picture of the scene and writes `contact.jpg`.
  2. **Look at every contact sheet before rendering.** Redraw what is off-model, has a missing crowd, has a wrong face upside down, or carries tufts that are not on the sheet. Reword what was refused.
  3. `python3 -m viz.drawn.scene render N`.
  4. Take a middle frame of every shot and check, for each one:
     - feet on the floor;
     - size against the room;
     - titles clear of the characters, and glyphs the title font has (subscripts are drawn);
     - captions readable.
- **Automatic holds:**
  - A painted variant that repaints the light or framing too much (mean difference over 22 of 255) is held still.
  - `render` prints each shot's gaps in its exposure sheet and any sudden jumps.
- **Founder:** sees each finished scene.

## 8. The cut

- **Make:** `python3 -m viz.drawn.scene cut` joins every shot with the score into `data/drawn/<look>/sand-to-chip.mp4`. `python3 -m viz.drawn.timeline` writes the editor's timeline (Kdenlive's MLT) and the voice lines as subtitles.
- **Voices:** recordings are laid onto the timeline's Voices track at their subtitles.

## 9. Second opinion

- **Make:** `python3 -m viz.drawn.pack` builds `~/Sand to Chip/Second opinion (<look>)/`, which holds:
  - the film;
  - the storyboard against the finished frames (PDF);
  - the model sheets and every contact sheet;
  - the score, the voice script and the timeline.
- **Write by hand:** a README covering how it was made, who did what, the cost, the known weak spots and the questions for the reviewer.
- **Then:** zip it for sending. A review that changes the look goes back to step 3.

## Costs so far (Sand to Chip, at Meta's published prices)

| Item | Cost |
|---|---|
| Muse Image | $0.01 a picture |
| Muse Spark | a few cents for the whole film |
| The first cut, comic look (274 pictures, tests included) | $2.77 |
| Repainting in a new look | about $3 |
| Key-moment acting | about $1.50 more |
