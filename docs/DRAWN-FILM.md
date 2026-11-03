# Sand to Chip, drawn

Written 3 Nov 2026, before the code. Tests in `viz/tests/test_drawn_film.py` are committed with this file. Plan page
(private). The story, science and soundtrack are the current
film's (`docs/CHIP-FILM.md`, 13 scenes, 2:44); the steps before and after the fab are general knowledge and say so;
the fab's part runs from the SMT2020 testbed. No real fab, company or product is shown.

## Decided (3 Nov, by quiz, all on the recommendation)

- **Look:** Fab Gym's comic house style (`docs/img/fabgym-hero.jpg`): bold even ink, flat cel colour with one shade.
- **Who draws what:** Meta's models paint the plates and every pose, cut the cels, direct and check; our own
  open-source code lays out, inks, colour-locks, draws the effects and diagrams, and moves the camera.
- **Hero:** Grain, a grain of sand that keeps its face through 11 forms and becomes Fab Gym's wafer coach in the fab;
  Lou Latency has a cameo at the fab door.
- **Length and spend:** the full 2:44 on twos (12 drawings a second, ones for fast action) on the existing soundtrack;
  Meta credits capped at **$25** (estimate about $12).

## How a frame is made

Each frame is a stack of levels, back to front: sky, plate, props, characters, effects, foreground. A level shows one
drawing and holds it until the exposure sheet changes it. The camera moves across the stack; a level's depth sets
how far it slides (multiplane). A rigid thing that only travels is one drawing slid along a path. Every unique drawing
is rendered once and cached; frames are stacked in memory and streamed to ffmpeg, never written as files.

## Who does what

| Step | Who | Endpoint |
| --- | --- | --- |
| Shot list, prompts, first exposure sheets | Muse Spark (`muse-spark-1.3-contributor`) | `https://api.meta.ai/v1/chat/completions` |
| Word times of the soundtrack | Muse Voice Transcribe (`muse-voice-transcribe-1.0`) | `/v1/audio/transcriptions` |
| Layouts (plain lines, accurate to the process; the fab traced from our own 3D models) | our code, Blender 5.2.3 | local |
| Plates, model sheets, each pose (edited from the sheet) | Muse Image (`muse-image-1.0`, $0.01 a picture) | `/v1/images/generations`, `/v1/images/edits` |
| Cels cut from their backdrop; moving pieces lifted from plates | SAM 3.1 (`sam-3.1`, $2.50 per 1,000 images) | `/v1/responses` |
| Ink at one weight, colour lock to the scene palette, effects cycles, diagrams | our code (numpy, Pillow, rsvg) | local |
| On-model and storyboard checks of every plate and pose | Muse Spark | `/v1/chat/completions` |
| Stacking, camera, captions, mix, encode | our code, ffmpeg | local |

Every Meta call goes through one client with a spend meter: each call's cost is written to a ledger, a call that
would pass the cap is refused, and a repeated request (same model, inputs and prompt) is answered from the cache at $0.

## The exposure sheet

One JSON file per shot, `film/drawn/sheets/<scene>-<shot>.json`, committed:

```json
{"shot": "2-2", "frames": 288, "fps": 24, "palette": "smelt",
 "levels": [
   {"name": "plate", "depth": 1.0, "cels": [["smelt_furnace", 288]]},
   {"name": "glow", "depth": 0.9, "cycle": ["glow_1", "glow_2", "glow_3", "glow_4", "glow_5", "glow_6"], "on": 2},
   {"name": "grain", "depth": 0.6, "cels": [["G_lookup_A", 4], ["G_lookup_B", 4], ["G_gasp_A", 4]], "at": [612, 540]},
   {"name": "thief", "depth": 0.6, "cels": [["C_enter_1", 2], ["C_enter_2", 2]], "path": [[0, 1500, 520], [24, 900, 520]]}],
 "camera": [[0, {"x": 0, "y": 0, "zoom": 1.0}], [288, {"x": 0, "y": 0, "zoom": 1.22}]],
 "cuts": [], "captions": [{"from": 0.4, "to": 5.8, "text": "Heat it with carbon, hotter than lava..."}]}
```

