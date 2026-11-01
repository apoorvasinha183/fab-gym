// The editor's basics (docs/EDITOR-BASICS.md): undo and redo, zoom and pan, a preview before placing, a run that keeps
// playing. Written before the code. On a teaching fab of our own and the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/editorbasics.test.mjs   (from the repo root; B1 to B4 need Google Chrome and the .venv)

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

// ---------------------------------------------------------------- in Node, on editor-core.js

test("C1 undo and redo, one step at a time", () => {
  const h = E.History(200);
  assert.equal(h.canUndo(), false);
  assert.equal(h.undo({ n: 0 }), null, "nothing to undo");
  h.push({ n: 0 }); // before step 1
  h.push({ n: 1 }); // before step 2
  assert.deepEqual(h.undo({ n: 2 }), { n: 1 }, "undo gives the state before the last step");
  assert.deepEqual(h.undo({ n: 1 }), { n: 0 });
  assert.equal(h.canUndo(), false);
  assert.deepEqual(h.redo({ n: 0 }), { n: 1 }, "redo gives the state after");
  assert.equal(h.canRedo(), true);
  h.push({ n: 1 }); // a new step
  assert.equal(h.canRedo(), false, "a new step clears redo");
  const big = E.History(200);
  for (let i = 0; i < 250; i++) big.push({ n: i });
  let k = 0;
  while (big.undo({ n: -1 })) k++;
  assert.equal(k, 200, "at most 200 steps kept");
  // a pushed state is a copy: changing it afterwards changes nothing kept
  const h2 = E.History(10), st = { blocks: [{ id: 1 }] };
  h2.push(st);
  st.blocks.push({ id: 2 });
  assert.deepEqual(h2.undo(st), { blocks: [{ id: 1 }] });
});

test("C2 zoom keeps the point under the pointer still, within limits; pan moves by the drag", () => {
  const v = { s: 20, ox: 100, oy: 50 };
  const world = (view, px, py) => [(px - view.ox) / view.s, (py - view.oy) / view.s];
  for (const f of [1.25, 0.8, 3]) {
    const z = E.zoomAt(v, f, 300, 200, 5, 80);
    const [a, b] = world(v, 300, 200), [c, d] = world(z, 300, 200);
    assert.ok(Math.abs(a - c) < 1e-9 && Math.abs(b - d) < 1e-9, `factor ${f}: the point under the pointer stays`);
  }
  assert.equal(E.zoomAt(v, 100, 0, 0, 5, 80).s, 80, "no closer than the limit");
  assert.equal(E.zoomAt(v, 0.01, 0, 0, 5, 80).s, 5, "no farther than the limit");
  assert.deepEqual(E.panBy(v, 13, -7), { s: 20, ox: 113, oy: 43 });
});

test("C3 a spot is free or says why not; the ghost reports its footprint", () => {
  const st = { W: 10, H: 8, blocks: [{ id: 1, kind: "stocker", x: 2, y: 2, w: 2, h: 2 }], rail: { [E.key(6, 1)]: { o: [1, 0, 0, 0] } } };
  assert.equal(E.isFree(st, 0, 0, 2, 2).ok, true);
  const onBlock = E.isFree(st, 3, 3, 2, 2);
  assert.equal(onBlock.ok, false);
  assert.match(onBlock.why, /machine|storage|in the way|taken/i);
  const onTrack = E.isFree(st, 5, 0, 2, 2);
  assert.equal(onTrack.ok, false);
  assert.match(onTrack.why, /track/i);
  const off = E.isFree(st, 9, 7, 2, 2);
  assert.equal(off.ok, false);
  assert.match(off.why, /floor|edge|outside/i);
  assert.equal(E.isFree(st, 2, 2, 2, 2, 1).ok, true, "a block may stay where it is when moved");
  assert.deepEqual(E.ghost(st, "stocker", 0, 4), { kind: "stocker", x: 0, y: 4, w: 2, h: 2, ok: true, why: "" });
  const g = E.ghost(st, "entry", 2, 2);
  assert.equal(g.w, 1);
  assert.equal(g.h, 2);
  assert.equal(g.ok, false);
});

