// Build: gears on the map, find a control, your changes and the glossary, part 5 (docs/BUILD-CONTROLS.md). Written
// before the code. On a teaching fab of our own, built from the SMT2020 testbed's shapes; not a real fab.
//
//     node --test web/tests/buildfind.test.mjs   (needs Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync } from "node:fs";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { rmSync as rmProfile } from "node:fs";
// headless Chrome profiles: made per browser, removed when this file's tests end, so test runs cannot fill the disk
const PROFILES = [];
const profileDir = (prefix) => { const d = mkdtempSync(join(tmpdir(), prefix)); PROFILES.push(d); return d; };
process.on("exit", () => { for (const d of PROFILES) { try { rmProfile(d, { recursive: true, force: true }); } catch { /* already gone */ } } });

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const E = require(join(HERE, "..", "editor-core.js"));
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");

const G = require(join(HERE, "..", "glossary.js"));
// ---------------------------------------------------------------- the page in headless Chrome, with its own helper

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function helper() {
  const port = 8800 + Math.floor(Math.random() * 400);
  const p = spawn(PY, ["-m", "agent.helper", "--no-model", "--port", String(port), "--runs", profileDir("bk-runs-")], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/editor.html`)).ok) return { port, close: () => p.kill() }; } catch { /* not up yet */ }
    await sleep(100);
  }
  p.kill();
  throw new Error("the helper did not start");
}

async function chrome() {
  const port = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${port}`, "--window-size=1440,1000", "--hide-scrollbars",
    `--user-data-dir=${profileDir("bk-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) {
    try { const l = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up yet */ }
    if (!ws) await sleep(200);
  }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
  // modifiers: 2 Ctrl, 8 Shift
  const key = async (k, code, modifiers = 0) => {
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code, modifiers, windowsVirtualKeyCode: k.toUpperCase().charCodeAt(0) });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, modifiers });
  };
  return { send, ev, mouse, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); } };
}

async function openEditor() {
  const h = await helper();
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Page.navigate", { url: `http://127.0.0.1:${h.port}/editor.html` });
  for (let i = 0; i < 200; i++) {
    await sleep(50);
    if (await b.ev("!!(window.FabEditorPage && window.FabEditorPage.runs && window.FabEditorPage.runs() >= 1)")) break;
  }
  const close = () => { b.close(); h.close(); };
  return { b, close };
}

const page = (b, expr) => b.ev(`(() => { const F = window.FabEditorPage; return ${expr}; })()`);



const until = async (b, cond, ms = 15000) => { for (let t = 0; t < ms; t += 100) { if (await b.ev(cond)) return true; await sleep(100); } return false; };
const toTab = async (b, k) => { const r0 = await page(b, "F.runs()"); await b.ev(`document.querySelectorAll("#chtabs button")[${k}].click(), 1`); await until(b, `FabEditorPage.runs() > ${r0}`); await sleep(300); };

const openTab = async (b, t) => { await b.ev(`document.querySelector('#ctl-tabs [data-tab="${t}"]').click(), 1`); await sleep(150); };
const setSel = async (b, id, v) => { await b.ev(`(() => { const s = document.getElementById(${JSON.stringify(id)}); s.value = ${JSON.stringify(v)}; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(200); };
const keyDown = (b, key, code) => b.send("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0) });
const keyUp = (b, key, code) => b.send("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0) });
const find = async (b, q) => { await b.ev(`(() => { const i = document.getElementById("ctl-find"); i.focus(); i.value = ${JSON.stringify(q)}; i.dispatchEvent(new Event("input")); return 1; })()`); await sleep(150); return b.ev(`[...document.querySelectorAll("#ctl-found [data-find]")].map(e => e.textContent)`); };
const polishing = (b) => page(b, `F.blocks().find(z => z.kind === "group" && z.area === "cmp")`);
const changes = (b) => b.ev(`[...document.querySelectorAll("#changes li[data-chg]")].map(e => e.textContent)`);

test("BG1 G shows a gear with its number on every machine block and breaking track piece; the Controls button too", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    assert.equal((await page(b, "F.gears()")).length, 0, "no gears at first");
    const groups = (await page(b, `F.blocks().filter(z => z.kind === "group")`)).length, breaks = (await page(b, "F.breaks()")).length;
    assert.ok(breaks >= 1, "challenge 1 has a breaking track piece");
    await keyDown(b, "g", "KeyG"); await sleep(150);
    let gs = await page(b, "F.gears()");
    assert.equal(gs.filter((g) => g.kind === "group").length, groups, "a gear on every machine block");
    assert.equal(gs.filter((g) => g.kind === "rail").length, breaks, "a gear on every breaking track piece");
    for (const g of gs) assert.equal(g.n, 3, `${g.kind}: three controls`);
    assert.ok(gs.filter((g) => g.kind === "rail").every((g) => g.lit), "challenge 1's lever, the broken track, is lit");
    await keyUp(b, "g", "KeyG"); await sleep(150);
    assert.equal((await page(b, "F.gears()")).length, 0, "letting go hides them");
    await b.ev(`document.getElementById("gears").click(), 1`); await sleep(150);
    assert.equal((await page(b, "F.gears()")).length, groups + breaks, "the Controls button shows them");
    await b.ev(`document.getElementById("gears").click(), 1`); await sleep(150);
    assert.equal((await page(b, "F.gears()")).length, 0, "and hides them");
    await toTab(b, 1);
    await keyDown(b, "g", "KeyG"); await sleep(150);
    gs = await page(b, "F.gears()");
    const blocks = await page(b, "F.blocks()");
    for (const g of gs.filter((x) => x.kind === "group")) {
      const bl = blocks.find((z) => z.id === g.id);
      assert.equal(g.lit, bl.area === "cmp", `challenge 2: ${bl.group} lit only if polishing`);
    }
    await keyUp(b, "g", "KeyG");
  } finally { close(); }
});

test("BG2 a click on a machine's gear selects that block and opens Selected", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await openTab(b, "fab");
    await b.ev(`document.getElementById("gears").click(), 1`); await sleep(150);
    const g = (await page(b, "F.gears()")).find((x) => x.kind === "group");
    await b.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: g.x, y: g.y });
    await b.send("Input.dispatchMouseEvent", { type: "mousePressed", x: g.x, y: g.y, button: "left", clickCount: 1 });
    await b.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: g.x, y: g.y, button: "left", clickCount: 1 });
    await sleep(200);
    assert.deepEqual(await page(b, "F.selected()"), { id: g.id }, "the block is selected");
    assert.equal(await b.ev(`document.getElementById("insp").hidden`), false, "Selected is open");
  } finally { close(); }
});

test("BK1 Find a control: / reaches it; cap, spare, polish and rule find their controls and light them", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await keyDown(b, "/", "Slash"); await keyUp(b, "/", "Slash"); await sleep(100);
    assert.equal(await b.ev("document.activeElement && document.activeElement.id"), "ctl-find", "/ puts the cursor in the box");
    let hits = await find(b, "cap");
    assert.match(hits[0] || "", /Cap on lots inside/);
    await b.ev(`document.getElementById("ctl-find").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })), 1`); await sleep(250);
    assert.equal(await b.ev(`document.getElementById("ctl-fab").hidden`), false, "Whole fab opens");
    assert.equal(await b.ev(`!!document.querySelector('#ctl-fab .ctlrow.lit[data-ctl="cap"]')`), true, "the cap is lit");
    hits = await find(b, "spare");
    assert.ok(hits.some((h) => /When it breaks/.test(h)), `spare: ${hits}`);
    hits = await find(b, "polish");
    assert.ok(hits.length && hits.every((h) => /Polishing/.test(h)), `polish: ${hits}`);
    await b.ev(`document.querySelector("#ctl-found [data-find]").click(), 1`); await sleep(250);
    const sel = await page(b, "F.selected()"), pb = (await page(b, "F.blocks()")).find((z) => sel && z.id === sel.id);
    assert.ok(pb && pb.area === "cmp", "a polishing block is selected");
    assert.equal(await b.ev(`!!document.querySelector("#insp .ctlrow.lit")`), true, "its control is lit");
    hits = await find(b, "rule");
    assert.ok(hits.some((h) => /Dispatch rule/.test(h)), `rule: ${hits}`);
    await find(b, "zzqx");
    assert.match(await b.ev(`document.getElementById("ctl-found").textContent`), /No control matches/);
  } finally { close(); }
});

/** One more polishing machine, a cap of 400 and First come, first served, in challenge 1. */
async function threeChanges(b) {
  const pb = await polishing(b);
  await page(b, `F.select(${pb.id})`); await sleep(150);
  await b.ev(`document.getElementById("up").click(), 1`); await sleep(150);
  await openTab(b, "fab");
  await setSel(b, "ctl-fab-cap", "400");
  await setSel(b, "ctl-fab-rule", "fifo");
  return pb;
}

test("BY1 BY2 Your changes lists each change with its cost, and the changed controls carry a dot", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    assert.deepEqual(await changes(b), [], "none at the start");
    const spend0 = await page(b, "F.spend()");
    const pb = await threeChanges(b);
    const list = await changes(b);
    assert.equal(list.length, 3, list.join(" | "));
    assert.ok(list.some((t) => /\+1 Polishing \(CMP\) machine/.test(t) && /\$5M/.test(t)), list.join(" | "));
    assert.ok(list.some((t) => /Cap on lots inside: 400/.test(t)), list.join(" | "));
    assert.ok(list.some((t) => /Dispatch rule: First come, first served/.test(t)), list.join(" | "));
    const extra = (await page(b, "F.spend()")) - spend0;
    assert.equal(extra, 5e6, "Extra spend is one polishing machine");
    assert.match(await b.ev(`document.querySelector("#changes summary").textContent`), /3[^]*\$5M/, "the line says how many and what they cost");
    // dots
    const moved = (k) => b.ev(`!!document.querySelector('#ctl-fab .ctlrow.moved[data-ctl="${k}"]')`);
    assert.equal(await moved("cap"), true); assert.equal(await moved("rule"), true);
    assert.equal(await moved("cars"), false); assert.equal(await moved("demand"), false);
    await page(b, `F.select(${pb.id})`); await sleep(150);
    assert.equal(await b.ev(`!!document.querySelector('#insp .ctlrow.moved[data-ctl="count"]')`), true, "the machines row");
    assert.equal(await b.ev(`!!document.querySelector('#insp .ctlrow.moved[data-ctl="fail"]')`), false, "breakdowns are as they started");
  } finally { close(); }
});

test("BY3 an undo in the list puts that one change back; the undo button takes it back", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    const pb = await threeChanges(b);
    const total0 = pb.count;
    const undoOf = (re) => b.ev(`(() => { const li = [...document.querySelectorAll("#changes li[data-chg]")].find(e => ${re}.test(e.textContent)); if (!li) return 0; li.querySelector("[data-undo]").click(); return 1; })()`);
    assert.equal(await undoOf("/Cap on lots inside/"), 1);
    await sleep(200);
    assert.doesNotMatch(await page(b, "F.fab()"), /^cap\t/m, "the cap is gone");
    assert.equal((await changes(b)).length, 2, "the other two stay");
    await b.ev(`document.getElementById("undo").click(), 1`); await sleep(200);
    assert.match(await page(b, "F.fab()"), /^cap\t400$/m, "the undo button brings the cap back");
    assert.equal(await undoOf("/Polishing/"), 1);
    await sleep(200);
    const now = (await page(b, "F.blocks()")).filter((z) => z.kind === "group" && z.group === pb.group).reduce((a, z) => a + z.count, 0);
    assert.equal(now, total0, "the polishing machines are back at their starting count");
    assert.equal((await changes(b)).length, 2, "the cap and the rule remain");
  } finally { close(); }
});

test("BL1 every control links to an entry that exists, and the card shows its picture, plain line, figure and the Floor", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    const terms = new Set(G.TERMS.map((t) => t.term));
    const rows = async (panel) => b.ev(`[...document.querySelectorAll("#${panel} .ctlrow")].map(r => { const q = r.querySelector(".gl-q"); return { k: r.dataset.ctl, term: q ? q.dataset.term : null }; })`);
    const check = (list, where) => { assert.ok(list.length, `${where}: controls`); for (const r of list) assert.ok(r.term && terms.has(r.term), `${where} ${r.k}: links to ${r.term}`); };
    const pb = await polishing(b);
    await page(b, `F.select(${pb.id})`); await sleep(150);
    check(await rows("insp"), "a machine");
    const rail = (await page(b, "F.breaks()"))[0];
    await page(b, `F.selectRail(${JSON.stringify(rail)})`); await sleep(150);
    check(await rows("insp"), "a track piece");
    await openTab(b, "fab"); check(await rows("ctl-fab"), "Whole fab");
    await openTab(b, "all"); check(await rows("ctl-all"), "All controls");
    await openTab(b, "fab");
    await b.ev(`document.querySelector('#ctl-fab .ctlrow[data-ctl="cap"] .gl-q').click(), 1`); await sleep(200);
    const t = G.TERMS.find((x) => x.term === "WIP cap");
    const card = await b.ev(`(() => { const c = document.getElementById("glcard"); return c && !c.hidden ? { img: (c.querySelector("img") || {}).getAttribute ? c.querySelector("img").getAttribute("src") : "", plain: (c.querySelector(".gl-plain") || {}).textContent, fig: !!c.querySelector("figure svg"), href: (c.querySelector("a[href*='index.html']") || {}).getAttribute ? c.querySelector("a[href*='index.html']").getAttribute("href") : "" } : null; })()`);
    assert.ok(card, "the card opens");
    assert.equal(card.img, t.picture);
    assert.equal(card.plain, t.plain);
    assert.equal(card.fig, true, "WIP cap has a figure");
    assert.match(card.href, /index\.html\?term=WIP%20cap/);
  } finally { close(); }
});

test("BL2 the Floor opened at ?term=WIP%20cap opens its glossary at WIP cap", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const h = await helper();
  const b = await chrome();
  try {
    await b.send("Page.enable");
    await b.send("Page.navigate", { url: `http://127.0.0.1:${h.port}/index.html?term=WIP%20cap` });
    assert.ok(await until(b, `!!(document.querySelector("#gl-article h3") && document.querySelector("#gl-article h3").textContent === "WIP cap")`, 30000), "the article is WIP cap");
  } finally { b.close(); h.close(); }
});

