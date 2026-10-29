// Tests for the stage explainer (docs/STAGES.md). Written before the code.
// On the SMT2020 model, a published model of a fab; not a real fab.
//
//     node --test web/tests/stages.test.mjs          (from the repo root)
//
// The cross-check against the raw SMT2020 route files skips when data/smt2020/hvlm is absent.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "web");
const require = createRequire(import.meta.url);
const S = require(join(WEB, "stages.js"));

const areaOf = Object.fromEntries(
  readFileSync(join(WEB, "data/areas.tsv"), "utf8").split("\n").filter(Boolean).map(l => l.split("\t")));

function shopRoutes() {
  const routes = {};
  let cur = null;
  for (const line of readFileSync(join(WEB, "data/shop.txt"), "utf8").split("\n")) {
    const p = line.split("\t");
    if (p[0] === "route") { cur = p[1]; routes[cur] = []; }
    else if (p[0] === "step" && cur) routes[cur].push(p[1]);
  }
  return routes;
}

const PROCESS = ["diff", "diel", "litho", "dry", "imp", "wet", "tf", "cmp", "chk"];

test("every area belongs to exactly one stage, and no stage names an unknown area", () => {
  const areas = new Set(Object.values(areaOf));
  const seen = new Map();
  for (const s of S.STAGES) for (const a of s.areas) {
    assert.ok(!seen.has(a), `${a} is in two stages`);
    seen.set(a, s.key);
  }
  assert.deepEqual([...seen.keys()].sort(), [...areas].sort());
  for (const a of areas) assert.equal(S.stageOfArea(a), seen.get(a));
  assert.deepEqual(S.STAGES.map(s => s.key).sort(), [...PROCESS, "hold"].sort());
});

