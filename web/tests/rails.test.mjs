// The Rails lens on the floor page (docs/FLEET.md): the drawn rails, which are the simulator's track, and the fleet
// replayed from the simulator's trace. Written before the code. On the SMT2020 model, a published research model of
// a wafer fab, with a gigafab-style layout of our own design.
//
//     node --test web/tests/rails.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const R = require(join(ROOT, "web", "rails.js"));
const html = readFileSync(join(ROOT, "web", "index.html"), "utf8");
const app = readFileSync(join(ROOT, "web", "app.js"), "utf8");
const build = readFileSync(join(ROOT, "web", "build.sh"), "utf8");

// three nodes, two stretches; vehicle 0 carries a lot along the first, vehicle 1 runs empty on the second and stays
// on it, vehicle 2 hoists at the port; a fourth vehicle is parked
const fixture = () => R.prep({
  track: { nodes: [[0, 0, "lane"], [10, 0, "lane"], [10, 5, "port"]], edges: [[0, 1, 10], [1, 2, 5]] },
  fleets: [{ vehicles: 4, from: 0, to: 10, entries: [[0, 0, 0, 1, 1], [1, 1, 0, null, 0]], hoists: [[2, 2, 7, 1, 0, 1]] }],
});

test("1. the floor page has a Rails lens and a strip to pick the fleet and play it", () => {
  assert.match(html, /data-lens="rails"[^>]*>Rails</);
  const strip = html.slice(html.indexOf('id="rails-ctl"'), html.indexOf("</div>", html.indexOf('id="rails-ctl"')));
  assert.ok(strip, "a rails strip");
  assert.match(html, /id="rails-fleet"/);
  assert.match(html, /id="rails-play"/);
  assert.match(html, /<script src="rails\.js"><\/script>/);
});

test("2. where each vehicle is, from the trace: moving, carrying, hoisting, held up or parked", () => {
  const d = fixture();
  let a = R.at(d, 0, 10 / 150 / 2);
  const v0 = a.vehicles.find(v => v.id === 0);
  assert.ok(Math.abs(v0.x - 5) < 1e-9 && v0.y === 0 && v0.state === "loaded", "half way along its stretch, carrying");
  assert.equal(a.vehicles.find(v => v.id === 1).state, "empty");
  assert.equal(a.vehicles.find(v => v.id === 2).state, "hoist");
  assert.deepEqual(a.counts, { empty: 1, loaded: 1, hoist: 1, held: 0, idle: 1 });
  a = R.at(d, 0, 0.5);
  assert.equal(a.vehicles.find(v => v.id === 0).state, "held", "still on its stretch long after it would have left");
  assert.equal(a.vehicles.find(v => v.id === 1).state, "held");
  assert.equal(a.counts.held, 2);
  a = R.at(d, 0, 2);
  assert.equal(a.vehicles.find(v => v.id === 0), undefined, "gone after it left");
  assert.equal(a.counts.idle, 3, "vehicle 1 is still held; 0 and 2 are parked with the fourth");
});

test("3. the page loads the fleet, draws it on the floor's canvas, and the build writes it", () => {
  assert.match(app, /data\/fleet\.json/);
  assert.match(app, /UI\.lens === "rails"/);
  assert.match(app, /FabRails\.draw\(/);
  assert.match(build, /web\/data\/fleet\.json/);
});

test("4. the lens says what it shows and where the numbers come from", () => {
  assert.match(app, /the simulator's own track/);
  assert.match(R.NOTE, /SMT2020/);
});
