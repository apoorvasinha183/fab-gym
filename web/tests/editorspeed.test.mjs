// The editor at the floor's speed (docs/EDITOR-SPEED.md): the floor's speed button, replay windows that grow with the
// speed, edits that run sooner and never mid-drag, and Max on both pages. Written before the code. On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/editorspeed.test.mjs   (from the repo root; V2 to V6 need Google Chrome and the .venv)

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
const html = readFileSync(join(HERE, "..", "editor.html"), "utf8");

test("V1 one speed button, no speed menu, no slow motion", () => {
  assert.match(html, /<button[^>]*id="speed"/, "a speed button");
  assert.ok(!/<select[^>]*id="speed"/.test(html), "no speed menu");
  assert.ok(!/slow motion/i.test(html), "no slow motion");
});

// ---------------------------------------------------------------- headless Chrome, a helper of its own

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openEditor() {
  const hp = 8800 + Math.floor(Math.random() * 600);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("speed-")}`, "about:blank"], { stdio: "ignore" });
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
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/editor.html` });
  for (let i = 0; i < 200; i++) { await sleep(50); if (await ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
  return { ev, send, mouse, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}
const label = (p) => p.ev(`document.getElementById("speed").textContent.trim()`);
const press = (p) => p.ev(`document.getElementById("speed").click()`);
const until = async (p, expr, ms) => { const t = Date.now(); while (Date.now() - t < ms) { if (await p.ev(expr)) return Date.now() - t; await sleep(20); } return null; };

test("V2 the speed button starts at 1× and cycles 1×, 3×, 12×, Max and back", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const seen = [await label(p)];
    for (let i = 0; i < 4; i++) { await press(p); seen.push(await label(p)); }
    assert.deepEqual(seen, ["1×", "3×", "12×", "Max", "1×"]);
  } finally { p.close(); }
});

test("V3 at 1× the clock moves 30 to 60 fab minutes in 2 real seconds", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(800);
    const a = await p.ev("FabEditorPage.clock()"); const t = Date.now();
    await sleep(2000);
    const b = await p.ev("FabEditorPage.clock()"), secs = (Date.now() - t) / 1000;
    const per2 = ((b - a) / secs) * 2;
    assert.ok(per2 >= 30 && per2 <= 60, `${per2.toFixed(1)} fab minutes in 2 s`);
  } finally { p.close(); }
});

test("V4 at 12× the clock stands still at most twice in 3 s", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await press(p); await press(p);
    assert.equal(await label(p), "12×");
    await sleep(500);
    let prev = await p.ev("FabEditorPage.clock()"), still = 0, skip = 0;
    for (let i = 0; i < 30; i++) {
      await sleep(100);
      const c = await p.ev("FabEditorPage.clock()");
      if (c < prev - 1) skip = 5; // back to the start of the run
      else if (skip > 0) skip--;
      else if (Math.abs(c - prev) < 1e-9) still++;
      prev = c;
    }
    assert.ok(still <= 2, `the clock stood still ${still} times`);
  } finally { p.close(); }
});

test("V5 after an edit the new run is in within 500 ms", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(1000);
    const r0 = await p.ev("FabEditorPage.runs()");
    await p.ev(`[...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "+").click()`);
    const ms = await until(p, `FabEditorPage.runs() > ${r0}`, 3000);
    assert.ok(ms != null && ms <= 500, `the new run came in after ${ms} ms`);
  } finally { p.close(); }
});

test("V6 a held track drag starts no run; the release does", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(1000);
    const [x, y] = JSON.parse(await p.ev("JSON.stringify(FabEditorPage.firstFree(3, 1))"));
    const a = JSON.parse(await p.ev(`JSON.stringify(FabEditorPage.screenOf(${x}, ${y}))`)), b = JSON.parse(await p.ev(`JSON.stringify(FabEditorPage.screenOf(${x + 1}, ${y}))`));
    await p.key("b", "KeyB");
    const r0 = await p.ev("FabEditorPage.runs()");
    await p.mouse("mouseMoved", a[0], a[1]); await p.mouse("mousePressed", a[0], a[1]);
    await p.mouse("mouseMoved", b[0], b[1], { buttons: 1 });
    await sleep(900);
    assert.equal(await p.ev("FabEditorPage.runs()"), r0, "no run while the drag is held");
    await p.mouse("mouseReleased", b[0], b[1]);
    const ms = await until(p, `FabEditorPage.runs() > ${r0}`, 1000);
    assert.ok(ms != null, "a run after the release");
  } finally { p.close(); }
});

