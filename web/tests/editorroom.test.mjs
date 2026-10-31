// Room to draw, and a reward you can see (docs/EDITOR-ROOM.md): paper all round, a floor that grows as you draw, stars
// and a moment when a challenge is met. Written before the code. On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/editorroom.test.mjs   (from the repo root; R4 to R8 need Google Chrome and the .venv)

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

test("R1 stars: met 1, 2% over 2, 5% over 3, over budget none", () => {
  const t = { wafers: 600, budget: 100 };
  assert.equal(E.stars({ wafers_per_day: 599 }, t, 0), 0);
  assert.equal(E.stars({ wafers_per_day: 600 }, t, 0), 1);
  assert.equal(E.stars({ wafers_per_day: 612 }, t, 0), 2);
  assert.equal(E.stars({ wafers_per_day: 630 }, t, 0), 3);
  assert.equal(E.stars({ wafers_per_day: 700 }, t, 101), 0);
});

const toy = () => ({ W: 10, H: 8, rail: { "2,2": { o: [1, 0, 0, 0] } }, blocks: [{ id: 1, kind: "stocker", x: 4, y: 4, w: 2, h: 2 }] });

test("R2 isFree with growing allowed: past any edge is free, still not through things or past 120", () => {
  const st = toy();
  assert.equal(E.isFree(st, 10, 0, 1, 1).why, "Off the edge of the floor.");
  assert.ok(E.isFree(st, 10, 0, 1, 1, undefined, true).ok);
  assert.ok(E.isFree(st, -3, -2, 2, 2, undefined, true).ok);
  assert.ok(!E.isFree(st, 4, 4, 1, 1, undefined, true).ok, "the storage is in the way");
  assert.ok(!E.isFree(st, 125, 0, 1, 1, undefined, true).ok, "past 120 tiles");
});

test("R3 grow: right widens; left moves everything over; past 120 nothing changes", () => {
  let st = toy();
  assert.deepEqual(E.grow(st, 11, 3, 1, 1), [0, 0]);
  assert.equal(st.W, 12); assert.equal(st.blocks[0].x, 4); assert.ok(st.rail["2,2"]);
  st = toy();
  assert.deepEqual(E.grow(st, -2, 0, 1, 1), [2, 0]);
  assert.equal(st.W, 12); assert.equal(st.blocks[0].x, 6); assert.ok(st.rail["4,2"] && !st.rail["2,2"]);
  st = toy();
  assert.equal(E.grow(st, 130, 0, 1, 1), null);
  assert.equal(st.W, 10);
});