`cels` lists [drawing, frames held]; `cycle` repeats its drawings, each held `on` frames; `path` keys a slide
(frame, x, y), eased between keys; `depth` 1.0 is the farthest level, which slides a third as far as the camera moves, and
0 the nearest, which slides the whole way.

## Keeping poses registered

The painful part of drawn animation is keeping one character steady across drawings made one at a time; an image
model makes it worse, since it puts the character at a slightly different place, size and angle in every picture. So
every pose is pegged, as animators peg drawings on a bar:

- **One canvas, one ground line.** Each pose is edited from its form's model sheet on the same canvas, centred, with
  the same ground line, and the prompt says so.
- **Anchors measured, not guessed.** From each cut-out, our code measures the contact point (the middle of the lowest
  painted row: where it stands or rests), the face point (where its eyes go) and the body height. They are kept in the
  pose library, `film/drawn/poses.json`, with the pose's form, view, action and source picture.
- **Placed by anchor.** A sheet says where the contact point goes; the compositor puts the pose's contact point
  there, never its corner, so swapping poses does not make the character jump.
- **Size held.** Poses of one form are scaled to the form's height; only a pose marked squash or stretch may differ.
- **Planted contacts do not slide.** A pose marked planted keeps its contact point still on the plate while it
  shows; travel happens on poses that step, hop or slide.
- **Faces drawn by us.** Grain's body poses come from Muse Image without a face; its eyes, blinks and mouth shapes
  are our own drawings on their own level, put at each pose's face point. The face never drifts, and lip sync and
  blinks cost no pictures.
- **Line-ups.** Every form's poses are shown side by side on their anchors, so a drifted pose shows at a glance.
- **Tracked after.** Each rendered shot is checked by following the character's painted area frame to frame; its
  path must be smooth wherever the sheet holds or eases it (SAM 3.1's video tracking can do the same at $0.20 per
  1,000 frames).

## The score and the voice

Decided 3 Nov by quiz: Meta writes an orchestral score that **MuseScore Studio 4.7.5** (GPL-3.0, open source) plays
and prints; a **full symphony orchestra**; the music **catches the big moments** (two to four hits a scene, each on
a beat); the voice-over is **a narrator plus a few lines from Grain and Lou**, voiced by people the founder brings.

- **Spotting** (Muse Spark): `film/drawn/score/spotting.json`, the cues, each with its start and end on the film,
  mood, key, meter, instruments and hit points (seconds on the film).
- **Tempo** (our code): each cue's tempo is chosen, between 60 and 160 beats a minute, so its hit points fall on
  beats, within one frame.
- **Composing** (Muse Spark): `film/drawn/score/<cue>.json`, every part bar by bar, notes as pitch and length in
  beats (`["D5", 1.5]`, `["r", 0.5]` a rest, `["C4+E4+G4", 2]` a chord).
- **Checks** (our code): every part adds up to the cue's bars; notes inside each instrument's range; the cue lasts
  its length. A failed check goes back to Spark with the reason; Spark then reads the checked score and revises.
- **Sheet and sound** (our code, MuseScore): each cue to MusicXML, the whole score as a PDF and each cue as audio from
  MuseScore's command line; the cues laid on the film and lowered under the voice.
- **Voice-over** (Muse Spark): `film/drawn/voice.json`, one entry per line: shot, who (narrator, Grain, Lou), words,
  start and end, an acting note. The founder brings the voices; our code places each take on its shot, checks its
  length and moves the speaker's mouth to it.

## Checks

- **D1** Every frame of every sheet resolves to a drawing that exists, on every level.
- **D2** A drawing is rendered once however many frames it is held for (the cache holds the unique drawings only).
- **D3** A level without its own timing changes at most every second frame (on twos).
- **D4** Multiplane: for a camera move, a nearer level slides further on screen than a farther one.
- **D5** No pop: two frames in a row differ by more than a set share of pixels only where a cut is marked.
- **D6** The same sheet renders the same frames, checked by hash.
- **D7** Rendering writes no frame files: only the video comes out.
- **D8** After inking, every painted pixel's colour is within a set distance of the scene's palette.
- **D9** The Meta client refuses a call that would pass the cap, writes each call to the ledger, and serves a repeat
  from its cache at $0.