test("V7 a rerun keeps the tool in your hand", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(1000);
    const r0 = await p.ev("FabEditorPage.runs()");
    await p.ev(`[...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "+").click()`);
    await p.key("b", "KeyB");
    assert.equal(await p.ev("FabEditorPage.tool()"), "rail", "Track in hand");
    assert.ok((await until(p, `FabEditorPage.runs() > ${r0}`, 3000)) != null, "the rerun came in");
    await sleep(100);
    assert.equal(await p.ev("FabEditorPage.tool()"), "rail", "still Track after the rerun");
  } finally { p.close(); }
});

// ---------------------------------------------------------------- Max: one fab hour each drawn frame, on both pages

const toMax = async (p) => { for (let i = 0; i < 6 && (await label(p)) !== "Max"; i++) await press(p); assert.equal(await label(p), "Max"); };

test("V8 at Max the clock moves an hour or more between most samples 30 ms apart", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await toMax(p);
    let prev = await p.ev("FabEditorPage.clock()"), moved = 0;
    for (let i = 0; i < 20; i++) {
      await sleep(30);
      const c = await p.ev("FabEditorPage.clock()");
      if (c - prev >= 59 || c < prev) moved++;
      prev = c;
    }
    assert.ok(moved >= 14, `${moved} of 20 samples moved an hour or more`);
  } finally { p.close(); }
});

test("V9 at Max no cars are drawn and none are asked for", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await toMax(p);
    await sleep(300);
    await p.ev(`(() => { window.__replays = 0; const f = window.fetch; window.fetch = (u, o) => { if (String(u).includes("/api/fab/replay")) window.__replays++; return f(u, o); }; })()`);
    await sleep(1000);
    assert.equal(await p.ev("FabEditorPage.cars()"), 0, "no cars drawn");
    assert.equal(await p.ev("window.__replays"), 0, "no car replay asked for");
  } finally { p.close(); }
});

test("V10 back from Max to 1× the cars come back within 1.5 s", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await sleep(800);
    assert.ok((await p.ev("FabEditorPage.cars()")) > 0, "cars at 1× to begin with");
    await toMax(p);
    await sleep(500);
    await press(p);
    assert.equal(await label(p), "1×");
    assert.ok((await until(p, "FabEditorPage.cars() > 0", 1500)) != null, "cars again");
  } finally { p.close(); }
});

test("V11 the floor has Max too: its clock moves 10 fab hours or more in half a second, or reaches the end", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const hp = 8800 + Math.floor(Math.random() * 600);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp), "--quick"], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/index.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("fmax-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const pg = l.find((x) => x.type === "page"); if (pg) ws = new WebSocket(pg.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  try {
    await send("Page.enable");
    await send("Page.navigate", { url: `http://127.0.0.1:${hp}/index.html#floor` });
    for (let i = 0; i < 400 && (await ev("document.body.dataset.floor")) !== "full"; i++) await sleep(50);
    const fp = { ev };
    for (let i = 0; i < 6 && (await label(fp)) !== "Max"; i++) await press(fp);
    assert.equal(await label(fp), "Max");
    if ((await ev(`document.getElementById("play").textContent`)) === "▶") await ev(`document.getElementById("play").click()`);
    const a = await ev("FabFloorPage.time()"), end = await ev("FabFloorPage.end()");
    await sleep(500);
    const b = await ev("FabFloorPage.time()");
    assert.ok(b - a >= 600 || b >= end - 1, `the floor moved ${(b - a).toFixed(0)} fab minutes (end ${end})`);
  } finally { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); }
});
