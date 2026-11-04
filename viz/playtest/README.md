# Playtest

For a bounded camera regression check, replay the guide's real route in fixed 50 ms steps:

```sh
godot --headless --path viz/fab3d --script res://playtest/tour_camera_check.gd -- --playability-check --tour-camera-check /tmp/tour-camera.json
```

This checks all 29 stops, sight lines to the centre and both sides of Lou's face, clearance from his model, and a maximum
25-degree camera error toward Lou at sampled walking frames. Lou's body must stay clear of solid geometry and the
tour must finish without getting stuck. Omit `--headless` and add `--stills /tmp/tour-stills`
to render each stop. It checks framing and direction; use the real-time playtest below for frame timing.

Plays the whole Fab Gym 3D demo the way a first-time visitor would, with scripted key presses, and turns what it saw
into a list of faults. It finds faults; it fixes nothing.

```sh
viz/playtest/run.sh OUT_DIR                  # the whole loop, drone opening included (about 25 minutes, window on top)
viz/playtest/run.sh OUT_DIR --no-intro --cinema   # the cinema part only (about 2.5 minutes)
python3 viz/playtest/analyse.py OUT_DIR      # OUT_DIR/faults.json and OUT_DIR/summary.md
```

The game scene runs inside `viz/fab3d/playtest/playtest.tscn` (`res://playtest/`), which loads `main.tscn` and logs:

- every frame's time (`frames.csv`), with the frames held by saving a still left out of the timing;
- every 0.2 s (`log.jsonl`): the camera, the floor under it and whether it is inside something solid; Lou's position,
  walk, clip and stop; whether Lou is in frame or hidden; whether Lou's body is inside something; what the text window,
  prompt, card and ask windows show and where they sit; the film; the doors near Lou and the camera;
- events: each stop reached, each line said, each prompt, each scripted action;
- stills at 960 x 540 every 3 s and after every stop and action (`shots/`).

The scripted visitor: watches the drone opening and the tour; at the third fab stop presses Space twice; at
lithography clicks a tool, closes the card with Esc, asks two typed questions and cycles the speed; at the cinema walks
to a free seat, sits (E), plays the film (Enter), pauses and resumes (Space), returns to the hall (Esc), stands (E),
chooses Walk alone, walks towards the screen and out by the rear exit, flies (F, E, W), lands and asks to be shown the
polishers.

`analyse.py` checks: frame time against the 16.7 ms bar and hitches over 100 ms; the camera inside something, under a
floor, or jumping; Lou off screen or hidden while talking, losing sight of him on the move, Lou inside something,
stuck, or his feet sliding; doors shut in someone's way; lines overflowing their window or gone before they can be read
(17 characters a second, assumed); windows overlapping; the key prompt flickering; stretches with nothing happening;
and each scripted action against what it should do. The thresholds are in `analyse.py`.

Needs a visible window (macOS does not draw a hidden one): it runs with the window on top and the display kept awake.
Run one at a time, nothing else heavy alongside, or the timing means nothing.
