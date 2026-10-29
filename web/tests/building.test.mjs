// The Live view on the real building (docs/LIVE-REAL.md). Written before the code. On the SMT2020 model, a published
// research model of a wafer fab, with a gigafab-style layout of our own design.
//
//     node --test web/tests/building.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const B = require(join(ROOT, "web", "building.js"));
const html = readFileSync(join(ROOT, "web", "index.html"), "utf8");
const app = readFileSync(join(ROOT, "web", "app.js"), "utf8");
const build = readFileSync(join(ROOT, "web", "build.sh"), "utf8");

// a building of two groups: A with two tools, B with one, drawn in an order of their own
const building = {
  tools: [["B", 10, 12, 0, 2, "etch", 0], ["A", 0, 2, 0, 2, "etch", 0], ["A", 0, 2, 4, 6, "etch", 1]],
  holding: ["Delay_32"],
};

test("1. each engine tool is drawn at its own box, by group and by order within the group", () => {
  // the engine's tools: groups A, A, B (indexes into its group list)
  const map = B.toolBoxes(building, ["A", "B"], [0, 0, 1]);
  assert.deepEqual([...map], [1, 2, 0]);
});

test("2. a shop fits the building when its drawn groups and their tool counts match", () => {
  assert.ok(B.fits(building, [["A", 2], ["B", 1], ["Delay_32", 1]]));
  assert.ok(!B.fits(building, [["A", 2], ["B", 1], ["A@B", 1]]), "a copy the drawings do not hold");
  assert.ok(!B.fits(building, [["A", 3], ["B", 1]]), "a different count");
});

test("3. vehicles at a moment, from the flat arrays, with the lot each carries", () => {
  const nodes = [[0, 0], [10, 0], [10, 5]];
  const edges = [[0, 1, 10], [1, 2, 5]];
  // vehicle 0 hoists lot 7 up at node 0 (0 to 1), rides stretch 0 loaded (1 to 3), hoists it down at node 1 (3 to 4);
  // vehicle 1 runs empty on stretch 1 from 0 and is still there
  const entries = new Float32Array([0, 0, 1, 3, 1, 1, 1, 0, -1, 0]);
  const hoists = new Float32Array([0, 0, 7, 1, 0, 1, 0, 1, 7, 0, 3, 4]);
  const F = B.prepFleet(entries, hoists, 3, 100);
  let a = B.vehicles(F, nodes, edges, 0.5);
  const v0 = a.list.find(v => v.id === 0);
  assert.equal(v0.state, "hoist");
  assert.equal(v0.lot, 7, "the lot being hoisted up");
  a = B.vehicles(F, nodes, edges, 1 + (10 / 150) / 2);
  const m = a.list.find(v => v.id === 0);
  assert.ok(Math.abs(m.x - 5) < 1e-6 && m.state === "loaded" && m.lot === 7, "half way, carrying lot 7");
  assert.equal(a.list.find(v => v.id === 1).state, "held", "on its stretch long after free flow");
  assert.equal(a.counts.idle, 1);
  a = B.vehicles(F, nodes, edges, 5);
  assert.equal(a.list.find(v => v.id === 0), undefined, "parked after setting the lot down");
});

test("4. wafers done in a step, 25 to a lot", () => {
  assert.equal(B.wafersDone(10, 20, 9, 25), 0);
  assert.equal(B.wafersDone(10, 20, 15, 25), 12);
  assert.equal(B.wafersDone(10, 20, 20, 25), 25);
  assert.equal(B.wafersDone(10, 10, 10, 25), 25, "a step of no time is done");
});

test("5. the Live view draws the building; the Rails lens is gone; the build writes the data", () => {
  assert.match(app, /data\/building\.json/);
  assert.match(app, /data\/shop-real\.txt/);
  assert.match(app, /FabBuilding\.vehicles\(/);
  assert.match(app, /FabBuilding\.wafersDone\(/);
  assert.match(html, /<script src="building\.js"><\/script>/);
  assert.ok(!/data-lens="rails"/.test(html), "Live is the rails now");
  assert.match(build, /web\/data\/building\.json/);
  assert.match(build, /web\/data\/shop-real\.txt/);
});