// ---------------------------------------------------------------- headless Chrome, a helper of its own

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openEditor() {
  const hp = 8800 + Math.floor(Math.random() * 600);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("room-")}`, "about:blank"], { stdio: "ignore" });
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
const J = async (p, expr) => JSON.parse(await p.ev(`JSON.stringify(${expr})`));
const until = async (p, expr, ms) => { const t = Date.now(); while (Date.now() - t < ms) { if (await p.ev(expr)) return true; await sleep(40); } return false; };

/** A row where the cells from `x0` across `n` are free (no track, no piece). */
const freeRow = (p, x0, n) => J(p, `(() => { const [W, H] = FabEditorPage.size(), rails = new Set(FabEditorPage.railKeys()), bl = FabEditorPage.blocks();
  const used = (x, y) => rails.has(x + "," + y) || bl.some((b) => x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h);
  for (let y = 0; y < H; y++) { let ok = true; for (let i = 0; i < ${n}; i++) if (used(${x0} < 0 ? i : ${x0} + i, y)) ok = false; if (ok) return y; } return null; })()`);

async function drag(p, cells) {
  const pts = [];
  for (const [x, y] of cells) pts.push(await J(p, `FabEditorPage.screenOf(${x}, ${y})`));
  await p.mouse("mouseMoved", pts[0][0], pts[0][1]); await p.mouse("mousePressed", pts[0][0], pts[0][1]);
  for (const [x, y] of pts.slice(1)) { await p.mouse("mouseMoved", x, y, { buttons: 1 }); await sleep(30); }
  await p.mouse("mouseReleased", pts[pts.length - 1][0], pts[pts.length - 1][1]);
  await sleep(150);
}

test("R4 the opening view shows paper round the floor", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const o = await J(p, `(() => { const [W, H] = FabEditorPage.size(), a = FabEditorPage.screenOf(-0.5, -0.5), b = FabEditorPage.screenOf(W - 0.5, H - 0.5), c = FabEditorPage.screenOf(0.5, -0.5);
      const r = document.getElementById("map").getBoundingClientRect(); return { a, b, tile: c[0] - a[0], r: [r.left, r.top, r.right, r.bottom] }; })()`);
    assert.ok(o.a[0] - o.r[0] >= o.tile - 0.5 && o.a[1] - o.r[1] >= o.tile - 0.5, `paper left and above: ${JSON.stringify(o)}`);
    assert.ok(o.r[2] - o.b[0] >= o.tile - 0.5 && o.r[3] - o.b[1] >= o.tile - 0.5, `paper right and below: ${JSON.stringify(o)}`);
  } finally { p.close(); }
});

test("R5 track past the right edge grows the floor and the view holds still", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const [W] = await J(p, "FabEditorPage.size()");
    const y = await freeRow(p, W - 1, 1);
    assert.notEqual(y, null, "a free cell in the last column");
    const m = (await J(p, "FabEditorPage.blocks()")).find((b) => b.kind === "group");
    const before = await J(p, `FabEditorPage.screenOf(${m.x}, ${m.y})`);
    await p.key("b", "KeyB");
    const r0 = (await J(p, "FabEditorPage.railKeys()")).length;
    await drag(p, [[W - 1, y], [W, y], [W + 1, y]]);
    assert.equal((await J(p, "FabEditorPage.size()"))[0], W + 2, "two columns more");
    assert.equal((await J(p, "FabEditorPage.railKeys()")).length, r0 + 3, "three pieces of track");
    const mm = (await J(p, "FabEditorPage.blocks()")).find((b) => b.id === m.id);
    const after = await J(p, `FabEditorPage.screenOf(${mm.x}, ${mm.y})`);
    assert.ok(Math.hypot(after[0] - before[0], after[1] - before[1]) <= 1, `the machine moved ${after[0] - before[0]}, ${after[1] - before[1]} px`);
  } finally { p.close(); }
});

test("R6 track past the left edge moves everything over, and the view holds still", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const [W] = await J(p, "FabEditorPage.size()");
    const y = await freeRow(p, 0, 1);
    assert.notEqual(y, null, "a free cell in the first column");
    const m = (await J(p, "FabEditorPage.blocks()")).find((b) => b.kind === "group");
    const before = await J(p, `FabEditorPage.screenOf(${m.x}, ${m.y})`);
    await p.key("b", "KeyB");
    await drag(p, [[0, y], [-1, y]]);
    assert.equal((await J(p, "FabEditorPage.size()"))[0], W + 1, "one column more");
    const mm = (await J(p, "FabEditorPage.blocks()")).find((b) => b.id === m.id);
    assert.equal(mm.x, m.x + 1, "the machine's place moved right by one");
    const after = await J(p, `FabEditorPage.screenOf(${mm.x}, ${mm.y})`);
    assert.ok(Math.hypot(after[0] - before[0], after[1] - before[1]) <= 1, `the machine moved ${after[0] - before[0]}, ${after[1] - before[1]} px on screen`);
  } finally { p.close(); }
});

test("R7 meeting a challenge brings up the card, the stars and Next challenge", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await p.ev(`document.getElementById("showfix").click()`);
    assert.ok(await until(p, `!document.getElementById("win").hidden`, 8000), "the card shows");
    const o = await J(p, `({ lit: document.querySelectorAll("#win .star.on").length, next: [...document.querySelectorAll("#win button")].some((b) => /Next challenge/.test(b.textContent)),
      tab: document.querySelector("#chtabs [data-ch='0']").textContent })`);
    assert.ok(o.lit >= 1, `${o.lit} stars lit`);
    assert.ok(o.next, "a Next challenge button");
    assert.match(o.tab, /★/, `the tab: ${o.tab}`);
  } finally { p.close(); }
});

test("R8 the goal bar marks only the next star: the first before it is met, the second after one star", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const shown = () => J(p, `[...document.querySelectorAll("#goalbar .starmark")].filter((m) => !m.hidden).map((m) => m.title)`);
    let s = await shown();
    assert.equal(s.length, 1, `one mark: ${s}`);
    assert.match(s[0], /^1 star at 670/);
    await p.ev(`document.getElementById("showfix").click()`);
    assert.ok(await until(p, `!document.getElementById("win").hidden`, 8000));
    s = await shown();
    assert.equal(s.length, 1, `one mark: ${s}`);
    assert.match(s[0], /^2 stars at 684/);
  } finally { p.close(); }
});
