// The Results tab: every simulation and policy run as an entry you can open to see the simulator's settings and the
// numbers that came from it (the founder, 29 Oct: "think of that like the logs of the sims and/or policy change").
// Written before the code. On the SMT2020 model, a published research model of a wafer fab.
//
//     node --test web/tests/results.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const B = require(join(ROOT, "web", "tools", "results-build.js"));
const U = require(join(ROOT, "web", "ui.js"));

test("every saved experiment is an entry with its settings, its numbers and its files", () => {
  const entries = B.buildResults(ROOT);
  for (const id of ["two-families", "evolve-x4", "lean-long-units", "rl-train", "rl-contest-defects-on", "rl-contest-defects-off"])
    assert.ok(entries.some(e => e.id === id), `no entry ${id}`);
  for (const e of entries) {
    assert.ok(e.title && e.question && e.when && e.kind, e.id);
    assert.ok(e.settings.length >= 3 && e.settings.every(s => s.length === 2 && s[0] && s[1] !== undefined), e.id);
    assert.ok(e.numbers.columns.length >= 2 && e.numbers.rows.length >= 1, e.id);
    assert.ok(e.numbers.rows.every(r => r.length === e.numbers.columns.length), e.id);
    assert.ok(e.headline, e.id);
    assert.ok(e.files.length >= 1 && e.files.every(f => existsSync(join(ROOT, f))), e.id);
    assert.match(e.note, /SMT2020 model/, e.id);
  }
  // newest first
  for (let i = 1; i < entries.length; i++) assert.ok(entries[i - 1].when >= entries[i].when);
});

test("a run in the page becomes an entry of the same shape", () => {
  const e = U.runEntry({
    kind: "what-if", title: "Shortest processing first, Planar_FE_79 down 8 h", question: "Try a change",
    settings: [["Dispatch rule", "Shortest processing first"], ["Seeds", "0 to 9"], ["Days", "3"]],
    columns: ["Measure", "Change", "95% interval"], rows: [["Moves", "+120", "+40 to +200"]], headline: "Moves +120",
  });
  assert.equal(e.kind, "what-if");
  assert.ok(e.id && e.when && e.files.length === 0);
  assert.match(e.note, /SMT2020 model/);
  assert.equal(e.numbers.rows[0].length, e.numbers.columns.length);
});
