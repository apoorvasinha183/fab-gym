// Plain words on every screen (docs/PLAIN-WORDS.md). The founder: "Improve the language on the screens ... talk like
// a human". The first things a visitor reads (the landing, the floor's labels and panels, the editor, the Results
// cards' titles and headlines) use everyday words; the technical terms stay in the Glossary and the run details.
// Written before the code.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..");
const ROOT = join(WEB, "..");
const require = createRequire(import.meta.url);
const E = require(join(WEB, "editor-core.js"));
const B = require(join(WEB, "tools", "results-build.js"));
const text = (html) => html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, " ").replace(/<[^>]+>/g, " ").replace(/&[a-z]+;/g, " ").replace(/\s+/g, " ");
const index = text(readFileSync(join(WEB, "index.html"), "utf8"));
const editor = text(readFileSync(join(WEB, "editor.html"), "utf8"));
const JARGON = [/\bPPO\b/, /\bE2\b/, /Bonferroni/, /paired t\b/, /\bWIP\b/, /dispatch rule/i, /\bspine stretch/, /lot-hours/, /\bscenario\b/i, /muse-spark-1\.3-contributor/, /Defect holds/];

function clean(where, s) {
  for (const j of JARGON) assert.ok(!j.test(s), `${where} uses ${j}: …${(s.match(new RegExp(`.{0,40}${j.source}.{0,40}`, j.flags.replace("g", ""))) || [""])[0]}…`);
}

test("the floor page's labels and panels use everyday words", () => {
  const glossary = index.indexOf('Glossary'); // the Glossary's own entries are built by script, not in the HTML
  clean("index.html", index);
  assert.ok(glossary >= 0);
  for (const w of ["Run it and compare with today", "Which lot a free machine picks next", "Switch off a machine group", "Cap on lots inside", "Quality holds", "machines busy"])
    assert.ok(index.includes(w), `index.html says "${w}"`);
});

test("the editor speaks plainly, challenges included", () => {
  clean("editor.html", editor);
  for (const c of E.CHALLENGES) { clean(`challenge ${c.id}`, c.problem); clean(`challenge ${c.id}`, c.goal); }
  for (const w of ["Days a wafer takes", "Longest line", "Extra spend", "Machines", "Wafers in", "Wafers out", "Storage"])
    assert.ok(readFileSync(join(WEB, "editor.html"), "utf8").includes(w) || readFileSync(join(WEB, "editor.js"), "utf8").includes(w), `the editor says "${w}"`);
});

test("every Results card's title and headline reads plainly", () => {
  for (const e of B.buildResults(ROOT)) { clean(`results ${e.id} title`, e.title); clean(`results ${e.id} headline`, e.headline); }
});

test("the floor's own sentences built in script read plainly", () => {
  const app = readFileSync(join(WEB, "app.js"), "utf8");
  for (const s of ["Choose a dispatch rule", "WIP cap ${", "(WIP cap)", "Simulate and compare"]) assert.ok(!app.includes(s), `app.js still writes "${s}"`);
});
