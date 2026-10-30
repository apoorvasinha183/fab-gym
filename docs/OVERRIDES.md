# Failure and recovery, per tool and per rail piece (the modular gym, deliverable 5)

Written 30 Oct 2026, before the code. The founder, 30 Oct: "Bring back the failure modes per tool, and rail piece,
the default version is what it is today but they should be able to configure it if they want. Let us first
modularize the thing." By quiz the same day: a JSON overrides file beside the fab file, listing only what differs.
On the SMT2020 model; every number a person puts in an overrides file is theirs, not a real fab's.

## Today, which stays the default

| What | Today | Where it is set |
|---|---|---|
| Breakdowns | each tool of a group fails at random: time to failure and repair time both exponential with the group's means; each tool has its own random stream | `group` record (MTTF, MTTR) |
| Maintenance | by calendar (every so many minutes) or by wafers processed, each lasting uniform(lo, hi) minutes | `pm`, `pmp` records |
| Fixed downs | windows when every tool of a group is down | `down` records, the outage dial |
| Defect holds | a rework finding holds the tool and the lots it touched just before | `defects` record |
| Recovery | the tool is repaired where it stands; a down due while it is busy waits for the job to end | the engine |
| Rails | never fail; a vehicle whose way is full takes another open stretch (a detour) | the engine |

## The modular part

Each tool is given its own **behaviour** before the run: its breakdowns, its maintenance and its recovery. With no
overrides every tool's behaviour is exactly what its group's records say today, drawn from the same random streams,
so every golden log is unchanged. Each rail stretch likewise has a behaviour: today, no breakdowns.

## The overrides file

```json
{
  "fabgym-overrides": 1,
  "groups": {
    "Planar_FE_79": {
      "breakdowns":  {"kind": "random", "mttf_hours": 40, "mttr_hours": 3},
      "recovery":    {"kind": "swap_to_spare", "spares": 1, "swap_minutes": 30}
    }
  },
  "tools": {
    "Planar_FE_79#2": {"maintenance": {"kind": "none"}}
  },
  "rails": {
    "n412>n413": {
      "breakdowns": {"kind": "random", "mttf_hours": 200, "mttr_minutes": 20},
      "recovery":   {"kind": "route_around"}
    }
  }
}
```

- `groups` applies to every tool of the group; `tools` (named `GROUP#k`, k from 1) to one tool and wins over its
  group. A key left out keeps today's setting.
- `rails` names a stretch by its two plan nodes, `FROM>TO` (the ids `fabsim fab-export` writes). Rail settings need a
  fleet.
- Times may be given in `_minutes` or `_hours`.

