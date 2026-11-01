// Build after review (docs/BUILD-REVIEW.md). Written before the code. On a teaching fab of our own and the SMT2020
// testbed; not a real fab.
//
//     node --test web/tests/buildreview.test.mjs   (needs Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
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
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");
const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const skip = !ready && "needs Google Chrome and the .venv";
async function openEditor(path = "editor.html?ch=1", w = 1440, h = 1000, stars = null) {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, `--window-size=${w},${h}`, "--hide-scrollbars", `--user-data-dir=${profileDir("build-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
  const key = async (k, code) => { await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code }); await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code }); };
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  if (stars) await send("Page.addScriptToEvaluateOnNewDocument", { source: `try { localStorage.setItem("fabgym.stars", ${JSON.stringify(JSON.stringify(stars))}); } catch (e) {}` });
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/${path}` });
  for (let i = 0; i < 200; i++) { await sleep(50); if (await ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
  return { ev, send, mouse, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}

const J = async (p, e) => JSON.parse(await p.ev(`JSON.stringify(${e})`));

test("BR1 tab stars are the best kept, filled and hollow; a challenge never met shows none", { skip }, async () => {
  const p = await openEditor("editor.html?ch=1", 1440, 1000, { rush: 2 });
  try {
    const tabs = await J(p, `[...document.querySelectorAll("#chtabs .tab")].map(t => t.textContent)`);
    assert.match(tabs[0], /best/i); assert.ok(tabs[0].includes("★★☆"), tabs[0]);
    assert.ok(!/[★☆]/.test(tabs[1]), `never met: ${tabs[1]}`);
  } finally { p.close(); }
});

test("BR2 the Layout card: complete and connected, never Looks good", { skip }, async () => {
  const p = await openEditor();
  try {
    for (let i = 0; i < 100; i++) { if (await p.ev(`/complete/i.test(document.getElementById("verdict").textContent)`)) break; await sleep(100); }
    const card = await J(p, `(() => { const c = document.getElementById("issues").closest(".card"); return { title: c.querySelector("h4 span").textContent, verdict: document.getElementById("verdict").textContent, body: document.getElementById("issues").textContent }; })()`);
    assert.equal(card.title, "Layout"); assert.match(card.verdict, /complete/i);
    assert.match(card.body, /Complete and connected/); assert.ok(!/Looks good/.test(card.body));
  } finally { p.close(); }
});

test("BR3 one clock, and one playback bar under the map", { skip }, async () => {
  const p = await openEditor();
  try {
    assert.equal(await p.ev(`!!document.getElementById("slabel")`), false, "no slider label");
    const r = await J(p, `(() => { const bar = document.getElementById("playbar"); const map = document.getElementById("mapbox").getBoundingClientRect(); return { inBar: ["play", "speed", "clock", "slider", "run-no", "new-run"].filter(id => bar && bar.contains(document.getElementById(id))), below: bar ? bar.getBoundingClientRect().top >= map.bottom - 1 : false }; })()`);
    assert.deepEqual(r.inBar, ["play", "speed", "clock", "slider", "run-no", "new-run"]);
    assert.ok(r.below, "the bar is under the map");
    await p.ev(`(() => { if (document.getElementById("play").textContent.includes("❚")) document.getElementById("play").click(); return 1; })()`);
    const before = await p.ev(`document.getElementById("clock").textContent`);
    await p.ev(`(() => { const s = document.getElementById("slider"); s.value = String(Math.max(0, +s.max - 3)); s.dispatchEvent(new Event("input", { bubbles: true })); return 1; })()`);
    await sleep(800);
    assert.notEqual(await p.ev(`document.getElementById("clock").textContent`), before, "the slider moves the clock");
  } finally { p.close(); }
});

test("BR4 every tile on Rush hour's map draws its name", { skip }, async () => {
  const p = await openEditor();
  try {
    await sleep(500);
    const r = await J(p, `({ labels: FabEditorPage.tileLabels(), n: FabEditorPage.blocks().length })`);
    assert.equal(r.labels.length, r.n, `${r.labels.length} names for ${r.n} tiles`);
    for (const want of ["Litho", "CMP", "Storage", "Wafers in", "Wafers out"]) assert.ok(r.labels.includes(want), `${want} is named`);
  } finally { p.close(); }
});

test("BR5 the palette's keys are keycaps and the buttons say which key", { skip }, async () => {
  const p = await openEditor("editor.html?ch=1");
  try {
    const keys = await J(p, `[...document.querySelectorAll("#pal button kbd")].map(k => ({ k: k.textContent, border: parseFloat(getComputedStyle(k).borderTopWidth), title: k.closest("button").title }))`);
    assert.ok(keys.length >= 3, "some keys");
    for (const k of keys) { assert.ok(k.border > 0, `${k.k} is a keycap`); assert.match(k.title, new RegExp(`key ${k.k}\\b`), `the title names key ${k.k}: ${k.title}`); }
  } finally { p.close(); }
});

// the page a laptop's browser actually gets: a 1,440 x 900 screen leaves about 760 to 790 px below Chrome's bars
for (const [w, h] of [[1440, 900], [1440, 760], [1280, 720]]) {
  test(`BR6 at ${w} x ${h} the page does not scroll and the playback bar is in view`, { skip }, async () => {
    const p = await openEditor("editor.html?ch=1", w, h);
    try {
      await sleep(600);
      const r = await J(p, `({ scroll: document.documentElement.scrollHeight - innerHeight, bar: document.getElementById("playbar") ? document.getElementById("playbar").getBoundingClientRect().bottom : 1e9, H: innerHeight })`);
      assert.ok(r.scroll <= 1, `no scroll (${r.scroll} px over)`);
      assert.ok(r.bar <= r.H, `the playback bar is in view (${r.bar} of ${r.H})`);
      const n = await p.ev("FabEditorPage.runs()");
      await p.ev(`FabEditorTools.call("set_cars", { count: 7 }), 1`);
      for (let i = 0; i < 200; i++) { await sleep(100); if ((await p.ev("FabEditorPage.runs()")) > n) break; }
      await sleep(300);
      const dl = await J(p, `[...document.querySelectorAll("#score .sc")].map(c => (c.querySelector(".dl") || {}).textContent || "")`);
      assert.equal(dl.length, 3);
      for (const d of dl) assert.match(d, /last run/, `each figure shows its change: ${d}`);
    } finally { p.close(); }
  });
}

test("BR7 Rush hour's goal names the click and the setting", { skip }, async () => {
  const p = await openEditor("editor.html?ch=1");
  try {
    const goal = await p.ev(`document.getElementById("chgoal").textContent`);
    assert.match(goal, /click the broken track/i); assert.match(goal, /Cars go around it/);
  } finally { p.close(); }
});

test("BR8 Build from a photo, and New run says what it plays", { skip }, async () => {
  const p = await openEditor();
  try {
    const b = await J(p, `({ text: document.getElementById("sketch-go").textContent.trim(), icon: !!document.querySelector("#sketch-go svg"), nr: document.getElementById("new-run").title })`);
    assert.match(b.text, /Build from a photo/); assert.ok(b.icon, "an icon");
    assert.match(b.nr, /another random run/i);
  } finally { p.close(); }
});
