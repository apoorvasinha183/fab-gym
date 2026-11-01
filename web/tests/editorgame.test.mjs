// The editor as a game (docs/EDITOR-GAME.md): a look made for drawing, the jam on the map, the first move, the change
// where you made it. Written before the code. On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/editorgame.test.mjs   (from the repo root; G7 to G13 need Google Chrome and the .venv)

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

// ---------------------------------------------------------------- in Node

test("G1 trouble: badges only for trouble", () => {
  const k = (m, q) => (E.trouble(m, q) || {}).kind || null;
  assert.equal(k("work", 0), null);
  assert.equal(k("work", 3), null);
  assert.equal(k("work", 4), "line");
  assert.equal(k("hurt", 0), "broken");
  assert.equal(k("physio", 2), "broken");
  assert.equal(k("tired", 5), "gassed");
  assert.equal(k("full", 0), "blocked");
  assert.equal(k("hold", 0), "held");
  assert.equal(k("pm", 0), "planned");
  assert.equal(k("setup", 1), "planned");
  assert.equal(k("pm", 6), "line");
  assert.equal(k("sleep", 0), null);
  assert.equal(k("batch", 2), null);
  for (const m of ["hurt", "tired", "full", "hold", "pm"]) assert.match(E.trouble(m, 0).color, /^#[0-9A-F]{6}$/i);
});

test("G2 pile: rows of six, up to three rows, a mark for more", () => {
  assert.deepEqual(E.pile(0), { shown: 0, more: false });
  assert.deepEqual(E.pile(17), { shown: 17, more: false });
  assert.deepEqual(E.pile(18), { shown: 18, more: false });
  assert.deepEqual(E.pile(30), { shown: 17, more: true });
});

test("G3 jamStyle: calm, amber, red, wider as it gets worse", () => {
  assert.deepEqual(E.jamStyle(0), { kind: "calm", width: 1 });
  assert.deepEqual(E.jamStyle(0.5), { kind: "amber", width: 1.5 });
  assert.deepEqual(E.jamStyle(2), { kind: "red", width: 2 });
});

test("G4 advise: the break, else the longest line, else met", () => {
  const brk = E.advise({ brokenJam: true, worst: { name: "Lithography", queue: 9 }, met: false });
  assert.match(brk, /break/i);
  const line = E.advise({ brokenJam: false, worst: { name: "Polishing", queue: 12 }, met: false });
  assert.match(line, /Polishing/); assert.match(line, /12 lots/);
  assert.match(E.advise({ brokenJam: false, worst: null, met: true }), /met/i);
});

test("G5 floatText: up, down, the same", () => {
  assert.equal(E.floatText(650, 662), "+12 wafers a day");
  assert.equal(E.floatText(650, 645), "−5 wafers a day");
  assert.equal(E.floatText(650, 650), "same output");
  assert.equal(E.floatText(null, 650), null);
});

test("G6 every challenge has a spot and a tool list with Select", () => {
  for (const c of E.CHALLENGES) {
    assert.ok(c.spot && (c.spot.rail || c.spot.group), `${c.id}: a spot`);
    assert.ok(Array.isArray(c.tools) && c.tools.includes("select"), `${c.id}: tools with select`);
  }
});

// ---------------------------------------------------------------- headless Chrome, a helper of its own

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openEditor() {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("game-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const key = async (k, code, type) => {
    if (type) return send("Input.dispatchKeyEvent", { type, key: k, code });
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code }); await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code });
  };
  await send("Page.enable");
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/editor.html` });
  for (let i = 0; i < 200; i++) { await sleep(50); if (await ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
  return { ev, send, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}
const until = async (p, expr, ms) => { const t = Date.now(); while (Date.now() - t < ms) { if (await p.ev(expr)) return true; await sleep(30); } return false; };
const tab = async (p, k) => { const r0 = await p.ev("FabEditorPage.runs()"); await p.ev(`[...document.querySelectorAll("#tabs button, .tabs button, button.tab")][${k}].click()`); await until(p, `FabEditorPage.runs() > ${r0}`, 5000); await sleep(200); };
// the palette's tools (docs/BUILD-CONTROLS.md lists the machines beside them, with data-kind)
const palette = (p) => p.ev(`[...document.querySelectorAll("#pal button[data-t]")].map((b) => b.dataset.t)`);

test("G7 the hint line follows the tool, and the lit cell follows the pointer", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await p.key("b", "KeyB");
    assert.match(await p.ev(`document.getElementById("hint").textContent`), /track/i);
    await p.key("e", "KeyE");
    assert.match(await p.ev(`document.getElementById("hint").textContent`), /erase|remove/i);
    const [x, y] = JSON.parse(await p.ev("JSON.stringify(FabEditorPage.screenOf(4, 5))"));
    await p.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await sleep(100);
    assert.deepEqual(await p.ev("FabEditorPage.cursor()"), [4, 5]);
  } finally { p.close(); }
});

test("G8 each challenge's palette holds its own tools, none disabled", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    assert.deepEqual(await palette(p), ["select", "rail", "route", "erase", "entry", "exit", "stocker"], "challenge 1 (Route comes with Track, docs/BUILD-CONTROLS.md part 8)");
    await tab(p, 1);
    assert.deepEqual(await palette(p), ["select"], "challenge 2");
    await tab(p, 4);
    const free = await palette(p);
    assert.ok(free.includes("rail") && free.includes("erase") && free.includes("stocker"), `free build: ${free}`);
    assert.equal(await p.ev(`document.querySelectorAll("#pal button:disabled").length`), 0, "no greyed keys");
  } finally { p.close(); }
});

test("G9 badges only for trouble at the opening hour", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(300);
    const o = JSON.parse(await p.ev("JSON.stringify({ badges: FabEditorPage.badges(), groups: FabEditorPage.groupsNow() })"));
    const kinds = new Set(["line", "broken", "gassed", "blocked", "held", "planned"]);
    for (const b of o.badges) assert.ok(kinds.has(b.kind), `badge kind ${b.kind}`);
    for (const g of o.groups) {
      const t = g.trouble;
      const drawn = o.badges.some((b) => b.group === g.group);
      assert.equal(drawn, !!t, `${g.group} (${g.mood}, ${g.queue} lots): a badge only with trouble`);
    }
  } finally { p.close(); }
});

test("G10 J turns the jam map on and off", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    assert.equal(await p.ev("FabEditorPage.jamMap()"), false);
    await p.key("j", "KeyJ");
    assert.equal(await p.ev("FabEditorPage.jamMap()"), true);
    assert.equal(await p.ev(`document.getElementById("jammap").getAttribute("aria-pressed")`), "true");
    await p.key("j", "KeyJ");
    assert.equal(await p.ev("FabEditorPage.jamMap()"), false);
  } finally { p.close(); }
});

test("G11 challenge 1 marks the broken track and gives advice", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const spot = await p.ev("JSON.stringify(FabEditorPage.spot())");
    const s = JSON.parse(spot);
    assert.ok(s && s.rail, `a spot on the track: ${spot}`);
    assert.ok(await p.ev(`!!FabEditorPage.railKeys().includes(${JSON.stringify(s.rail)})`), "the spot is a piece of track on the floor");
    assert.ok((await p.ev(`document.getElementById("advice").textContent.trim().length`)) > 10, "advice under the map");
  } finally { p.close(); }
});

test("G12 an edit floats its result over the map", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(800);
    await p.ev(`[...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "+").click()`);
    assert.ok(await until(p, `!!document.querySelector("#floats .float")`, 1500), "a float");
    assert.match(await p.ev(`document.querySelector("#floats .float").textContent`), /wafers a day|same output/);
  } finally { p.close(); }
});

test("G13 holding H shows the last run's jams", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(800);
    await p.ev(`[...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "+").click()`);
    await until(p, "FabEditorPage.runs() >= 2", 3000);
    await p.key("h", "KeyH", "keyDown");
    await sleep(100);
    assert.equal(await p.ev("FabEditorPage.showingLast()"), true, "the last run shows while H is held");
    assert.equal(await p.ev(`!document.getElementById("lastrun").hidden`), true, "the page says so");
    await p.key("h", "KeyH", "keyUp");
    await sleep(100);
    assert.equal(await p.ev("FabEditorPage.showingLast()"), false);
  } finally { p.close(); }
});
