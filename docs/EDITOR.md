# The map editor (the modular gym, deliverable 7)

Written 31 Oct 2026, before the code. Decided by quiz the same day: a new page, `web/editor.html`, in the floor
page's 2.5D look, served by the same helper on 127.0.0.1, which calls the real simulator; one block per tool group
with a count; 3 m tiles. The look and the cast come from the design page.
On the SMT2020 model or a teaching fab of our own; never a real fab.

## What a person does

1. Start from a template: the **teaching fab** (eight groups, one per cast area, a short route) or **SMT2020** (all
   105 groups, laid out in bays by area along a two-lane spine with U-turns at both ends, the delay group held in a
   stocker).
2. Place, move and remove blocks (a tool group, its count set in the inspector), stockers, the entry and the exit;
   lay one-way rail by dragging; give a rail piece more ways out to split it.
3. Press **Check**: the simulator's checks (`fabsim fab-check`), each pinned to the map.
4. Press **Run**: if there are no errors, the simulator runs the fab with a fleet and returns its moods
   (`fabsim moods`): a time slider steps through the run, each block shows its group's mood badge and its card,
   rails tint by jam, and the counts of lots in each mood sit beside the map.

## How the map becomes a fab file (`web/editor-core.js`)

- Every rail cell is a node `c<x>_<y>` at (3x, 3y) metres; each way out is a link of 3 m.
- A block's tools take their stops on the rail cells beside the block, in turn.
- A block's station is its rectangle in metres; stocker blocks give stocker nodes beside them; the entry and exit
  blocks give the entry and exit nodes beside them; groups listed in `stores` get a `store` record.
- The fab file is the template's shop text with each placed group's count set to the block's, a `fleet` record when
  none is there (120 vehicles for SMT2020, 12 for the teaching fab; assumed), and these plan records.
- A block's mood at a moment is the most common mood among its group's tools; a tie goes to the more serious (hurt,
  physio, hold, full, tired, batch, setup, pm, sleep, work).

## The helper's endpoints

`GET /api/fab/base?name=smt2020` (the shop text and areas); `POST /api/fab/check {fab}` (the checks); `POST
/api/fab/run {fab, seed, days, every}` (the checks, then, with no errors, a run's moods). One run at a time, niced.

## Tests (written before the code)

`web/tests/editor.test.mjs`: the teaching fab passes the checks; every block has a stop per tool beside it; links
are 3 m and node ids unique; the fab text keeps the base shop and changes only counts; cutting the loop is caught;
the SMT2020 template places every group once with its count, holds the delay group in a stocker and passes; a
block's mood. `agent/tests/test_editor.py`: a good fab passes and a bad one is named; a run gives moods frames; a
fab with errors is not run; text that is not a fab is refused plainly; the base shop is served; the endpoints and
the page answer over HTTP.
