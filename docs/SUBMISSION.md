# The submission pack

Written 31 October 2026, from what runs today. The founder, by quiz: "Submission pack" next (README, the demo path and a
shot list for the video). Submissions close **4 November, 9:00 PM ET** (5 November, 7:30 AM IST). Indie track (decided 4 Nov). On the
SMT2020 testbed and a teaching fab of our own; not a real fab. Agents propose, the simulator scores, a person signs.

## 1. The demo path (3 minutes, live)

The same walk is clicked end to end by `web/tests/demopath.test.mjs` (no model, no credit), so it cannot break without
a test failing. Start the helper (`python3 -m agent.helper --port 8766`, `--preset open` for Muse Spark Open) and open
`http://127.0.0.1:8766`.

| Time | Page | Do | Say (plain, in your own voice) |
| --- | --- | --- | --- |
| 0:00 | Home | Let the hook sit; click **Play a challenge** later, not yet | "A polishing machine just finished. Five batches of wafers are waiting. Which one goes next? Fabs answer that thousands of times a day, with rules of thumb." |
| 0:15 | Floor | Speed to **12×**; point at a polisher showing *Gassed*; click **Follow one lot** | "This is a whole chip fab from the SMT2020 testbed: 1,043 machines, simulated live in the browser. This polisher is flat out and its line keeps growing. One batch spends most of its life waiting in lines like this." |
| 0:50 | Build | Challenge 1: read the advice line; press **J**; draw track through the bay's loop round the break (practise first), or **Stuck? Show me a fix** | "Here's a fab you can draw. A piece of track keeps breaking and every car behind it waits. J shows only the jams. Give the cars a way round... and the simulator reruns as soon as I let go." |
| 1:25 | Build | The float rises; the **Challenge met** card; stars | "Plus a few wafers a day, challenge met, one star. Beat the target by 2% for two." |
| 1:35 | Floor, ask bar | Ask a question in plain words (a worked example, or live with the model) | "Now ask the fab. Meta's open model, Muse Spark Open, turns the question into a scenario, marking what you said and what it assumed. It writes rules as small Rust functions; each runs in a sandbox and the simulator scores it on days it never saw, against today's rule." |
| 2:10 | Floor, answer | Point at the card's numbers and **Sign** | "The card quotes only the simulator's numbers, with how sure we are. The model proposes; a person signs." |
| 2:25 | Evidence | Scroll the four findings; stop on **120 / 120** | "What we found, in plain words. And every scored run is checked: a referee written in Lean re-read all 120 runs, 423 million machine jobs. All passed." |
| 2:50 | Close | The closing card | "Fab Gym, by Chetnova. An operating system for your full org." |

## 2. Shot list for the video

Screen capture at 1920 x 1080 of the live pages; voiced by the founder. Built means it runs today; planned means it is in
`docs/NARRATIVE.md` but not built, so it stays out unless it is finished first.

| # | Time | Shot | Source | Built |
| --- | --- | --- | --- | --- |
| 1 | 0:00–0:15 | The puzzle as text over the floor at 12× | Floor page | Built |
| 2 | 0:15–0:35 | Hover the gassed polisher; its card | Floor page | Built |
| 3 | 0:35–0:50 | Follow one lot along its route | Floor page | Built |
| 4 | 0:50–1:10 | Challenge 1: the ring on the broken track, the red jam, J for the jam map | Build page | Built |
| 5 | 1:10–1:35 | Draw the bypass; the float; Challenge met with confetti and a star | Build page | Built |
| 6 | 1:35–2:10 | Ask in plain words; the scenario with said and assumed values; the rules scored on held-out days | Floor page, ask panel | Built (a live answer needs the model key, see the checklist) |
| 7 | 2:10–2:25 | The card and the signature | Floor page, answer | Built |
| 8 | 2:25–2:50 | Evidence: four findings, 120 / 120 | Evidence page | Built |
| 9 | 2:50–3:00 | Closing card over the building | Godot walkthrough or the Blender film (`docs/FAB-FILM-SCRIPT.md`) | Film rendered 27 Oct; the game runs |
| — | — | The colleague, the movie hall, voice questions, the critic | `docs/NARRATIVE.md` steps 5 to 8 | Planned: leave out |

Words to keep out: "real fab", "TSMC", "runs a fab", "guaranteed", any result or placing not yet announced. Say "the
SMT2020 testbed" when a number is from it, and "made up" or "assumed" for prices.

## 3. The submission form, a draft

- **Project:** Fab Gym, by Chetnova.
- **One line:** A simulated chip fab you can draw, ask questions in plain words and trust: Meta's open model writes the
  rules, the simulator scores them, a Lean referee checks every run, and a person signs.
- **What it is:** An open simulator of a 1,043-machine wafer fab built on the published SMT2020 testbed, in Rust (about
  0.03 s per simulated day), in the browser through WebAssembly. Three ways in: watch the whole fab live (Floor), draw a
  fab and earn stars against four challenges (Build), and read what the simulator taught us in plain words (Evidence).
- **How it uses Meta's models:** Muse Spark Open (on Baseten) turns a plain-English question into a scenario that must
  pass a schema, every value marked said or assumed, and writes candidate dispatch rules as Rust functions compiled to
  WebAssembly and run in a sandbox; it reads their scores on training days and rewrites them; finalists are scored once
  on held-out days against today's rule. Ideas and trials use `muse-spark-1.3-contributor`. The cast of machines was
  drawn with Muse Image.
- **Impact:** A fab cannot test a new rule for running its floor without risking weeks of real output. Fab Gym tests it
  first, says how sure it is, and shows it in words a newcomer follows. The same machinery is Chetnova's: an operating
  system for an organisation, simulated before it changes.
- **Technical depth:** an exact event-log match against a reference engine, paired seeds with 95% intervals, a
  pre-registered uncertainty study, a sandbox with a fuel limit, and a Lean 4 referee with soundness proofs that passed
  all 120 scored runs.
- **What is new:** everything in the repository was built from the 26 October kickoff; earlier work is labelled in the
  README's "What is new in this hackathon".

## 4. The checklist (only the founder can do these)

- [ ] The NOTICE text, then the OK to make `apoorvasinha183/fab-gym` public (the repo must be public to be judged).
- [ ] The Baseten key for Muse Spark Open, so the video's live answer uses the open model the README names
      (`--preset open`); without it, use a worked example and say so.
- [ ] Record the video from section 1 in your own voice; upload it.
- [ ] Submit on the Cerebral Valley page before 4 November, 9:00 PM ET.
- [ ] The X post (Most Viral is counted until 8 November).

## Changes
