// The way in (docs/FRONT-DOOR.md): the landing leads
// with the gym and two doors, one top bar joins the floor and the editor, and SMT2020 is called a testbed (a published
// set of a fab's tool groups, routes and times), never a fab. Written before the code.
//
//     node --test web/tests/frontdoor.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = join(HERE, "..");
const ROOT = join(WEB, "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");
const index = read("web/index.html"), editor = read("web/editor.html"), app = read("web/app.js");

test("the landing leads with the gym, by the chosen words", () => {
  assert.match(index, /<h1 id="open-title">A gym for wafer fabs\.<\/h1>/);
  // the models named by their jobs since docs/HOME-REVIEW.md (item 5)
  assert.ok(index.includes("Build a fab, watch every machine work out, and fix what hurts. Muse Spark sets up the what-ifs you ask, Muse Wonder plays the challenges against you, the simulator scores every change, and a person signs off."));
  assert.ok(index.includes("Fab Gym · from the SMT2020 testbed"));
});

test("two doors: play a challenge opens the editor, watch the whole fab opens the Floor", () => {
  const doors = index.slice(index.indexOf('id="open-doors"'), index.indexOf("</section>", index.indexOf('id="open-doors"')));
  assert.ok(doors.length > 0, "a doors block on the landing");
  // Play a challenge became a door of four challenge links and a Start button (docs/HOME-REVIEW.md)
  assert.match(doors, /Play a challenge[\s\S]*<a [^>]*href="editor\.html\?ch=1"[^>]*>Start challenge 1/);
  // Ask the fab left the gate for the Floor's ask bar (docs/HOME-GATE.md)
  assert.match(doors, /Watch the whole fab at work[\s\S]*href="#floor"/);
  assert.ok(!/Ask the fab/.test(doors) && !/id="open-q"/.test(doors), "no question box at the gate");
  assert.ok(!/id="open-explore"/.test(index), "or explore the floor went: the nav's Floor does it (docs/SITE-CUTS.md)");
});

function navOf(html) {
  const m = html.match(/<nav class="topnav"[^>]*>([\s\S]*?)<\/nav>/);
  assert.ok(m, "a top bar");
  return [...m[1].matchAll(/<a [^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>/g)].map((x) => [x[2].trim(), x[1]]);
}

test("one top bar on both pages: Home, Floor, Build, Evidence, Runs (Ask became the bar, docs/SITE-CUTS.md; Runs, docs/RUNS.md)", () => {
  assert.deepEqual(navOf(index).map((x) => x[0]), ["Home", "Floor", "Build", "Evidence", "Runs"]);
  assert.deepEqual(navOf(editor), [["Home", "index.html"], ["Floor", "index.html#floor"], ["Build", "editor.html"], ["Evidence", "index.html#evidence"], ["Runs", "runs.html"]]);
  assert.equal(Object.fromEntries(navOf(index)).Build, "editor.html");
  assert.match(editor, /<a [^>]*href="editor\.html"[^>]*aria-current="page"/, "the editor marks Build as the page you are on");
});

test("the floor page opens where the link says: #floor on the floor, #ask with the ask panel", () => {
  assert.match(app, /location\.hash/);
  assert.match(app, /hashchange/);
  assert.match(app, /["']#floor["']|["']floor["']/);
  assert.match(app, /["']#ask["']|["']ask["']/);
});

test("the editor's scores sit in the challenge band, so the running floor shows without scrolling", () => {
  const band = editor.slice(editor.indexOf('class="banner"'), editor.indexOf("</section>", editor.indexOf('class="banner"')));
  assert.match(band, /id="score"/);
});

test("SMT2020 is a testbed everywhere a visitor or the agent reads it", () => {
  const files = [
    ...readdirSync(WEB).filter((f) => /\.(html|js)$/.test(f)).map((f) => `web/${f}`),
    "README.md",
    ...readdirSync(join(ROOT, "agent")).filter((f) => f.endsWith(".py")).map((f) => `agent/${f}`),
  ];
  for (const f of files) {
    const t = read(f);
    assert.ok(!/SMT2020 model/.test(t), `${f} still says "SMT2020 model"`);
    assert.ok(!/(research )?model of a (wafer )?fab/.test(t), `${f} still calls SMT2020 a model of a fab`);
  }
  for (const f of ["web/index.html", "web/editor.html", "README.md"]) assert.ok(read(f).includes("SMT2020 testbed"), f);
});