- **D10** Captions land within one frame of the word times from the transcript.
- **D11** Every caption's words appear in `docs/CHIP-FILM.md`.
- **D12** The end card names each Meta model used and the CC0 music (The Budding of Consciousness by Yoiyami, New
  Sunrise by nene).
- **D13** Every pose's anchors are measured from its cut-out: the contact point is the middle of its lowest painted row,
  the height is its painted height.
- **D14** Swapping poses at one place keeps the contact point within 1 pixel on screen, and poses of one form are
  scaled to the same height.
- **D15** A sheet that moves a planted pose is reported (its frames named).
- **D16** The face level puts the eyes at the pose's face point, within 2 pixels; blinks and mouth shapes come from a
  fixed set.
- **M1** Every hit point lands within one frame of a beat at its cue's tempo, and every tempo is 60 to 160.
- **M2** Every part of a cue adds up to the cue's bars, and the cue lasts its length within half a beat.
- **M3** Every note is inside its instrument's range.
- **M4** Each cue becomes valid MusicXML: one part per instrument, named, every measure adding up to its meter.
- **M5** The orchestra is a full symphony: strings, woodwinds, brass, percussion and harp each have a part.
- **V1** Every voice line sits inside its shot; the narrator speaks at most 2.8 words a second, Grain and Lou 3.2.
- **V2** Every number the narrator says is in `docs/CHIP-FILM.md`.
- **V3** Grain has at most 8 lines of at most 8 words each; Lou has 1 or 2.
- **D17** In a rendered shot, the character's painted area moves smoothly: no frame-to-frame jump of its centre over
  a set size where the sheet does not cut, step or slide it.

## In order

1. This spec and its tests.
2. Story reel: rough boards for about 40 shots, timed to the soundtrack; the founder signs off.
3. Model sheets (Grain in 11 forms, Lou, the oxygen twins, the carbon thieves, the specks, the sibling dies) and the
   colour script; the founder signs off.
4. Pilot: Smelt finished end to end; the founder signs off the look and the motion, and sees the measured spend.
5. The other 12 scenes in story order, each checked.
6. Final cut: captions, mix, end card; `data/film/out/sand-to-chip-drawn.mp4` and the cinema's OGV.

## Limits

An image model drifts between pictures: poses are edited from one sheet, inked and colour-locked by our code and
checked by Muse Spark, and some will be redrawn. Smooth in-betweens are where image models turn to mush, so this is
limited animation: strong poses, holds, slides and smear drawings for fast moves.

## Changes

- 3 Nov, during the build: the sentence on `depth` said the far plate moves with the camera; it slides least (a third
  of the camera's move at depth 1, all of it at depth 0). D5's pop is a spike: over a quarter of the pixels change by
  more than 8 levels, and over three times the change of the frames around it, so a steady pan over detailed paint
  is not a pop. Tests unchanged.
- 3 Nov: D17's test placed the unpegged drawing's corner where the pegged one's contact goes, off the bottom of the
  frame, so nothing was tracked; the unpegged run now keeps its corner inside the frame. The check is unchanged.
- 3 Nov: Muse Voice Transcribe is listed in `/v1/models` for our key but every request tried answers 404
  (`/audio/transcriptions`, `/audio/transcribe`, `/speech/transcriptions`) or `model_not_found` (chat, responses).
  Until a working request is found, the story reel is timed by the script's scene times and Muse Spark's split of each
  scene's narration across its shots; D10 waits for word times. The game's spoken questions use the same call.
- 3 Nov: Muse Spark wrote the shot list (`film/drawn/shots.json`): 38 shots, back to back from 0 to 164 s, every
  caption the script's own words ($0.0017).
- 3 Nov: the score tests' made-up cue added up to 12 bars for a 6-bar cue, and one made-up hit (26.25 s) fell on no beat
  between 60 and 160 a minute; both corrected before the checks were changed.
