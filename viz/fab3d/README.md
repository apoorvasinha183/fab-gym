# Fab Gym 3D

A walkable 3D wafer fab in Godot 4.7 (Forward+). Lou Latency, the robot CEO, meets you in the parking lot and takes
you through the visitors' entrance, the lift, gowning and the air shower. He then walks both phases of the fab, crosses
the bridge, and ends at the campus cinema, where you pick a seat and watch the film "From sand to chip". After that you
walk anywhere on your own. Tools, vehicles and queues come live from the simulator running in the helper.

From the SMT2020 testbed; a gigafab-style layout of our own design; not a real fab. The full spec, with dated
changes, is `docs/FAB-3D.md`.

## Run it

From the repo root (`~/evalzero_work/fab-gym`):

```sh
# 1. the helper (the live simulator the scene reads); keep it running
.venv/bin/python -m agent.helper --port 8766

# 2. copy what the scene reads into viz/fab3d/data/ (never committed); rerun after any model or data change
python3 viz/fab3d/prep.py

# 3. play
~/Applications/Godot.app/Contents/MacOS/Godot --path viz/fab3d
```

Or open `viz/fab3d/project.godot` in the Godot editor and press Play (the game opens in its own window).

Useful starts (after `--`):

| Flag | What it does |
| --- | --- |
| `--no-intro` | skip the drone flight round the campus |
| `--cinema` | start the tour at the cinema door |
| `--no-ui` | no screen windows (clean stills) |
| `--check FILE` | headless self-check; writes a JSON report (the tests read it) |
| `--perf FILE` | timed tour for the 60 fps bar (F8) |
| `--shots DIR --shot-times 6,14` | stills at those seconds |
| `--clearance FILE` | the camera's lowest height over the cinema floor |
| `--film` | the recorded tour; seats the viewer, plays the whole movie, then exits |
| `--sweep`, `--corridor` | fixed camera moves for measuring shimmer |

Recording a video: `--write-movie OUT.avi --fixed-fps 30` before the `--`, with `--always-on-top` (macOS does not draw
a hidden window).

## Controls

- **Space** or click the text window: next line
- **W A S D** walk, **Shift** hurry, **F** fly (**E** up, **Q** down), hold the **right mouse button** to look
- **Esc** closes a question or tool card and releases mouse look. Typing a question suspends walking and flight controls.
- Click a tool for its card. Use **Ask Lou** to type or speak a question. **Walk alone** ends the tour.
- Cinema: walk up to a free seat and press **E** to sit. Seated, press **Enter** to play the film full screen, **Esc**
  to return to the hall, **Space** to pause, and **E** to stand up.

## How it fits together

| Path | What |
| --- | --- |
| `main.gd`, `main.tscn` | wiring: the tour's stops, the guide's lines, the walkable map, the headless check |
| `campus.gd` | the fab streamed by 24 m cells around the viewer: tools, rail, vehicles, stockers |
| `player.gd` | the visitor and camera: follow rules, the lift camera, floor heights, sliding along solid things, sitting |
| `guide/` | Lou: walking (eased, feet matched to the clip), talking, the air-shower bump, paths round obstacles |
| `solid.gd` | what is solid: collision from the drawn meshes, boxes for tools and stockers |
| `entrance/`, `exterior/`, `drone/`, `cinema/` | the way in, the outside and logo, the opening flight, the cinema |
| `ui/` | the JRPG-style windows, pixel font (Kenney, CC0), portrait, prompts |
| `live.gd` | talks to the helper at 127.0.0.1:8766 |
| `looks.gd` | CC0 Poly Haven materials (triplanar), from `~/fab-gym-downloads/polyhaven` |
| `prep.py` | builds `data/campus.json` and copies models, textures, film and the cinema's floor map |

Models are made in Blender (5.2.3, headless) by scripts in `viz/blender/` and land in `data/fab3d/models/`:
`tools/*.py` for each tool kind, `buildings/merge_bim.py` (the fab building), `entrance.py`, `exterior.py` and
`cinema.py`. The cinema is built from a rules-generated plan: `viz/cinema/plan.py` writes `data/cinema/plan.json`
(seats, aisles, doors, checked against the building code register in `viz/permit/codes/us-2024.json`), and
`cinema.py` turns it into `cinema.glb` plus `data/cinema/built.json` (the floor-height map, doors and posters). The
cinema is built on the Mac mini:

```sh
scp viz/blender/buildings/cinema.py data/cinema/plan.json sdas@Souravs-Mac-mini.local:fab-gym-cinema/
ssh sdas@Souravs-Mac-mini.local 'cd ~/fab-gym-cinema && ~/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P cinema.py -- --plan plan.json --out cinema.glb'
scp sdas@Souravs-Mac-mini.local:fab-gym-cinema/{cinema.glb,built.json} .   # then: cinema.glb -> data/fab3d/models/, built.json -> data/cinema/
```

After new models: run `prep.py`, then `Godot --headless --path viz/fab3d --import` so Godot picks them up.

## Nothing walks through anything

Walls, door frames, rails, benches, cars, trees, tools and stockers are solid. You slide along them, and the camera
stays on your side of them. Lou walks round them: when the game starts it bakes a walkable map from the solid
geometry (about 1 to 3 seconds), and any leg of his tour whose straight line hits something becomes the map's path. A
waypoint that falls inside something solid moves to the nearest spot he can reach. The headless check sweeps his body
along all 48 legs of the tour and fails on any contact. The air-shower bump is the one planned contact.

## Tests

```sh
python3 viz/fab3d/prep.py
~/Applications/Godot.app/Contents/MacOS/Godot --headless --audio-driver Dummy --path viz/fab3d -- --check $PWD/data/fab3d/check.json
python3 -m unittest viz.tests.test_fab3d viz.tests.test_cinema agent.tests.test_fab3d
```

The Godot tests read `data/fab3d/check.json`, or run Godot themselves when `GODOT` names it. There are now 45 checks, including entrance floor levels, seat approach/standing and typing focus.
The performance check reads `data/fab3d/perf.json`; it must be refreshed separately from the headless checks.

## Known gaps

- The fresh 1080p entrance measurement misses the 60 fps bar: median 18.06 ms, p99 26.19 ms, 99.97% drawn (3 Nov).
- The cinema's exit stair does not meet its rear exit door (off the tour).
- The browser export is not built yet.

## Rules for this repo

No trademarks in code, docs, tests or commit messages. Ask the founder before any
download or anything public. One heavy job at a time, niced. Keep the helper on 8766 running.

## Polish pass, 3 November

The follow camera sweeps a small volume around the lens to catch wall corners, with frame-independent position easing.
Entrance ground and upper levels are distinguished; the lift floor follows the car. Camera trails reset at tour teleports.
Cinema posters fit their frames, lobby surfaces have restrained material detail, and grazing-angle texture filtering is increased.
Standing returns to the approach in front of the seat; seats cannot be selected from outside the hall or another level.
Full-screen film playback locks world controls. Cinema-only starts show the correct two-stop total.

Movie mode waits until the viewer is seated, holds the hall view for two seconds, then starts the complete film in full screen.
It exits two seconds after the film finishes, instead of cutting it off after 14 seconds. During full-screen playback the
hidden 3D world is not drawn. Space pauses/resumes with a visible paused hint; E stands up, and Esc returns to the hall.
The pointer hides while the movie is full screen and returns afterwards. A missing film keeps the visitor in the hall.

Validation: 44 functional tests pass; F8 fails against the fresh performance report. Disabling ambient occlusion improved the
entrance sample to median 16.67 ms / p99 23.61 ms, still short of F8, so the default retains its existing lighting.
