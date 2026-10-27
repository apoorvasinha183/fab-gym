# Film script: Where the Time Goes

About 2 minutes 7 seconds, 1920×1080, 24 fps. Rendered in Blender; the same
scene is explorable in Godot. A gigafab-style layout of our own design on the
SMT2020 model; not a real fab.

**The story in one line.** Follow one lot for eight hours on the SMT2020 model
and find where its time goes: about 26 minutes moving, nearly three hours
waiting. That sets up Fab Gym's question: which lot should go next?

**Numbers.** Every number below is from today's run (optimised layout, seed
3000, simulated day 30). The layout is re-packed at true size before the
render, so each number is re-measured from that run and the lot is re-chosen
by the same rule: a back-end lot whose clip includes lithography, metrology,
etch and a wait of over an hour.

**Today's lot.** `wip.977.Init_Lot_3_954` (shown as "Lot 954"):

| step | group | moved | waited | on the tool |
|---|---|---|---|---|
| coat and develop | LithoTrack_FE_95 (Phase 1) | 4.4 min | 15.0 min | 50.7 min |
| exposure | Litho_BE_110 (Phase 2) | 4.4 | 13.9 | 71.1 |
| litho metrology | LithoMet_BE_18 | 4.6 | 0.0 | 18.4 |
| registration check | Litho_REG_BE_63 | 3.7 | 0.0 | 25.8 |
| dry etch | DE_BE_65 | 4.4 | 11.9 | 92.5 |
| wet etch | WE_BE_9 | 4.1 | 125.0 | 22.0 |
| **total** | | **25.6 min** | **2 h 46** | **4 h 41** |

Across all lots in the clip's hours: 50.4% of lot time waiting for a tool,
46.4% on tools or timed holds, 3.2% moving.

## Camera grammar

- Lenses: 24 mm outside, 35 mm wide inside, 50 mm tracking, 85 mm close-ups.
- Every move eases in and out. Acts join through a move (through the cut,
  through the ceiling); the only hard cuts are the three beats of shot 9.
- The camera never passes through a tool, a wall that is standing or a person.
- A caption holds at least 3 seconds, lower left. In Act 3 a clock and a step
  card sit upper right; the clock shows simulated time since the lot left wet
  etch, with the speed-up beside it (×1, ×26, ×400).
- A label appears only when it names something on screen and shrinks away
  when the camera comes close.
- The lighting (dawn to morning) is a look only; the simulation has no time of
  day.

## Act 1 · The place (0:00–0:22)

**Shot 1 (0:00–0:10). Establishing.** 24 mm. Starts 900 m south-east of the
campus at 350 m height; slow push in and descent to 450 m away, 160 m high,
drifting 10° round. Dawn behind the cooling towers, steam rising, cars arriving
in the lot, the hoist bridges' glass catching the light.
*Caption:* "A wafer fab campus of our own design, run on the SMT2020 model."

**Shot 2 (0:10–0:22). Round the campus.** 24 mm. Orbit north at 300 m past the
gas yard and office, revealing Phase 1, the bridge, Phase 2 and the empty pad.
Labels fade in as each passes: Phase 1, front end · overhead hoist bridge ·
Phase 2, back end · pad for Phase 3 · utility building · gas yard.
*Caption:* "1,043 tools in two buildings, joined by an overhead hoist."

## Act 2 · Inside (0:22–0:40)

**Shot 3 (0:22–0:32). The cut.** 35 mm. Crane down to Phase 2's west face,
60 m out. A section plane sweeps down through the building and the façade falls
away floor by floor: the air space (fan filter units lit), the cleanroom (bays,
tools, rails), the support floor (pumps, chillers, ducts). Slow push in.
*Captions, one per floor:* "Air space: fans push filtered air down." ·
"Cleanroom." · "Support floor: pumps, chillers, exhaust."

**Shot 4 (0:32–0:40). Through the cut.** 35 mm. Dolly through the cut onto
Phase 2's spine at 6 m, moving east under the rails as hoist cars pass
overhead; settle above the wet etch bay, where Lot 954 sits on a load port.
*Caption:* "Each lot is one carrier of wafers." (the wafer count once checked
in SMT2020's files)

## Act 3 · One lot (0:40–1:35)

**Shot 5 (0:40–0:50). Pick up.** 85 mm, 1.5 m from the load port, ×1. A hoist
car stops overhead, its gripper lowers, takes the carrier and lifts it. The
wet bench's status light behind. Clock and step card appear.
*Caption:* "Lot 954 leaves wet etch."

**Shot 6 (0:50–1:00). The ride.** 50 mm, tracking 4 m beside the car at rail
height, ×26. West along Phase 2's spine, through the bridge (the campus outside
the glass), into Phase 1 and down to the track bay; the carrier is set down.
*Caption:* "Across the bridge to Phase 1 for coat and develop. 4 minutes on
the hoist."

**Shot 7 (1:00–1:10). Yellow light.** 35 mm, rising to 8 m and pulling back,
×400. The lithography bay in yellow light, carriers at the track's load ports,
status lights changing.
*Caption:* "It waits 15 minutes, then spends 51 on the track."

**Shot 8 (1:10–1:18). Exposure.** 50 mm tracking, then 85 mm on the scanner's
long body, ×26 then ×400. Back across the bridge to a Phase 2 scanner.
*Caption:* "Back to Phase 2 for exposure: 14 minutes waiting, 71 on the
scanner."

**Shot 9 (1:18–1:24). Three beats.** 50 mm at load-port height, 2 s each, hard
cuts, ×400. Litho metrology, the registration check, dry etch. The step card
builds a list.
*Caption:* "Measured, checked, etched: 2 hours 17 minutes on three tools."

**Shot 10 (1:24–1:35). The queue.** 35 mm. The carrier is set down at wet
etch; the camera pulls back and rises to show the carriers waiting for the wet
benches. The clock spins, ×400.
*Caption:* "Then it waits. Two hours in the queue for wet etch."

## Act 4 · Where the time went (1:35–1:55)

**Shot 11 (1:35–1:44). Up through the ceiling.** 35 mm rising through the
filter grid to a top-down view at 120 m. The lot's path drawn across both
buildings. A bar fills: on tools 4 h 41 · waiting 2 h 46 · moving 26 min.
*Caption:* "Moving: 26 minutes. Waiting: almost three hours."

**Shot 12 (1:44–1:55). All lots.** Same view. Every waiting carrier glows at
its queue.
*Captions:* "Across the fab, half of lot time was spent waiting for a tool and
3% moving." · "Our layout cut hoist travel by 30%. Cycle time did not clearly
change."

## Act 5 · The question (1:55–2:07)

**Shot 13 (1:55–2:01). Back out.** 24 mm. Pull up and out to the campus in
morning light, ending on Shot 1's angle.
*Caption:* "Which lot should go next? In Fab Gym, an agent proposes, the
simulator scores, a person signs."

**End card (2:01–2:07).** "Fab Gym. A gigafab-style layout of our own design on
the SMT2020 model. Not a real fab." Small: SMT2020 (Kopp, Hassoun, Kalir and
Mönch, 2020); the CC0 sources by name.

## Settled by the founder (27 Oct)

- The script is approved as written.
- The re-pack places each tool group in the phase that sends it most of its
  lots. `LithoTrack_FE_95` (78% of its lots from back-end groups) moves to
  Phase 2, so the re-chosen lot may not cross the bridge; shot 6 follows the
  lot's real ride, whichever building it is in.
- Captions now; a voice later, reading the same captions.
