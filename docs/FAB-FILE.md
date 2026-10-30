# One file for any fab (the modular gym, deliverable 1)

Written 30 Oct 2026, before the code. Decided by quiz the same day: the 4 Nov entry has the config file, its checks,
rails of any shape read from the file, the layout editor and a Meta model that writes a fab. This is the first
piece: the file. From the SMT2020 testbed; any layout here is of our own design, not a real fab.

## The idea

SMT2020 is one configuration. A fab file says everything a person or the editor chooses: which tools of each type
and what they cost, where they stand on a 2D floor plan, how the overhead rail runs, and where wafers come in and
leave. The simulator reads it.

## The format

The file is today's shop text (`fabgym-shop 1`: groups, routes, steps, lots, releases, layout, fleet), unchanged,
plus optional **plan records** after them, tab separated, written in this order:

| Record | Fields | Meaning |
|---|---|---|
| `price` | group, buy, day | dollars to buy one tool of the group, and dollars a day to run it |
| `node` | id, x, y | a point of the rail on the floor plan, in metres |
| `link` | from, to, metres | a one-way stretch of rail from one node to another, and its length |
| `station` | group, x, y, w, h | where the group's tools stand on the plan: a rectangle in metres, for drawing |
| `stop` | group, tool, node | the node where the group's tool number `tool` (from 0) loads and unloads |
| `stocker` | node | a stocker's port |
| `entry` | node | where new lots come onto the rail |
| `exit` | node | where finished lots leave |

A rail of any shape is nodes and links: a node with two links out is a split, with two in a merge. Lengths are
written, so a curve or a lift can be longer than the straight line between its ends.

A shop with no plan records writes exactly as before, so every shop and golden log today is unchanged. A plan does
not change a run in this deliverable: the engine still moves lots as the shop's `transport`, `oht` and `fleet` say.
Reading the track from the plan is deliverable 3.

## Refused on reading, with the line number

A link, stop, stocker, entry or exit naming a node that is not defined; a price, station or stop naming a group the
shop does not have; a stop's tool number at or past the group's count; a node defined twice; a negative price or
length.

## Today's campus as a plan

`fabsim fab-export SHOP` writes a shop with drawn rails (the realistic campus) as a fab file: one node per track
node, one link per stretch with its length, a stop for every tool's port, the stockers, and entry and exit at the
campus start. Plan coordinates: x along the campus west to east, phases end to end with their bridges; y from the
spine, north negative and south positive. Station rectangles are the box round a group's ports, 1 m wider each way
(assumed, for drawing only).

## Tests (written before the code: `crates/fabsim/tests/fab_file.rs`)

1. A shop with no plan has no plan and writes no plan records; the toy shops read and write back unchanged.
2. A hand-written fab file with every record reads and writes back unchanged, with the values it says.
3. The SMT2020 reference shop with a plan attached writes, reads back and, with the plan removed, has the recorded
   golden hash; its seed-0 one-day log has the golden hash; a toy's log is the same with and without a plan.
4. Bad plans are refused, each naming its line: unknown node, unknown group, tool number too high, a node twice, a
   negative price, a negative length.
5. The realistic campus exported to a plan holds its rails: as many nodes and links as the drawn track, the same
   total metres, a stop for every tool's port, a node for every stocker port, and entry and exit at the start; the
   exported file reads back to the same shop.
6. `fabsim fab-export` writes a file that reads back.

## Changes

- 31 Oct, with the checks (`docs/FAB-CHECKS.md`): a ninth plan record, `store` (group), for a group with no tools on
  the floor whose lots wait in a stocker for their time: SMT2020's `Delay_32`, 400 slots of waiting. Written last.
  `fabsim fab-export` writes one for every group the layout places in a stocker. The test that builds a plan by hand
  names the new field (`stores: vec![]`).
