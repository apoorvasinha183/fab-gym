# The checks a layout must pass (the modular gym, deliverable 2)

Written 31 Oct 2026, before the code. A fab file (`docs/FAB-FILE.md`) can describe any layout; these checks say
whether it can run, and why not, before the simulator spends any time on it. The editor runs them on every edit and
the Meta model that writes a fab (deliverable 8) is shown their messages to fix what it wrote. On the SMT2020 model;
any layout here is of our own design or a person's, never a real fab.

## What is checked

The checks read the shop and its plan (nodes, one-way links, stops, stockers, entry, exit). Reaching means following
links in their direction.

**Errors (the layout cannot run):**

| Code | When |
|---|---|
| `no_plan` | the file has no plan records |
| `no_entry`, `no_exit` | no entry node, or no exit node |
| `missing_stops` | a group has fewer stops than tools (each tool `0..count` needs its own stop) |
| `unreachable` | a tool's stop cannot be reached from any entry |
| `no_way_out` | from a tool's stop no exit can be reached |
| `route_gap` | a route goes from one group to the next and no stop of the first reaches any stop of the next; also the entry to a route's first group and its last group to an exit |
| `trap` | a node reachable from an entry from which no exit can be reached: a vehicle that goes in never comes back out (a node with no way out that is not an exit is one) |

**Warnings (it can run, but something is off):**

| Code | When |
|---|---|
| `stocker_unreachable` | a stocker cannot be reached from an entry or cannot reach an exit |
| `no_price` | a group has no price, so the budget leaves it out (only when the plan prices some group) |
| `overlap` | two groups' stations overlap on the plan |
| `too_short` | a link is shorter than the straight line between its two nodes |

Each issue names what it is about (groups, tools as `GROUP#k`, node ids, or a link `FROM>TO`) and says in one
sentence what is wrong and how to fix it.

## Interfaces

- `fabsim::checks::check(&shop) -> Vec<Issue>`, `Issue { severity, code, message, at }`, errors first.
- `fabsim fab-check FILE [--json]`: one line per issue, or a JSON list; exit code 0 with no errors, 2 with errors.

## Tests (written before the code: `crates/fabsim/tests/fab_checks.rs`)

1. Today's campus exported by `fabsim fab-export` has no errors (its only warnings may be `no_price`, none here
   since it has no prices).
2. The tiny hand-written fab has no errors and no warnings.
3. Each error is raised by a small change to the tiny fab, naming the right thing: no plan, no entry, no exit, a
   tool without a stop, a stop nobody can reach, a stop with no way out, a route gap, a trap.
4. Each warning likewise: an unreachable stocker, a group with no price, overlapping stations, a link shorter than
   the straight line.
5. `fabsim fab-check --json` prints the issues as JSON and exits 2 with errors, 0 without.

## Changes

- 31 Oct, the first run: **today's campus has two traps.** The drawn spine rails (`Track::drawn`, viz/look/scene.py)
  stop at the campus's far ends with no U-turn: the south rail's west end (n35 on the exported plan) and the north
  rail's east end (n110). A vehicle there could go nowhere. Runs never send one there, since a vehicle only takes a
  stretch from which its target can be reached, so no result changes; but the layout has two dead ends. Test 1 now
  says what holds: the only errors are traps, exactly two, each a spine rail's end with no way out. Adding U-turns
  would change the drawn building and is the founder's call. Probe: `crates/fabsim/examples/trap_probe.rs`.
- The `store` record (docs/FAB-FILE.md, Changes) came with this deliverable: SMT2020's delay group has no tools on
  the floor, so it needs no stops; route checks reach a stored group through any stocker.
