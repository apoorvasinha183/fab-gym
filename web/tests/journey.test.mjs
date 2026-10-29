// Following one lot from start to finish on the real building (docs/LIVE-REAL.md). Written before the code. On the
// SMT2020 model, a published research model of a wafer fab, with a gigafab-style layout of our own design.
//
//     node --test web/tests/journey.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const J = require(join(ROOT, "web", "journey.js"));
const app = readFileSync(join(ROOT, "web", "app.js"), "utf8");
const html = readFileSync(join(ROOT, "web", "index.html"), "utf8");
const build = readFileSync(join(ROOT, "web", "build.sh"), "utf8");

// two steps: wait 0-10, work 10-20 on tool 4; move 20-30 on stretch 0; wait 30-100, work 100-110 on tool 7
const journey = {
  lot: "Lot_3.3", steps: [[0, "A", 4, 0, 10, 20], [1, "B", 7, 30, 100, 110]],
  entries: [[0, 21, 29, 1]], hoists: [[0, 1, 20, 21], [1, 0, 29, 30]],
};
const pace = { wait: 1, work: 2, move: 3 };

test("1. the journey plays as waits, work and moves, each at its own pace", () => {
  const P = J.plan(journey, pace);
  assert.deepEqual(P.segs.map(s => s.kind), ["wait", "work", "move", "wait", "work"]);
  assert.equal(P.total, 1 + 2 + 3 + 1 + 2);
  const a = J.at(P, 1 + 1);
  assert.equal(a.kind, "work");
  assert.equal(a.step, 0);
  assert.ok(Math.abs(a.t - 15) < 1e-9, "half way through the work, half way through its minutes");
  const m = J.at(P, 1 + 2 + 1.5);
  assert.equal(m.kind, "move");
  assert.ok(Math.abs(m.t - 25) < 1e-9);
  assert.equal(J.at(P, 99).step, 1, "past the end stays on the last step");
});

test("2. jumping to a step lands at its start", () => {
  const P = J.plan(journey, pace);
  assert.equal(J.startOf(P, 1), 1 + 2 + 3);
  assert.equal(J.at(P, J.startOf(P, 1)).step, 1);
});

test("3. where the lot is on a move: on its stretch, or hoisting at a node", () => {
  const nodes = [[0, 0], [10, 0]], edges = [[0, 1, 10]];
  const h = J.where(journey, nodes, edges, 20.5);
  assert.equal(h.state, "hoist");
  const r = J.where(journey, nodes, edges, 21 + (10 / 150) / 2);
  assert.ok(Math.abs(r.x - 5) < 1e-6 && r.state === "rail");
  assert.equal(J.where(journey, nodes, edges, 15), null, "not on the rails during work");
});

test("4. the page offers it in Flows on the building; the build writes the journey", () => {
  assert.match(html, /id="follow-lot"/);
  assert.match(html, /<script src="journey\.js"><\/script>/);
  assert.match(app, /data\/journey\.json/);
  assert.match(app, /FabJourney\.at\(/);
  assert.match(build, /web\/data\/journey\.json/);
});
