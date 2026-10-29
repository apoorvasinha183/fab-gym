// From Sand to Chip (docs/CHIP-FILM.md): the film's scene list is the agreed script. Written before the code.
// The fab's part runs on the SMT2020 model; the rest is general knowledge, labelled so on screen.
//
//     node --test web/tests/film.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const F = require(join(ROOT, "web", "film", "script.js"));
const doc = readFileSync(join(ROOT, "docs", "CHIP-FILM.md"), "utf8");

test("the film's scenes are the script's: same titles, order and lengths", () => {
  const heads = [...doc.matchAll(/^## (\d+)\. (.+?) \((\d+:\d+), (\d+) s\)/gm)].map(m => ({ n: +m[1], title: m[2], t: m[3], d: +m[4] }));
  assert.equal(F.SCENES.length, heads.length);
  F.SCENES.forEach((s, i) => {
    assert.equal(s.title, heads[i].title, `scene ${i}`);
    assert.equal(s.d, heads[i].d, `${s.title}: length`);
  });
  assert.equal(F.total(), heads.reduce((a, h) => a + h.d, 0));
  // start times add up
  let t = 0;
  for (const s of F.SCENES) { assert.equal(F.startOf(s.key), t); t += s.d; }
});

test("every scene has its narration, a still moment inside it and its explainer marks", () => {
  for (const s of F.SCENES) {
    assert.ok(s.say && doc.includes(s.say), `${s.title}: narration from the script`);
    assert.ok(s.still >= 0 && s.still < s.d, `${s.title}: still time inside the scene`);
    assert.ok(Array.isArray(s.fx) && s.fx.length >= 1, `${s.title}: explainer marks`);
    assert.ok(["open", "before", "fab", "after"].includes(s.act));
  }
  const fab = F.SCENES.filter(s => s.act === "fab");
  assert.ok(fab.length >= 3 && fab.every(s => s.simulated), "the fab's scenes carry the simulated tag");
  assert.ok(F.SCENES.filter(s => s.act !== "fab").every(s => !s.simulated));
});

test("the music cue: Budding until the fab, crossfading into New Sunrise", () => {
  const into = F.startOf("arrive");
  assert.equal(F.MUSIC[0].file, "budding/the_budding_of_consciousness.wav");
  assert.equal(F.MUSIC[1].file, "new-sunrise/new_sunrise_V2.wav");
  assert.ok(F.MUSIC[1].start <= into && F.MUSIC[1].start >= into - 4, "the crossfade lands as the box enters the fab");
  assert.ok(F.MUSIC[0].end > F.MUSIC[1].start, "the two overlap for the crossfade");
});

test("the film page loads the vendored Three.js through an import map", () => {
  const html = readFileSync(join(ROOT, "web", "film", "index.html"), "utf8");
  assert.match(html, /"three":\s*"\.\.\/vendor\/three\/build\/three\.module\.min\.js"/);
  assert.match(html, /"three\/addons\/":\s*"\.\.\/vendor\/three\/examples\/jsm\/"/);
  assert.ok(existsSync(join(ROOT, "web", "vendor", "three", "LICENSE")));
  assert.match(html, /src="script\.js"/);
});

// Fades between scenes (the full cut): black at each cut, clear in the middle, the cold open fading in from black.
test("scenes fade through black at each cut and are clear in between", () => {
  for (const s of F.SCENES) {
    assert.ok(F.fade(s, 0) > 0.95, `${s.title}: black at its start`);
    assert.ok(F.fade(s, s.d) > 0.95, `${s.title}: black at its end`);
    assert.equal(F.fade(s, s.d / 2), 0, `${s.title}: clear in the middle`);
    assert.equal(F.fade(s, s.still), 0, `${s.title}: its still is clear`);
  }
  for (let x = 0; x <= 1; x += 0.05) assert.ok(F.fade(F.SCENES[3], x) >= F.fade(F.SCENES[3], x + 0.05) - 1e-9, "fading in never darkens");
});