test("the stages' halls are the floor's halls", () => {
  const app = readFileSync(join(WEB, "app.js"), "utf8");
  const block = app.slice(app.indexOf("const HALLS = ["), app.indexOf("];", app.indexOf("const HALLS = [")));
  const halls = [...block.matchAll(/\["([^"]+)", \[/g)].map(m => m[1]);
  assert.equal(halls.length, 10);
  assert.deepEqual(S.STAGES.map(s => s.hall).sort(), halls.sort());
});

test("steps per stage on each route, from the page's data", () => {
  const r = shopRoutes();
  const v3 = S.visits(r.part_3, areaOf), v4 = S.visits(r.part_4, areaOf);
  assert.deepEqual(v3, { diff: 17, diel: 31, litho: 73, dry: 76, imp: 31, wet: 152, tf: 29, cmp: 13, chk: 137, hold: 24 });
  assert.deepEqual(v4, { diff: 11, diel: 16, litho: 51, dry: 41, imp: 13, wet: 88, tf: 20, cmp: 9, chk: 84, hold: 10 });
  assert.equal(Object.values(v3).reduce((a, b) => a + b, 0), 583);
  assert.equal(Object.values(v4).reduce((a, b) => a + b, 0), 343);
});

test("the page's routes match the SMT2020 route files", { skip: !existsSync(join(ROOT, "data/smt2020/hvlm/route_3.txt")) }, () => {
  const r = shopRoutes();
  for (const n of ["3", "4"]) {
    const lines = readFileSync(join(ROOT, `data/smt2020/hvlm/route_${n}.txt`), "utf8").split("\n").filter(Boolean);
    const head = lines[0].split("\t");
    const fam = head.indexOf("STNFAM"), step = head.indexOf("STEP");
    const rows = lines.slice(1).map(l => l.split("\t")).sort((a, b) => +a[step] - +b[step]);
    assert.deepEqual(rows.map(x => x[fam]), r["part_" + n]);
  }
});

test("tool groups per stage", () => {
  const g = S.groupsPerStage(areaOf);
  assert.deepEqual(g, { diff: 10, diel: 10, litho: 11, dry: 21, imp: 9, wet: 14, tf: 11, cmp: 6, chk: 13, hold: 1 });
  assert.equal(Object.values(g).reduce((a, b) => a + b, 0), Object.keys(areaOf).length);
  // 105 tool groups and the holding group (spec change, 27 Oct)
  assert.equal(Object.keys(areaOf).length, 106);
  assert.equal(Object.values(g).reduce((a, b) => a + b, 0) - g.hold, 105);
});

test("the strip has one cell per step, in route order", () => {
  const steps = shopRoutes().part_3;
  const cells = S.strip(steps, areaOf);
  assert.equal(cells.length, 583);
  cells.forEach((c, i) => {
    assert.equal(c.i, i);
    assert.equal(c.group, steps[i]);
    assert.equal(c.area, areaOf[steps[i]]);
    assert.equal(c.stage, S.stageOfArea(c.area));
  });
  assert.deepEqual(cells.slice(0, 5).map(c => c.stage), ["diff", "wet", "chk", "chk", "diff"]);
});

test("the loop is eight process stages in order", () => {
  assert.deepEqual(S.LOOP, ["diff", "diel", "litho", "dry", "imp", "wet", "tf", "cmp"]);
  for (const k of S.LOOP) assert.ok(S.byKey(k));
});

test("each drawing is one self-contained SVG; holding has none", () => {
  for (const k of PROCESS) {
    const svg = S.crossSection(k, "t-" + k);
    assert.equal(typeof svg, "string", k);
    assert.match(svg, /^<svg [^>]*viewBox="0 0 240 150"/, k);
    assert.match(svg, /role="img"/, k);
    assert.match(svg, /aria-label="[^"]+"/, k);
    assert.match(svg, /<\/svg>$/, k);
    for (const tag of ["svg", "g", "text", "defs", "pattern", "marker", "linearGradient", "radialGradient"]) {
      const open = (svg.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length;
      const close = (svg.match(new RegExp(`</${tag}>`, "g")) || []).length;
      assert.equal(open, close, `${k}: <${tag}> opened ${open}, closed ${close}`);
    }
    const ids = new Set([...svg.matchAll(/ id="([^"]+)"/g)].map(m => m[1]));
    for (const m of svg.matchAll(/url\(#([^)]+)\)/g)) assert.ok(ids.has(m[1]), `${k}: url(#${m[1]}) is not defined in its SVG`);
    for (const id of ids) assert.ok(id.startsWith("t-" + k), `${k}: id ${id} lacks the prefix`);
  }
  assert.equal(S.crossSection("hold", "x"), null);
});

test("stage text: a what and a why each, no company named", () => {
  for (const s of S.STAGES) {
    for (const f of ["name", "what", "why", "note"]) {
      assert.equal(typeof s[f], "string", `${s.key}.${f}`);
      assert.ok(s[f].length > 0 && s[f].length <= 260, `${s.key}.${f} length ${s[f].length}`);
    }
    assert.ok(!/\d/.test(s.note), `${s.key}.note holds a number; numbers come from the data`);
  }
  const src = readFileSync(join(WEB, "stages.js"), "utf8");
  for (const w of ["TSMC", "Intel", "Samsung", "ASML"]) assert.ok(!src.includes(w), `stages.js names ${w}`);
});

test("the page carries the button, the panel and its wording", () => {
  const html = readFileSync(join(WEB, "index.html"), "utf8");
  const brand = html.slice(html.indexOf('<header class="card brand">'), html.indexOf("</header>"));
  assert.match(brand, /id="stages-open"/);
  assert.match(brand, /How a chip is made/);
  const panel = html.slice(html.indexOf('<section id="stages"'), html.indexOf("</section>", html.indexOf('<section id="stages"')));
  assert.ok(panel.length > 0, "no section#stages");
  assert.match(panel, /^<section id="stages"[^>]* hidden/);
  assert.match(panel, /role="dialog"/);
  assert.match(panel, /aria-labelledby="/);
  for (const id of ["stages-close", "stages-loop", "stages-detail", "stages-strip", "stages-hall"]) assert.match(panel, new RegExp(`id="${id}"`));
  for (const w of ["on the SMT2020 model", "No real fab's data", "not to scale"]) assert.ok(panel.includes(w), `panel lacks "${w}"`);
  assert.ok(html.indexOf('src="stages.js"') > 0 && html.indexOf('src="stages.js"') < html.indexOf('src="app.js"'));
});

test("the floor wires the panel, the fly to a hall and the hall card", () => {
  const app = readFileSync(join(WEB, "app.js"), "utf8");
  assert.match(app, /function flyToHall\(/);
  assert.match(app, /"Escape"/);
  const tip = app.slice(app.indexOf("function showTip("), app.indexOf("\n}\n", app.indexOf("function showTip(")));
  // the hover card names the group's stage; its drawing lives in How a chip is made (docs/FLOOR-CLEANUP.md, item 7)
  assert.match(tip, /FabStages\.byKey\(/);
  assert.match(tip, /st\.name/);
});
