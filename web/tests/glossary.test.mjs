// The Glossary tab: every technical word used or assumed, in plain English, as a wiki (the founder, 29 Oct). Written
// before the code. Each entry: plain meaning, how this fab uses it, where it comes from, an example, see also.
// On the SMT2020 model, a published research model of a wafer fab.
//
//     node --test web/tests/glossary.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const G = require(join(ROOT, "web", "glossary.js"));

const REQUIRED = [
  "SMT2020", "Wafer", "Lot", "Route", "Step", "Tool", "Tool group", "Area", "Hall", "Lithography", "Etch", "Polishing (CMP)",
  "Checks (metrology)", "Track (overhead track)", "Dispatch rule", "Today's rule", "Hot lot", "Volume wafers (family A)",
  "Prototype lots (family B)", "Setup change", "Batch", "Breakdown", "Repair time", "Rework", "Defect hold", "Queue-time limit",
  "Cycle time", "WIP", "WIP cap", "Move", "Seed", "Paired seeds", "Warm-up", "Window", "95% interval", "Bonferroni",
  "Verdict", "Held-out seeds", "Operating profit", "Operating cash", "Capital", "Depreciation", "Payback", "Net present value",
  "Qualification", "Prototype wing", "Copies in the halls", "Family cap", "Prototypes first", "Reservation", "Reinforcement learning",
  "PPO", "Episode", "Reward", "E2 (evolutionary search)", "Genetic programming", "Ant colony search", "Assumed", "Simulator",
];
const TOPICS = ["The fab", "Lots and tools", "Rules and policies", "Money", "Statistics", "Learning", "This page"];

test("every entry has its plain meaning, how this fab uses it, where it comes from, an example and see also", () => {
  const names = new Set(G.TERMS.map(t => t.term));
  assert.equal(names.size, G.TERMS.length, "no term twice");
  for (const t of G.TERMS) {
    assert.ok(TOPICS.includes(t.topic), `${t.term}: topic ${t.topic}`);
    assert.ok(t.meaning && t.meaning.length <= 320, `${t.term}: meaning`);
    assert.ok(t.here && t.here.length > 10, `${t.term}: how this fab uses it`);
    assert.ok(["published", "assumed", "choice", "standard"].includes(t.source.kind), `${t.term}: source kind`);
    assert.ok(t.source.text, `${t.term}: source text`);
    if (t.source.kind === "assumed") assert.ok(t.source.range, `${t.term}: an assumed value says the range tried`);
    assert.ok(t.example, `${t.term}: example`);
    assert.ok(Array.isArray(t.see) && t.see.length >= 1, `${t.term}: see also`);
    for (const s of t.see) assert.ok(names.has(s), `${t.term}: see also ${s} is not a term`);
    for (const f of ["meaning", "here", "example"]) assert.ok(!/, not (a|an|the) /.test(t[f]), `${t.term}: "X, not Y" in ${f}`);
  }
  for (const r of REQUIRED) assert.ok(names.has(r), `missing ${r}`);
});

test("search finds a term by its name or another name for it, A to Z", () => {
  assert.equal(G.find("cmp")[0].term, "Polishing (CMP)");
  assert.ok(G.find("npv").some(t => t.term === "Net present value"));
  assert.ok(G.find("family b").some(t => t.term === "Prototype lots (family B)"));
  const all = G.find("");
  assert.equal(all.length, G.TERMS.length);
  for (let i = 1; i < all.length; i++) assert.ok(all[i - 1].term.localeCompare(all[i].term, "en", { sensitivity: "base" }) <= 0);
});

test("words on the page link to their article: the longest match, once each", () => {
  const segs = G.linkify("The WIP cap wins with a 95% interval; WIP falls and the WIP cap holds.");
  const linked = segs.filter(s => s.term).map(s => [s.text, s.term]);
  assert.deepEqual(linked, [["WIP cap", "WIP cap"], ["95% interval", "95% interval"], ["WIP", "WIP"]]);
  assert.equal(segs.map(s => s.text).join(""), "The WIP cap wins with a 95% interval; WIP falls and the WIP cap holds.");
  // whole words only
  assert.ok(!G.linkify("Lottery").some(s => s.term));
});

test("the page has the Glossary tab: a search box, the index and the article", () => {
  const html = readFileSync(join(ROOT, "web", "index.html"), "utf8");
  for (const id of ["glossary", "gl-search", "gl-index", "gl-article"]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /data-tab="glossary"/, "opened from the dock's rail and tabs (docs/FLOOR-CLEANUP.md)");
  assert.ok(html.indexOf('src="glossary.js"') > 0 && html.indexOf('src="glossary.js"') < html.indexOf('src="app.js"'));
});
