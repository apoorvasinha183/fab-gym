# One question, all the way down to the building

The entry's narrative and the plan that makes it true. Written 29 October 2026 with the founder; every choice below
was made by quiz the same day (`~/HACKATHON-README.md`). On the SMT2020 model, a published research model of a wafer
fab; prices assumed; every drawing NOT FOR CONSTRUCTION. Agents propose, the simulator scores, a person signs.

## The story

**Logline.** A plain-English question becomes a scored decision. The decision becomes a layout, the layout becomes a
building drawn for one place's rules, and you can walk through the building.

The five steps are one decision seen ever closer to the real world. Each answers the next person's question about
the same change.

| Step | Who asks | What they see | Proof on screen | Meta's models |
| --- | --- | --- | --- | --- |
| 1. The numbers | The operations head: "Prototype orders double next quarter. Their own copies of the busiest tools, or first in line?" | The 2D floor: experiments run on 10 held-out seeds against today's rules; copies in the halls win (+$194k a day, 95% +$101k to +$288k); a person signs | Paired seeds, intervals, the price sheet, the critic's note, the signature | Muse Voice Transcribe hears the question; Muse Spark Open turns it into experiments; Muse Glimmer critiques the candidates |
| 2. The plan | The planner: "Where do the new tools go?" | The copies placed in the realistic layout; plan, section and site sheets redrawn | Travel metres before and after; the sheets | |
| 3. The building, for a place | The engineer: "Can this be built here?" | The BIM model rebuilt with the copies, checked against a hypothetical US jurisdiction adopting the 2024 IBC and IFC as published (hazard values from the Willamette Valley, Oregon); the bill of materials and the capital | The code analysis, the checks rerun, the bill of materials' difference; the `intl` profile refusing for lack of codes read | |
| 4. The walkthrough | The investor: "What does it feel like?" | A visitor walks from the car park to the clean floor; the lots overhead are the simulator's | The film, timed to the run | |
| 5. Your turn | The judge: "Let me look." | The Godot game: walk the same building freely, with a colleague who shows you around, and a movie hall | Tools in the states the simulator says | Muse Spark (Meta Model API) is the colleague's brain; Muse Voice Transcribe hears spoken questions |

**Close.** "An operating system for your full org." Then the truth card.

### The colleague and the movie hall (the founder's idea)

- A colleague walks beside you in the game. You ask in text or by voice; it answers in text. Ask it to show you
  something ("show me the polishing hall", "where are the new copies?") and it walks you there.
- Its brain is Muse Spark through the Meta Model API, with tools: go to a place, show a tool group, read the fab's
  live numbers, explain a stage, start the film. Spoken questions go through Muse Voice Transcribe. Until the key is
  in, a stand-in answers from a fixed set and says so on screen.
- A movie hall in the fab plays **Silicon Odyssey** (the sand-to-chip film, retitled, voiced), followed by a trailer,
  **Robot Construction Crew**: robot crews and people building the fab from the bill of materials, robots on the
  repetitive work, people supervising and signing, ending on the Chetnova card.

### The demo video (3 minutes)

Screen capture of the real page and game, the plans and the BIM as they are, and cuts from the Blender walkthrough;
about 35 s a step; voiced. Opening on the spoken question, closing on the colleague walking you into the movie hall.

## Deliverables, in order

1. **This plan.**
2. **The decision as a fab.** A signed answer becomes a variant: the candidate's changes (copies by group and area,
   policy, capital from the price sheet) and the changed shop; the realistic layout re-packed with the copies.
   Built 29 Oct: `fabsim variant` keeps today's US plan (1.6 m chases, cross aisles) block for block and puts one copy
   of each of TF_FE_103, Planar_FE_79 and LithoMet_BE_18 right after its original; $20.1M once on the central price
   sheet; 42 bays and the hall lengths unchanged; hoist travel +0.14% at the two-family flows
   (`results/layout-real-dd-copies/`).
3. **Plans, BIM and bill of materials for the variant**, through the same pipeline as today's fab, with a difference
   sheet (tools, floor area, travel, capital, code checks rerun).
   Built 29 Oct: the variant through the design-development and construction-document stages and the bill of
   materials (`data/layout-real-dd-copies/`), and `viz/variant/diff.py` writes the difference (sheet X-001, JSON, note
   in `results/layout-real-dd-copies/difference/`): 3 tools added, 18 moved along their wall, 0 of 279 and 0 of 292
   verdicts change (the P2 chase travel goes from 67.3 to 70.3 ft against 75), 12 bill of materials lines, 14 of 37 and
   18 of 73 sheets.
4. **The variant in the film and the game**: the game loads the variant building; the walkthrough gains a shot of the
   copies.
5. **The colleague**: the character, the chat panel, "show me" walking you there, places taken from the layout, the
   tool workflow, the stand-in until the key is in.
6. **The movie hall**: the room, the screen, Silicon Odyssey then the Robot Construction Crew trailer.
7. **Voice**: spoken questions through Muse Voice Transcribe (the page and the game); the film's narration.
8. **The critic**: Muse Glimmer on the Linux server reads each candidate and its scores and flags rules that game
   the metric or break a queue-time limit; its note sits on the card before the signature.
9. **Proof**: a Lean checker for scored runs, a tampered run rejected; a misbehaving rule stopped by the sandbox.
10. **The demo video**, as above.
11. **Public**: the README labelling new work and what existed before 27 Oct, the NOTICE, the repository made
    public, the submission and the X post (the founder).

## Tests (written with each deliverable, before its code)

- The variant: a signed answer's changes appear in the shop and the layout, and nothing else changes; the capital
  matches the price sheet.
- The pipeline: today's fab still builds byte for byte; the variant's sheets, IFC and bill of materials differ from
  today's only where the copies are; every code check reruns.
- The colleague: every tool call is one of the listed tools with valid arguments; "show me" ends with the walker at
  the named place; every number it states is read from the fab, never invented; the stand-in is labelled.
- The movie hall: the screen plays the film then the trailer; the trailer ends on the Chetnova card.
- The critic: a rule that games the metric is flagged on a fixed test case; the critic never changes a score.
- The Lean checker: real runs accepted, tampered copies rejected.

## Waiting on the founder

The Meta Model API key (the colleague, voice), the Baseten key (step 1's live model), the OK for cmake to build
llama.cpp on the server, the NOTICE text and the OK to make the repository public.
