// The redesigned floor page's pure parts (docs/FLOOR-UI.md). Written before the code.
// On the SMT2020 model, a published model of a fab; not a real fab.
//
//     node --test web/tests/ui.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const U = require(join(HERE, "..", "ui.js"));
const summary = JSON.parse(readFileSync(join(ROOT, "results", "two-families", "summary.json"), "utf8"));
const runs = readFileSync(join(ROOT, "results", "two-families", "runs.tsv"), "utf8");

test("the tilted view maps there and back, and picks the hall under a point", () => {
  const views = [{ rot: -0.66, tilt: 0.56, scale: 7, ox: 400, oy: 120 }, { rot: 0.3, tilt: 0.8, scale: 2.5, ox: -50, oy: 300 }];
  for (const v of views) {
    for (const [x, y] of [[0, 0], [12.5, -3], [300, 140], [-40, 77]]) {
      const [sx, sy] = U.iso(x, y, v);
      const [bx, by] = U.isoInverse(sx, sy, v);
      assert.ok(Math.abs(bx - x) < 1e-9 && Math.abs(by - y) < 1e-9, `${x},${y}`);
    }
  }
  const halls = [{ name: "Lithography", x: 0, y: 0, w: 50, h: 30 }, { name: "Polishing", x: 70, y: 0, w: 20, h: 30 }];
  const v = views[0];
  const [sx, sy] = U.iso(80, 15, v);
  assert.equal(U.hallAt(halls, sx, sy, v).name, "Polishing");
  const [ox, oy] = U.iso(60, 15, v);
  assert.equal(U.hallAt(halls, ox, oy, v), null);
});

test("axis ticks are round, even and cover the range, with signed labels", () => {
  for (const [lo, hi] of [[-604, 781], [0.3, 4.7], [-1666, -2], [12, 13]]) {
    const t = U.niceTicks(lo, hi);
    assert.ok(t.length >= 3 && t.length <= 7, `${lo}..${hi}: ${t}`);
    const step = t[1] - t[0];
    for (let i = 2; i < t.length; i++) assert.ok(Math.abs(t[i] - t[i - 1] - step) < 1e-9);
    const mag = Math.pow(10, Math.floor(Math.log10(step)));
    assert.ok([1, 2, 5, 10].some((m) => Math.abs(step / mag - m) < 1e-9), `step ${step}`);
    assert.ok(t[0] <= lo + step && t[t.length - 1] >= hi - step);
  }
  assert.equal(U.tickLabel(750), "+750");
  assert.equal(U.tickLabel(-566.4), "−566.4");
  assert.equal(U.tickLabel(0), "0");
});

test("verdicts read the interval the right way round", () => {
  assert.equal(U.verdictOf({ lo: 2, hi: 9 }, true), "better");
  assert.equal(U.verdictOf({ lo: 2, hi: 9 }, false), "worse");
  assert.equal(U.verdictOf({ lo: -9, hi: -2 }, true), "worse");
  assert.equal(U.verdictOf({ lo: -9, hi: -2 }, false), "better");
  assert.equal(U.verdictOf({ lo: -2, hi: 9 }, true), "no clear effect");
  assert.equal(U.verdictOf(null, true), "no clear effect");
  assert.equal(U.verdictOf({ lo: null, hi: null }, true), "no clear effect");
});

test("the numbers view's rows come from the sweep", () => {
  const rows = U.sweepRows(summary, 4, "money");
  assert.equal(rows.length, 14);
  assert.ok(!rows.some((r) => r.strategy === "D1 share" && r.policy === "P0 today"));
  const bf = rows.find((r) => r.strategy === "D1 share" && r.policy === "P1 family B first");
  assert.equal(bf.mean.toFixed(1), "750.5");
  assert.equal(bf.lo.toFixed(1), "720.6");
  assert.equal(bf.hi.toFixed(1), "780.5");
  assert.equal(bf.verdict, "better");
  assert.equal(bf.text, "+750.5 (+720.6 to +780.5)");
  const capped = U.sweepRows(summary, 1, "b_cycle").find((r) => r.strategy === "D1 share" && r.policy === "P2 family cap");
  assert.equal(capped.text, "no prototype lot out");
  assert.equal(capped.verdict, "no clear effect");
});

test("the policies across shares, and today's baselines from the runs", () => {
  const lines = U.sweepLines(summary, "money");
  assert.equal(lines.length, 4);
  for (const l of lines) assert.equal(l.points.length, 4);
  const bf = lines.find((l) => l.policy === "P1 family B first");
  assert.deepEqual(bf.points.map((p) => p.share), [1, 2, 4, 8]);
  assert.ok(bf.points[2].mean > 0 && bf.points[3].mean < 0, "family B first flips between x4 and x8");
  const base = U.baselineFromRuns(runs);
  assert.equal(base[4].money.toFixed(2), "1210.63");
  assert.equal(base[8].a_wafers.toFixed(2), "561.43");
  assert.equal(base[2].b_cycle.toFixed(2), "97.47");
});

test("one scrubber drives two runs", () => {
  const c = U.pairedClock(4320, 2880);
  assert.deepEqual(c.at(0), [0, 0]);
  assert.deepEqual(c.at(1000), [1000, 1000]);
  assert.deepEqual(c.at(3000), [3000, 2880]);
  assert.deepEqual(c.at(9999), [4320, 2880]);
  assert.equal(c.end, 4320);
});

test("the page opens on a question ready to ask", () => {
  const withHelper = U.openingState({ model_connected: false, examples: [{ question: "Q1" }, { question: "Q2" }] }, []);
  assert.deepEqual(withHelper.examples, ["Q1", "Q2"]);
  assert.equal(withHelper.prompt, "Ask the fab a question");
  assert.equal(withHelper.explore, "or explore the floor");
  assert.equal(withHelper.canAsk, true);
  const without = U.openingState(null, [{ question: "Bundled" }]);
  assert.deepEqual(without.examples, ["Bundled"]);
  assert.equal(without.canAsk, false);
  assert.equal(without.explore, "or explore the floor");
});

// Plain wording on the page (the founder, 29 Oct): short sentences, no "X, not Y", the model named every time.
test("the page's words: no 'X, not Y' and no stacked labels", () => {
  const html = readFileSync(join(ROOT, "web", "index.html"), "utf8");
  const app = readFileSync(join(ROOT, "web", "app.js"), "utf8");
  const ask = readFileSync(join(ROOT, "web", "ask.js"), "utf8");
  for (const [name, src] of [["index.html", html], ["app.js", app], ["ask.js", ask]]) {
    for (const bad of [", not a real", "not a real one", "Real-fab effect", "(written by us, not by a model)", "Hover a step."])
      assert.ok(!src.includes(bad), `${name} still says "${bad}"`);
  }
  assert.match(html, /on the SMT2020 model/);
});