test("BL3 the four new entries have every part and their cast pictures", () => {
  const want = { "Car (vehicle)": "cast/lots/ride.webp", "Load port": "cast/cmp/full.webp", "Storage (stocker)": "cast/lots/bench.webp", "Demand (release rate)": "cast/lots/line.webp" };
  for (const [term, pic] of Object.entries(want)) {
    const t = G.TERMS.find((x) => x.term === term);
    assert.ok(t, `${term}: an entry`);
    assert.ok(G.TERMS.some((x) => !(x.term in want) && x.topic === t.topic), `${term}: a topic the glossary already has (${t.topic})`);
    for (const k of ["meaning", "here", "example", "plain"]) assert.ok(typeof t[k] === "string" && t[k].length > 10, `${term}: ${k}`);
    assert.ok(t.source && t.source.kind && t.source.text, `${term}: where it comes from`);
    assert.ok(Array.isArray(t.see) && t.see.length, `${term}: see also`);
    assert.equal(t.picture, pic);
  }
});

test("BL4 the page does not scroll with changes listed and a card open", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await threeChanges(b);
    await b.ev(`(() => { const d = document.getElementById("changes"); d.open = true; return 1; })()`);
    await b.ev(`document.querySelector('#ctl-fab .ctlrow[data-ctl="cap"] .gl-q').click(), 1`); await sleep(200);
    for (const [w, hh] of [[1440, 900], [1440, 760], [1280, 720]]) {
      await b.send("Emulation.setDeviceMetricsOverride", { width: w, height: hh, deviceScaleFactor: 1, mobile: false });
      await sleep(400);
      const over = await b.ev(`Math.max(document.documentElement.scrollHeight - innerHeight, document.documentElement.scrollWidth - innerWidth)`);
      assert.ok(over <= 0, `${w} x ${hh}: the page scrolls ${over} px`);
    }
  } finally { close(); }
});
