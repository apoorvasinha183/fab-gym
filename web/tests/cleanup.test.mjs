// The floor page, cleaned up (docs/FLOOR-CLEANUP.md). Written before the code.
// On the SMT2020 model, a published research model of a wafer fab.
//
//     node --test web/tests/cleanup.test.mjs          (from the repo root)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const U = require(join(ROOT, "web", "ui.js"));
const G = require(join(ROOT, "web", "glossary.js"));
const html = readFileSync(join(ROOT, "web", "index.html"), "utf8");
const css = readFileSync(join(ROOT, "web", "floor-ui.css"), "utf8");
const app = readFileSync(join(ROOT, "web", "app.js"), "utf8");
const between = (s, a, b) => { const i = s.indexOf(a); return i < 0 ? "" : s.slice(i, s.indexOf(b, i)); };
const block = (id) => { const i = html.search(new RegExp(`<[a-z]+[^>]*id="${id}"`)); return i < 0 ? "" : html.slice(i); };

test("1. one place to ask, and one dock with five tabs holding the panels", () => {
  const outsideOpening = html.slice(0, html.indexOf('<section id="opening"')) + html.slice(html.indexOf("</section>", html.indexOf('<section id="opening"')));
  const boxes = outsideOpening.match(/<(input|textarea)\b[^>]*>/g).filter(t => !/type="(range|number|checkbox|search)"/.test(t) && !/id="ask-text"/.test(t));
  assert.deepEqual(boxes.map(t => t.match(/id="([^"]+)"/)[1]), ["cmd-q"], "the top bar is the only question box");
  assert.ok(!/id="ask-open"/.test(html) && !/id="ask-q"/.test(html));
  const dock = between(html, '<aside id="dock"', "</aside>");
  assert.ok(dock, "a dock");
  // the dock's five tabs became a title; the rail keeps Try a change and the glossary; Evidence holds the studies and
  // results (docs/SITE-CUTS.md)
  assert.match(dock, /id="dock-title"/);
  // the rail went (docs/FLOOR-REVIEW.md): Try a change sits in the top strip, the glossary by How a chip is made
  // the strip holds the suggestions' own div (docs/HOME-GATE.md), so it is read up to the map's buttons
  const strip = between(html, '<div id="topbar"', '<div id="maptools"'), help = between(html, '<div class="help-row"', "</div>");
  assert.match(strip, /data-tab="change"/, "change"); assert.match(help, /data-tab="glossary"/, "glossary");
  const dockAll = html.slice(html.indexOf('<aside id="dock"'), html.indexOf("<!-- /dock -->"));
  for (const id of ["pane-ask", "pane-change", "numbers", "results", "glossary", "run", "cmp-rows", "ask-result", "long-grid"])
    assert.match(dockAll, new RegExp(`id="${id}"`), `${id} inside the dock`);
  assert.ok(!/id="rail"/.test(html), "no rail: the tabs are in the top strip and the help row");
});

test("2. the bottom bar holds only time controls, labelled", () => {
  const footer = between(html, "<footer", "</footer>");
  for (const gone of ["numbers-open", "results-open", "glossary-open", "panel-open", "askbtn"]) assert.ok(!footer.includes(gone), gone);
  assert.match(footer, /id="fit"[^>]*>[^<]*Fit/);
  assert.match(footer, /Lots waiting/);
});

test("3. the floor key names every mark on the floor", () => {
  const key = between(html, 'id="key"', "</section>");
  for (const w of ["working", "idle", "changing setup", "maintenance", "broken down", "a lot", "urgent lot", "prototype lot", "+N", "Holding"])
    assert.ok(key.includes(w), `key lacks ${w}`);
});

test("4. each colour has one role", () => {
  const P = U.PALETTE;
  assert.equal(P.broken, P.worse, "red means broken or worse");
  const others = Object.entries(P).filter(([k, v]) => typeof v === "string" && !["broken", "worse"].includes(k));
  assert.ok(!others.some(([, v]) => v === P.broken), "red has no other role");
  assert.ok(!others.filter(([k]) => k !== "proto").some(([, v]) => v === P.proto), "pink is only prototype lots");
  for (const a of [0, 0.3, 1]) {
    const [r, g, b] = U.heatColor(a).match(/\d+(\.\d+)?/g).map(Number);
    assert.ok(r >= 240 && g >= 150 && b <= 120, `heat ${a} is amber: ${U.heatColor(a)}`);
  }
  assert.match(css, /button\.primary\s*\{[^}]*var\(--accent\)/);
  assert.ok(!/askbtn[^}]*--pink/.test(css.replace(/\/\*[\s\S]*?\*\//g, "")) || !html.includes("askbtn"), "no pink buttons");
});

test("5. detail grows with zoom: names, then chips, then queue belts", () => {
  let last = { names: false, chips: false, queues: false };
  const order = [];
  for (let s = 1; s <= 12; s += 0.25) {
    const d = U.zoomDetail(s);
    for (const k of ["names", "chips", "queues"]) {
      if (last[k]) assert.ok(d[k], `${k} stays on above its scale`);
      if (!last[k] && d[k]) order.push(k);
    }
    last = d;
  }
  assert.deepEqual(order, ["names", "chips", "queues"]);
  assert.deepEqual(U.zoomDetail(1), { names: false, chips: false, queues: false });
});

test("6. the views", () => {
  // the view bar went (docs/SITE-CUTS.md): Live is the floor; Follow one lot, and Show prototypes only while there are some
  assert.ok(!/<nav class="lenses"/.test(html));
  assert.match(html, /id="follow-open"/);
  assert.match(html, /id="proto-open"/);
});

test("7. the hover card stays inside the screen and off the cursor", () => {
  for (const [x, y] of [[10, 10], [1400, 10], [10, 800], [1400, 800], [700, 400]]) {
    const p = U.tipPlace(x, y, 260, 180, 1440, 812);
    assert.ok(p.x >= 8 && p.y >= 8 && p.x + 260 <= 1432 && p.y + 180 <= 804, `inside at ${x},${y}`);
    assert.ok(x < p.x || x > p.x + 260 || y < p.y || y > p.y + 180, `off the cursor at ${x},${y}`);
  }
});

test("8. a candidate is named by what it changes", () => {
  assert.equal(U.candidateName([["floor", "wing"]]), "A prototype wing");
  assert.equal(U.candidateName([["policy", "bfirst"]]), "Prototypes first");
  assert.equal(U.candidateName([["floor", "copies"], ["policy", "cap"]]), "Copies in the halls, capped at the door");
  assert.equal(U.candidateName([["rule", "fifo"]]), "First come, first served");
  assert.equal(U.candidateName([["cap", "2400"]]), "A cap of 2,400 lots inside");
  assert.equal(U.policyWord("P1 family B first"), "Prototypes first");
  assert.equal(U.floorWord("D3 copies"), "Copies in the halls");
});

test("9. the shares chart leaves out far points and lists them", () => {
  const r = U.clipRange([0.1, 0.2, -0.3, 0.5, 0.75, -0.15, -3.5]);
  assert.ok(r.lo > -3.5 && r.lo <= -0.3 && r.hi >= 0.75);
  assert.deepEqual(r.off, [-3.5]);
  assert.deepEqual(U.clipRange([1, 2, 3]).off, []);
});

test("10. money to three significant figures", () => {
  assert.equal(U.usd3(667248), "$667k");
  assert.equal(U.usd3(1067504), "$1.07M");
  assert.equal(U.usd3(24.3e6), "$24.3M");
  assert.equal(U.usd3(-3.05e6, true), "−$3.05M");
  assert.equal(U.usd3(8000), "$8,000");
  assert.equal(U.usd3(35210, true), "+$35.2k");
});

test("11. results filter by words and by kind", () => {
  const es = [{ kind: "sweep", title: "Two families", headline: "cap wins", question: "" }, { kind: "contest", title: "PPO contest", headline: "worse", question: "" }];
  assert.deepEqual(U.filterResults(es, "", "all").length, 2);
  assert.deepEqual(U.filterResults(es, "ppo", "all").map(e => e.kind), ["contest"]);
  assert.deepEqual(U.filterResults(es, "", "sweep").map(e => e.kind), ["sweep"]);
});

test("12. a glossary term's other names leave out codes", () => {
  const t = G.TERMS.find(x => x.term === "Prototypes first");
  assert.ok(!G.shownAliases(t).some(a => /^[A-Z]\d$/.test(a)));
  assert.ok(G.shownAliases(t).includes("family B first"));
});

test("13. one type family, nothing tiny, one name per thing", () => {
  const live = css.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/monospace|--mono/.test(live), "no monospace in the chrome's CSS");
  const tiny = [...live.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m => Number(m[1])).filter(v => v < 12);
  assert.deepEqual(tiny, [], "no text under 12 px");
  assert.ok(!/monospace/.test(app), "no monospace drawn by the page");
});

test("14. rest: reduced motion and a hidden page", () => {
  assert.match(app, /prefers-reduced-motion/);
  assert.match(app, /visibilitychange/);
});

test("15. a bottom sheet on narrow screens", () => {
  const m = css.match(/@media \(max-width: 900px\)\s*\{([\s\S]*?)\n\}/);
  assert.ok(m && /#dock/.test(m[1]), "the dock changes under 900 px");
});

test("no function in app.js is declared twice (a second declaration silently replaces the first)", () => {
  // the follow-one-lot drawing once reused journeyDraw, and How a chip is made opened empty (30 Oct)
  const names = [...app.matchAll(/^(?:async )?function ([A-Za-z0-9_$]+)/gm)].map(m => m[1]);
  const twice = [...new Set(names.filter((n, i) => names.indexOf(n) !== i))];
  assert.deepEqual(twice, []);
});
