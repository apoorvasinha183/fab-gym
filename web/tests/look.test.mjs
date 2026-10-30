// The floor takes the editor's look (docs/FLOOR-LOOK.md): one shared file of icons, area colours, names and moods
// (web/look.js) used by both pages; each tool group gets the editor's icon, label, mood badge and lots in line.
// Written before the code. On the SMT2020 model and a teaching fab of our own; not a real fab.
//
//     node --test web/tests/look.test.mjs          (from the repo root; needs `cargo build --release`)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, writeFileSync, mkdtempSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..");
const ROOT = join(WEB, "..");
const require = createRequire(import.meta.url);
const L = require(join(WEB, "look.js"));
const E = require(join(WEB, "editor-core.js"));
const TOOL_MOODS = ["work", "sleep", "tired", "full", "batch", "setup", "pm", "hurt", "physio", "hold"];

test("every area has an icon, a colour, names and cast art in every mood", () => {
  for (const a of E.AREAS) {
    assert.ok(L.ICONS[a], `icon for ${a}`);
    assert.match(L.FAM[a], /^#[0-9A-F]{6}$/i, `colour for ${a}`);
    assert.ok(L.AREA[a] && L.AREA[a].name && L.AREA[a].short && L.AREA[a].exercise, `names for ${a}`);
    for (const m of TOOL_MOODS) assert.ok(existsSync(join(WEB, "cast", a, `${m}.webp`)), `cast/${a}/${m}.webp`);
  }
  for (const k of ["rail", "split", "stocker", "entry", "exit", "select", "erase", "bolt"]) assert.ok(L.ICONS[k], k);
});

test("the ten tool moods, in the simulator's order, each with a name, colour and badge icon", () => {
  assert.deepEqual(L.TOOL_MOODS, TOOL_MOODS);
  for (const m of TOOL_MOODS) {
    assert.ok(L.MOOD[m].name, m);
    assert.match(L.MOOD[m].color, /^#[0-9A-F]{6}$/i, m);
    assert.ok(L.ICONS[L.MOOD[m].badge], `badge icon for ${m}`);
  }
});

test("every SMT2020 group maps to a cast area, except the stocker delay", { skip: !existsSync(join(WEB, "data", "areas.tsv")) }, () => {
  for (const line of readFileSync(join(WEB, "data", "areas.tsv"), "utf8").split("\n")) {
    const [g, area] = line.split("\t");
    if (!g) continue;
    if (area === "Delay_32") assert.equal(L.areaOf(area), null, g);
    else assert.ok(E.AREAS.includes(L.areaOf(area)), `${g} (${area})`);
  }
  assert.equal(L.areaOf("Planar"), "cmp");
});

test("a group's label is its area's short name and its number", () => {
  assert.equal(L.label("DE_BE_11", "dry"), "Dry etch BE 11");
  assert.equal(L.label("Planar_FE_79", "cmp"), "CMP FE 79");
  assert.equal(L.label("Litho_T", "litho"), "Litho");
});

test("a group's mood on the floor is the editor's: the commonest of its tools, a tie to the more serious", () => {
  const m = { tool_moods: TOOL_MOODS, groups: ["A", "A", "B", "B"], frames: [{ tools: [0, 2, 1, 1] }, { tools: [7, 7, 0, 8] }] };
  for (let f = 0; f < 2; f++) for (const g of ["A", "B"]) assert.equal(L.groupMood(m, f, g), E.blockMood(m, f, g), `frame ${f} group ${g}`);
  assert.equal(L.groupMood(m, 0, "A"), "tired");
  assert.equal(L.groupMood(m, 1, "A"), "hurt");
  assert.equal(L.groupMood(m, 1, "B"), "physio", "work and physio tie; physio is the more serious");
});

test("both pages load the shared look, and neither keeps its own icon table", () => {
  for (const page of ["index.html", "editor.html"]) {
    const h = readFileSync(join(WEB, page), "utf8");
    assert.ok(h.includes('<script src="look.js"></script>'), page);
  }
  for (const js of ["editor.js", "app.js"]) {
    const t = readFileSync(join(WEB, js), "utf8");
    assert.ok(!/const IC = \{/.test(t), `${js} keeps no icon table of its own`);
    assert.ok(t.includes("FabLook."), `${js} uses the shared look`);
  }
});

test("the floor's moods come from the browser build's moods export", () => {
  const app = readFileSync(join(WEB, "app.js"), "utf8");
  assert.ok(app.includes("fg_moods("), "app.js asks the simulator for moods");
  assert.ok(app.includes("FabLook.groupMood("), "app.js draws a group's mood the editor's way");
});

test("the command line's moods are unchanged by moving them into the library", { skip: !existsSync(join(ROOT, "target", "release", "fabsim")) }, () => {
  const d = mkdtempSync(join(tmpdir(), "look-"));
  const shop = join(d, "s.txt");
  writeFileSync(shop, E.TEACHING_SHOP);
  const r = spawnSync(join(ROOT, "target", "release", "fabsim"), ["moods", shop, "1", "--until", "720", "--every", "60"], { maxBuffer: 1 << 26 });
  assert.equal(r.status, 0, r.stderr.toString());
  const m = JSON.parse(r.stdout);
  for (const k of ["about", "tool_moods", "lot_moods", "tools", "groups", "stretches", "group_names", "score", "frames"]) assert.ok(k in m, k);
  assert.equal(m.frames.length, 13);
});