// ---------------------------------------------------------------- the page in headless Chrome, with its own helper

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function helper() {
  const port = 8800 + Math.floor(Math.random() * 400);
  const p = spawn(PY, ["-m", "agent.helper", "--no-model", "--runs", mkdtempSync(join(tmpdir(), "test-runs-")), "--port", String(port)], { cwd: ROOT, stdio: "ignore" });
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
    `--user-data-dir=${profileDir("edb-")}`, "about:blank"], { stdio: "ignore" });
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

test("B1 undo and redo from the keyboard; a track drag is one step", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    assert.equal(await page(b, "F.canUndo()"), false, "nothing to undo at load");
    assert.equal(await b.ev("document.getElementById('undo').disabled"), true, "the undo button is disabled at load");
    // storage in hand, clicked on a free spot
    const [x, y] = await page(b, "F.firstFree(2, 2)");
    const n0 = await page(b, "F.blocks().length");
    await b.ev("document.querySelector('#pal [data-t=stocker]').click()");
    const [sx, sy] = await page(b, `F.screenOf(${x}, ${y})`);
    await b.mouse("mouseMoved", sx, sy); await b.mouse("mousePressed", sx, sy); await b.mouse("mouseReleased", sx, sy);
    await sleep(100);
    assert.equal(await page(b, "F.blocks().length"), n0 + 1, "storage placed");
    assert.equal(await b.ev("document.getElementById('undo').disabled"), false, "the undo button is on after an edit");
    await b.key("z", "KeyZ", 2);
    await sleep(100);
    assert.equal(await page(b, "F.blocks().length"), n0, "Ctrl+Z removes it");
    await b.key("z", "KeyZ", 2 | 8);
    await sleep(100);
    assert.equal(await page(b, "F.blocks().length"), n0 + 1, "Ctrl+Shift+Z puts it back");
    // a four-cell track drag, undone in one step
    const [tx, ty] = await page(b, "F.firstFree(4, 1)");
    const r0 = await page(b, "F.rails()");
    await b.key("b", "KeyB");
    const pts = [];
    for (let i = 0; i < 4; i++) pts.push(await page(b, `F.screenOf(${tx + i}, ${ty})`));
    await b.mouse("mouseMoved", pts[0][0], pts[0][1]); await b.mouse("mousePressed", pts[0][0], pts[0][1]);
    for (const [px, py] of pts.slice(1)) { await b.mouse("mouseMoved", px, py, { buttons: 1 }); await sleep(20); }
    await b.mouse("mouseReleased", pts[3][0], pts[3][1]);
    await sleep(100);
    assert.equal(await page(b, "F.rails()"), r0 + 4, "four track pieces laid");
    await b.key("z", "KeyZ", 2);
    await sleep(100);
    assert.equal(await page(b, "F.rails()"), r0, "one undo takes the whole drag back");
  } finally { close(); }
});

