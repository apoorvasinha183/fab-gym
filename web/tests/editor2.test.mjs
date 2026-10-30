// Editor take two (docs/EDITOR-TAKE-TWO.md): the challenges, the score's spend, the selection widget's failures as an
// overrides file, the work-in-fab cap, and the replay. Written before the code. On the teaching fab of our own and
// the SMT2020 model; not a real fab.
//
//     node --test web/tests/editor2.test.mjs          (from the repo root; needs `cargo build --release`)

import { test } from "node:test";
import assert from "node:assert/strict";
import { writeFileSync, mkdtempSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const E = require(join(HERE, "..", "editor-core.js"));
const FABSIM = join(ROOT, "target", "release", "fabsim");

function fabsim(args, files) {
  const d = mkdtempSync(join(tmpdir(), "fabed2-"));
  for (const [name, text] of Object.entries(files)) writeFileSync(join(d, name), text);
  const r = spawnSync(FABSIM, args.map((a) => (a.startsWith("@") ? join(d, a.slice(1)) : a)), { maxBuffer: 1 << 28 });
  return { code: r.status, out: r.stdout.toString(), err: r.stderr.toString() };
}

/** Run a challenge set-up ({state, base, overrides}) for its days and return the score. */
function score(ch, setup) {
  const fab = E.fabText(setup.base, setup.state, { vehicles: setup.state.vehicles });
  const args = ["moods", "@c.fab.txt", "1", "--until", String(ch.days * 1440), "--every", "60"];
  const files = { "c.fab.txt": fab };
  if (setup.overrides) {
    files["o.json"] = JSON.stringify(setup.overrides);
    args.push("--overrides", "@o.json");
  }
  const r = fabsim(args, files);
  assert.equal(r.code, 0, r.err);
  return JSON.parse(r.out).score;
}

test("four challenges, in order", () => {
  assert.deepEqual(E.CHALLENGES.map((c) => c.id), ["rush", "polisher", "breakdown", "lean"]);
  for (const c of E.CHALLENGES) {
    assert.ok(c.title && c.problem && c.goal, c.id);
    assert.ok(c.target.wafers > 0 && c.days > 0, c.id);
  }
});

for (const id of ["rush", "polisher", "breakdown", "lean"]) {
  test(`challenge ${id}: the start passes the checks and misses the target; its fix meets it`, () => {
    const c = E.CHALLENGES.find((x) => x.id === id);
    const start = c.setup();
    const chk = fabsim(["fab-check", "@c.fab.txt", "--json"], { "c.fab.txt": E.fabText(start.base, start.state, { vehicles: start.state.vehicles }) });
    assert.equal(chk.code, 0, chk.out);
    const s0 = score(c, start);
    assert.ok(!E.meets(s0, c.target, 0), `${id} start ${JSON.stringify(s0)} misses ${JSON.stringify(c.target)}`);
    const fixed = c.fix(c.setup());
    const s1 = score(c, fixed);
    const extra = E.spend(fixed.state) - E.spend(start.state);
    assert.ok(E.meets(s1, c.target, extra), `${id} fix ${JSON.stringify(s1)} (spent ${extra}) meets ${JSON.stringify(c.target)}`);
  });
}

test("every placed group is priced and the simulator's spend is the prices times the counts", () => {
  const s = E.template("teaching");
  const fab = E.fabText(E.TEACHING_SHOP, s);
  const groups = s.blocks.filter((b) => b.kind === "group");
  for (const b of groups) assert.ok(fab.includes(`price\t${b.group}\t`), b.group);
  const r = fabsim(["moods", "@c.fab.txt", "1", "--until", "120", "--every", "60"], { "c.fab.txt": fab });
  assert.equal(r.code, 0, r.err);
  assert.equal(JSON.parse(r.out).score.spend_usd, E.spend(s));
});

test("the selection widget's failures and recoveries become an overrides file the simulator reads", () => {
  const s = E.template("teaching");
  const litho = s.blocks.find((b) => b.group === "Litho_T");
  litho.fail = { kind: "random", mttf_minutes: 300, mttr_minutes: 60 };
  litho.rec = { kind: "swap_to_spare", spares: 1, swap_minutes: 20 };
  const spine = Object.keys(s.rail).find((k) => s.rail[k].spine && s.rail[k].o[0]);
  s.rail[spine].fail = { kind: "random", mttf_minutes: 200, mttr_minutes: 30 };
  s.rail[spine].rec = { kind: "route_around" };
  const ov = E.overridesFor(s);
  assert.equal(ov["fabgym-overrides"], 1);
  assert.deepEqual(ov.groups.Litho_T.breakdowns, litho.fail);
  assert.deepEqual(ov.groups.Litho_T.recovery, litho.rec);
  assert.equal(Object.keys(ov.rails).length, 1);
  const r = fabsim(["moods", "@c.fab.txt", "1", "--until", "600", "--every", "60", "--overrides", "@o.json"], { "c.fab.txt": E.fabText(E.TEACHING_SHOP, s), "o.json": JSON.stringify(ov) });
  assert.equal(r.code, 0, r.err);
  assert.equal(E.overridesFor(E.template("teaching")), null, "nothing set, no file");
});

test("a work-in-fab cap is written as a cap record", () => {
  const s = E.template("teaching");
  s.cap = 20;
  assert.ok(E.fabText(E.TEACHING_SHOP, s).split("\n").includes("cap\t20"));
});

test("a vehicle in the replay is drawn along its stretch at its time", () => {
  const stays = [[0, "c2_6", "c3_6", 10, 12, true, false], [0, "c3_6", "c4_6", 12, 14, true, true], [1, "c9_7", "c8_7", 11, null, false, false]];
  const at = E.vehicleAt(stays, 11);
  const v0 = at.find((v) => v.vehicle === 0), v1 = at.find((v) => v.vehicle === 1);
  assert.deepEqual([v0.x, v0.y, v0.loaded], [2.5, 6, true]);
  assert.equal(v1.x, 9, "still on its stretch at the end: drawn at its start");
  assert.equal(E.vehicleAt(stays, 13).find((v) => v.vehicle === 0).hot, true);
  assert.equal(E.vehicleAt(stays, 20).filter((v) => v.vehicle === 0).length, 0, "gone after its last stay");
});