**Breakdowns** (tools): `none`; `random` (`mttf`, `mttr`: exponential, as today); `by_wafers` (`every` wafers
processed, repair `minutes: [lo, hi]` uniform: wear that comes with use).
**Maintenance** (tools): `none`; `calendar` (`every`, `minutes: [lo, hi]`); `by_wafers` (`every`, `minutes: [lo, hi]`).
Either replaces all of the group's maintenance records for the tools it applies to.
**Recovery** (tools): `repair_in_place` (today); `swap_to_spare` (`spares`, `swap`: while the group has a spare the
tool is back after the swap time and the broken unit is repaired off the floor, returning to the spares when its
repair time ends; with none left it repairs in place); `repair_and_hold_lots` (`lookback`, `hold`: as a breakdown
starts, the lots the tool finished in the lookback are held for `hold` minutes, as a defect finding does).
**Breakdowns** (rails): `none` (today); `random` (`mttf`, `mttr`): while down, no vehicle enters the stretch.
**Recovery** (rails): `route_around` (vehicles reroute over the open track, counted as detours; today's detour rule);
`wait` (vehicles queue at the stretch until it is repaired).

Refused, naming the path in the file (for example `groups.Planar_FE_79.breakdowns.mttf_hours`): an unknown group,
tool or stretch, an unknown kind, a missing or negative number, `lo` above `hi`, and rail settings without a fleet.
Each random stream is new and named by its tool or stretch, so changing one tool's settings leaves every other
tool's breakdown times as they were.

## What a run reports

With `record`, a run lists every breakdown and maintenance down as it falls due, and every rail stretch's breakdown:
`RunResult::due`, each with what (`breakdown`, `maintenance`, `rail`), the tool (`GROUP#k`) or stretch
(`FROM>TO`), the time it fell due and the minutes it is down for (the swap time when a spare is used). A down that
falls due while the tool is busy still waits for the job to end, as today. The API: `Overrides::parse(json, &shop)`,
then `engine::run_with(shop, opts, chooser, &overrides)`; `run` is `run_with` with no overrides.

## Later, optional: a custom state machine per tool

The founder asked (30 Oct) whether each tool could have its own state transitions. It can, cheaply: every
transition is one event, like today's breakdowns, maintenance and setups, and rules checked only when something
happens (a job ends, a count is reached, a repair finishes) never need polling. The kinds above are written so each
tool carries its own behaviour; a `custom` kind (states, and transitions on a timer, a wafer count or an event, with
probabilities) can be added later without reworking them. Not in this deliverable.

## Commands

`fabsim log SHOP SEED [UNTIL] --overrides FILE`, `fabsim score ... --overrides FILE`. The helper and the editor pass
the file the same way.

## Tests (written before the code: `crates/fabsim/tests/overrides.rs`)

1. No overrides, and an empty overrides file, leave the toy logs, the SMT2020 golden logs (seeds 0 to 2, one day)
   and a fleet run on the campus unchanged.
2. The file is refused, naming the path, for each case above.
3. A group's `random` breakdowns with a shorter time to failure give its tools more unscheduled down minutes; `none`
   gives them none apart from holds; another group's breakdown starts are unchanged.
4. One tool's override changes that tool only: its siblings' breakdown starts are unchanged.
5. `maintenance: none` removes the group's maintenance downs; `calendar` with a given period puts them that far apart.
6. `by_wafers` breakdowns come every so many wafers processed.
7. `swap_to_spare` makes a breakdown last the swap time while a spare is free, and the group's unscheduled down
   minutes fall against `repair_in_place` on the same seed.
8. `repair_and_hold_lots` holds the lots the tool finished in the lookback.
9. A rail stretch with breakdowns: no vehicle enters it while it is down; `route_around` records detours and every
   move still arrives; `wait` holds vehicles up longer than `route_around` on the same seed.
10. `fabsim log --overrides` reads the file.

## Changes (30 to 31 Oct, while building)

- **Test 5's window.** The shortest SMT2020 maintenance calendar is 7 days, its first drawn within the period, so a
  3-day run could show none for the group tested. The removal check now runs 7 days; the calendar check is unchanged.
- **Going round a break.** Reusing today's detour rule made vehicles cross over and straight back to the same break,
  every few seconds of fab time for the whole repair, and two waits retried at the same instant forever. Now a
  vehicle whose next stretch is broken takes the shortest way to its target that avoids every broken stretch, and
  waits, without retrying at the same instant, when there is none; a broken stretch never counts as about to free.
- **Test 9, and a finding.** Today's campus has no stretch with a way round: each of the 158 stretches leaving a
  split cuts part of the track off when it breaks (with the busiest, n17>n18, down, 388 of 1,259 nodes stay reachable
  from its start). So going round and waiting gave the same run, and test 9 now checks what holds: no vehicle enters
  a broken stretch, every move arrives or is under way, breaking the busiest stretch lowers deliveries, and going
  round is never worse than waiting. The going-round rule is tested properly once a map with a bypass can be built
  (deliverables 3 and 7). Probes: `crates/fabsim/examples/rail_probe.rs`, `rail_reach.rs`.