test("B2 scroll zooms about the pointer; Space-drag pans; F fits", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await b.key("v", "KeyV");
    const fitted = await page(b, "F.view()");
    const [x, y] = await page(b, "F.firstFree(1, 1)");
    // positions measured on the map itself, so a shift of the page around it does not count
    const onMap = async (cx, cy) => page(b, `(() => { const r = document.getElementById("map").getBoundingClientRect(), p = F.screenOf(${cx}, ${cy}); return [p[0] - r.left, p[1] - r.top]; })()`);
    const [sx, sy] = await page(b, `F.screenOf(${x}, ${y})`);
    const [mx0, my0] = await onMap(x, y);
    await b.send("Input.dispatchMouseEvent", { type: "mouseWheel", x: sx, y: sy, deltaX: 0, deltaY: -240 });
    await sleep(150);
    const z = await page(b, "F.view()");
    assert.ok(z.s > fitted.s * 1.1, `zoomed in (${fitted.s} to ${z.s})`);
    const [mx1, my1] = await onMap(x, y);
    assert.ok(Math.hypot(mx1 - mx0, my1 - my0) <= 2, `the cell under the pointer stayed (moved ${Math.hypot(mx1 - mx0, my1 - my0).toFixed(1)} px)`);
    // Space-drag on the floor: the view moves by the drag (a plain drag selects, docs/BUILD-CONTROLS.md part 7)
    const [ex, ey] = await page(b, "F.firstFree(1, 1)");
    const [px, py] = await page(b, `F.screenOf(${ex}, ${ey})`);
    const before = await page(b, "F.view()");
    await b.send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space" });
    await b.mouse("mouseMoved", px, py); await b.mouse("mousePressed", px, py);
    await b.mouse("mouseMoved", px + 60, py + 30, { buttons: 1 }); await b.mouse("mouseReleased", px + 60, py + 30);
    await b.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space" });
    await sleep(100);
    const after = await page(b, "F.view()");
    assert.ok(Math.abs(after.ox - before.ox - 60) <= 1 && Math.abs(after.oy - before.oy - 30) <= 1, `panned by the drag (${after.ox - before.ox}, ${after.oy - before.oy})`);
    await b.key("f", "KeyF");
    await sleep(100);
    const back = await page(b, "F.view()");
    assert.ok(Math.abs(back.s - fitted.s) < 1e-6 && Math.abs(back.ox - fitted.ox) < 1e-6 && Math.abs(back.oy - fitted.oy) < 1e-6, "F fits again");
  } finally { close(); }
});

test("B3 a ghost before placing: teal where it fits, red where it does not, nothing placed until a click", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await b.ev("document.querySelector('#pal [data-t=stocker]').click()");
    const n0 = await page(b, "F.blocks().length");
    const [x, y] = await page(b, "F.firstFree(2, 2)");
    const [sx, sy] = await page(b, `F.screenOf(${x}, ${y})`);
    await b.mouse("mouseMoved", sx, sy);
    await sleep(80);
    const g = await page(b, "F.ghost()");
    assert.ok(g && g.ok === true && g.x === x && g.y === y && g.w === 2 && g.h === 2, `ghost fits at the free spot: ${JSON.stringify(g)}`);
    assert.equal(await page(b, "F.blocks().length"), n0, "nothing placed by hovering");
    const m = await page(b, "F.blocks().find((k) => k.kind === 'group')");
    const [mx, my] = await page(b, `F.screenOf(${m.x}, ${m.y})`);
    await b.mouse("mouseMoved", mx, my);
    await sleep(80);
    assert.equal((await page(b, "F.ghost()")).ok, false, "over a machine the ghost does not fit");
  } finally { close(); }
});

test("B4 an edit leaves the run playing and a new run arrives by itself", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await sleep(500);
    const runs0 = await page(b, "F.runs()");
    const c0 = await page(b, "F.clock()");
    // an edit: storage placed on a free spot
    await b.ev("document.querySelector('#pal [data-t=stocker]').click()");
    const [x, y] = await page(b, "F.firstFree(2, 2)");
    const [sx, sy] = await page(b, `F.screenOf(${x}, ${y})`);
    await b.mouse("mouseMoved", sx, sy); await b.mouse("mousePressed", sx, sy); await b.mouse("mouseReleased", sx, sy);
    const c1 = await page(b, "F.clock()");
    await sleep(300);
    const c2 = await page(b, "F.clock()");
    assert.ok(c2 > c1, `the clock keeps moving after an edit (${c1} to ${c2})`);
    let runs = runs0;
    for (let i = 0; i < 60 && runs <= runs0; i++) { await sleep(50); runs = await page(b, "F.runs()"); }
    assert.ok(runs > runs0, "a new run arrived by itself within 3 s");
    const c3 = await page(b, "F.clock()");
    assert.ok(c3 >= c0, `the clock did not go back (${c0} then ${c3})`);
  } finally { close(); }
});
