# Race the AI, and the groundwork for Meta's models in the 2D gym

Written 31 October 2026, before the tests and the code. From the plan "Five Meta features for the 2D gym" and the founder's answers the same day: build in the plan's
order, starting with the groundwork and Race the AI; caps inside the helper's $5 of Race the AI $2 and $1 for each of
the others. On a teaching fab of our own; not a real fab. Agents propose, the simulator scores, a person signs.

## First calls (31 Oct, approved, about 2 cents in all)

- **Muse Wonder** (`muse-wonder-1.0`, `/v1/chat/completions`): asked to lay one piece of track with a `lay_track` tool,
  it answered in 2.8 s with that tool call and its arguments, 525 tokens in and 159 out (72 of them thinking), about
  half a cent.
- **Muse Image** (`muse-image-1.0`, `/v1/images/generations`): a poster of a fab on grid paper in 12.7 s, 1600 x 1600,
  $0.01.
- **SAM 3.1** (`sam-3.1`, `/v1/responses`, streamed): an image sent inline as a data URL was taken ("images_processed":
  1); the concept "rectangle" found nothing in a plain pencil-style line drawing, in 1.7 s.

## Groundwork (shared by the five features)

1. **One meter per feature.** Each feature counts its own spend in its own file with its own cap (Race the AI $2,
   the poster, the daily challenges and the sketch $1 each), and every model call also stays under the helper's total
   ($5 by default) across all of them.
2. **Keys stay on the Mac.** Each feature has its own route on the helper; the page sends what it wants and gets back
   the model's reply, which model answered, and what it cost.
3. **A stand-in for every model.** Started with `--stand-in DIR`, the helper answers each feature from recorded replies
   in `DIR` instead of calling a model, says so in every reply ("stand-in"), and spends nothing. The tests use it; so
   does a machine with no key.

## Race the AI

4. **Let the AI try.** A button in every challenge's banner. Muse Wonder plays the challenge with the same moves a
   player has, through tools that do exactly what the editor does:
   - `look`: the map as text: the floor's size, every piece (kind, group, place, machines), the track with its
     directions and the broken pieces, the checks, the advice line, the last score, the stars, the target and budget;
   - `lay_track` (a path of neighbouring cells, like a drag), `set_track_direction`, `erase`, `place`;
   - `set_machines`, `set_when_it_breaks` (for a machine group or a track piece), `set_cars`, `set_cap`;
   - `run`: waits for the simulator's rerun of the changes and returns the score, the stars and the advice.
   Every move goes through the editor, so it shows on the map, is checked, reruns, and can be undone.
5. **The AI's panel.** Beside the map: each move with the one-line reason the model gave, the score and stars as they
   come, which model is playing, what this game has cost and the cap. A Stop button. The game ends at three stars, at
   30 moves, when the model stops calling tools, or at the cap, and the panel says which.
6. **Bad moves are refused, not hidden.** A call to an unknown tool, or with arguments the tool cannot use, gets an
   error back to the model and a line in the panel; the game goes on.

## Tests (written before the code)

`agent/tests/test_race.py` (Python, no model called):
- **RA1** the race tools are the ten named above, each a function with an object schema; the system prompt names
  every tool and the star rule.
- **RA2** with a stand-in, `/api/race/step` returns the recorded reply for the move it is asked for (the number of
  model turns so far picks the line), marked "stand-in", costing nothing.
- **RA3** a race meter at its cap refuses the step with a plain message and sends nothing; so does the helper's total.
- **RA4** a reply's usage is priced as Muse Wonder (the first call's 525 in and 159 out cost $0.005280).
- **RA5** a request with a message from a role other than user, assistant or tool, or more than 200 messages, is
  refused.

`web/tests/race.test.mjs` (headless Chrome, a helper of its own with a recorded game for challenge 1):
- **RA6** "Let the AI try" opens the panel; the recorded game's moves appear in order with their reasons; the broken
  track piece at (3, 6) is set to let cars route round it; the run earns at least one star; the panel shows "stand-in"
  and $0.00.
- **RA7** a recorded unknown tool is refused with a line in the panel, and the game still ends.
- **RA8** one undo after the game takes back the AI's last change.

## Changes
