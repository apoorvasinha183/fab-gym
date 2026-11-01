// Build: editing that knows it is a fab, part 8 (docs/BUILD-CONTROLS.md). Written before the code. On a teaching fab of
// our own, built from the SMT2020 testbed's shapes; not a real fab.
//
//     node --test web/tests/editorsmart.test.mjs   (needs Google Chrome and the .venv for SR1 to SR6)

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

const k = E.key;
const sorted = (a) => [...a].sort();
const blank = (W = 20, H = 12) => ({ W, H, blocks: [], rail: {} });
const D4 = [[1, 0], [0, 1], [-1, 0], [0, -1]];
/** Each cell of a path points to the next (and only there, for the cells the route laid). */
function followsPath(st, path) {
  for (let i = 0; i + 1 < path.length; i++) {
    const [x, y] = path[i].split(",").map(Number), [nx, ny] = path[i + 1].split(",").map(Number);
    const d = D4.findIndex(([dx, dy]) => x + dx === nx && y + dy === ny);
    assert.ok(d >= 0, `${path[i]} and ${path[i + 1]} are neighbours`);
    assert.equal(st.rail[path[i]].o[d], 1, `${path[i]} leads to ${path[i + 1]}`);
  }
}

test("SM1 a route: the shortest way over free floor, one way, joined at its start; or why not", () => {
  const st = blank(), before = JSON.stringify(st);
  const r = E.route(st, k(0, 6), k(6, 6));
  assert.equal(r.ok, true, r.why);
  assert.deepEqual(r.path, [0, 1, 2, 3, 4, 5, 6].map((x) => k(x, 6)), "straight across");
  followsPath(r.state, r.path);
  assert.deepEqual(r.state.rail[k(6, 6)].o, [0, 0, 0, 0], "the end has no way on yet");
  assert.equal(JSON.stringify(st), before, "the old floor is unchanged");
  // around a machine standing in the way
  const st2 = blank();
  st2.blocks.push({ id: 1, kind: "group", area: "litho", group: "L1", count: 1, x: 3, y: 5, w: 2, h: 3 });
  const r2 = E.route(st2, k(0, 6), k(6, 6));
  assert.equal(r2.ok, true, r2.why);
  assert.equal(r2.path.length, 11, "the shortest way round");
  followsPath(r2.state, r2.path);
  for (const c of r2.path) { const [x, y] = c.split(",").map(Number); assert.ok(!(x >= 3 && x <= 4 && y >= 5 && y <= 7), `${c} is not under the machine`); }
  // a start on existing track keeps its way and gains one more
  const st3 = blank(); st3.rail[k(0, 6)] = { o: [0, 0, 0, 1] }; st3.rail[k(0, 5)] = { o: [0, 0, 0, 0] };
  const r3 = E.route(st3, k(0, 6), k(3, 6));
  assert.deepEqual(r3.state.rail[k(0, 6)].o, [1, 0, 0, 1]);
  // to any of several targets: the nearest
  const r4 = E.route(blank(), k(0, 0), [k(9, 0), k(3, 0)]);
  assert.equal(r4.path[r4.path.length - 1], k(3, 0));
  // nothing free
  const st5 = blank();
  for (const [x, y] of [[9, 9], [11, 9], [10, 8], [10, 10]]) st5.blocks.push({ id: x * 100 + y, kind: "stocker", x, y, w: 1, h: 1 });
  const r5 = E.route(st5, k(0, 0), k(10, 9));
  assert.equal(r5.ok, false); assert.match(r5.why, /no free way/i);
});

test("SM2 a cut's gaps, and healing routes around the cut tiles", () => {
  const st = blank();
  for (let x = 0; x <= 4; x++) st.rail[k(x, 2)] = { o: [x < 4 ? 1 : 0, 0, 0, 0] };
  const gaps = E.cutGaps(st, [k(2, 2)]);
  assert.deepEqual(gaps.preds, [k(1, 2)]); assert.deepEqual(gaps.succs, [k(3, 2)]); assert.deepEqual(gaps.cells, [k(2, 2)]);
  const cut = E.deleteSel(st, { blocks: [], rails: [k(2, 2)] }, "track");
  const h = E.heal(cut, gaps);
  assert.equal(h.ok, true, h.why);
  const p = h.paths[0];
  assert.equal(p[0], k(1, 2)); assert.equal(p[p.length - 1], k(3, 2)); assert.equal(p.length, 5, "round one row");
  assert.ok(!p.includes(k(2, 2)), "not through the cut");
  followsPath(h.state, p);
  assert.equal(h.state.rail[k(1, 2)].o.reduce((a, b) => a + b), 1, "the piece before the cut has one way out, round it");
  assert.ok(!h.state.rail[k(2, 2)], "the cut stays cut");
});

test("SM3 snap beside the track: within 3 tiles, the nearest free spot that touches it", () => {
  const st = blank();
  for (let x = 0; x <= 9; x++) st.rail[k(x, 5)] = { o: [1, 0, 0, 0] };
  assert.deepEqual(E.snapBeside(st, 4, 1, 2, 2), [4, 3], "two tiles down to touch the track");
  assert.deepEqual(E.snapBeside(st, 4, 3, 2, 2), [4, 3], "already beside it");
  assert.equal(E.snapBeside(st, 15, 0, 2, 2), null, "nothing within 3 tiles");
});

test("SM4 what the entry reaches and what reaches an exit, along the track's directions", () => {
  const st = blank();
  st.blocks.push({ id: 1, kind: "entry", x: 0, y: 3, w: 1, h: 2 }, { id: 2, kind: "exit", x: 5, y: 3, w: 1, h: 2 });
  st.rail[k(1, 3)] = { o: [1, 0, 0, 0] }; st.rail[k(2, 3)] = { o: [1, 1, 0, 0] }; st.rail[k(3, 3)] = { o: [1, 0, 0, 0] }; st.rail[k(4, 3)] = { o: [0, 0, 0, 0] };
  st.rail[k(2, 4)] = { o: [0, 0, 0, 0] }; st.rail[k(8, 8)] = { o: [1, 0, 0, 0] }; st.rail[k(9, 8)] = { o: [0, 0, 0, 0] };
  const r = E.reach(st);
  assert.deepEqual(sorted(r.fromEntry), sorted([k(1, 3), k(2, 3), k(3, 3), k(4, 3), k(2, 4)]));
  assert.deepEqual(sorted(r.toExit), sorted([k(1, 3), k(2, 3), k(3, 3), k(4, 3)]));
});

test("SM5 the same for every machine group, or every group of one kind", () => {
  const st = blank(), F = { kind: "random", mttf_minutes: 300, mttr_minutes: 30 }, R = { kind: "swap_to_spare", spares: 1, swap_minutes: 20 };
  st.blocks.push({ id: 1, kind: "group", area: "litho", group: "L1", count: 2, x: 0, y: 0, w: 2, h: 2, fail: F, rec: R },
    { id: 2, kind: "group", area: "litho", group: "L2", count: 1, x: 3, y: 0, w: 2, h: 2 },
    { id: 3, kind: "group", area: "litho", group: "L2", count: 1, x: 6, y: 0, w: 2, h: 2 },
    { id: 4, kind: "group", area: "cmp", group: "C1", count: 1, x: 9, y: 0, w: 2, h: 2 });
  const kind = E.sameForKind(st, "L1", "kind");
  for (const id of [2, 3]) { const b = kind.blocks.find((z) => z.id === id); assert.deepEqual([b.fail, b.rec], [F, R], `block ${id}`); }
  assert.equal(kind.blocks.find((z) => z.id === 4).fail, undefined, "another kind is left alone");
  const all = E.sameForKind(st, "L1", "all");
  assert.deepEqual(all.blocks.find((z) => z.id === 4).fail, F);
  assert.equal(st.blocks[1].fail, undefined, "the old floor is unchanged");
});

test("SM6 a pasted machine whose group this fab does not know takes an unplaced group of its kind, or is left out", () => {
  const st = blank();
  const clip = { blocks: [{ kind: "group", area: "litho", group: "Litho_FE_1", count: 2, w: 2, h: 2, dx: 0, dy: 0 }], rails: [], w: 2, h: 2 };
  const a = E.pasteAt(st, clip, 4, 4, { litho: ["Litho_T"] }, ["Litho_T", "Planar_T"]);
  assert.equal(a.blocks[0].group, "Litho_T");
  const b = E.pasteAt(st, clip, 4, 4, {}, ["Litho_T", "Planar_T"]);
  assert.equal(b.blocks.length, 0); assert.match(b.skipped.join(" "), /not in this fab/i);
  const c = E.pasteAt(st, clip, 4, 4, {}, ["Litho_FE_1"]);
  assert.equal(c.blocks[0].group, "Litho_FE_1", "a known group is its own");
});
// ---------------------------------------------------------------- the page in headless Chrome, with its own helper

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function helper() {
  const port = 8800 + Math.floor(Math.random() * 400);
  const p = spawn(PY, ["-m", "agent.helper", "--port", String(port), "--runs", profileDir("sm-runs-")], { cwd: ROOT, stdio: "ignore" });
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
    `--user-data-dir=${profileDir("sm-")}`, "about:blank"], { stdio: "ignore" });
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


const snap = (b) => page(b, "F.snapshot()");
const cellPt = (b, x, y) => page(b, `F.screenOf(${x}, ${y})`);
const MOD = { alt: 1, ctrl: 2, meta: 4, shift: 8 };
async function drag(b, from, to, modifiers = 0) {
  await b.mouse("mouseMoved", from[0], from[1], { modifiers });
  await b.mouse("mousePressed", from[0], from[1], { modifiers });
  for (let i = 1; i <= 4; i++) await b.mouse("mouseMoved", from[0] + ((to[0] - from[0]) * i) / 4, from[1] + ((to[1] - from[1]) * i) / 4, { buttons: 1, modifiers });
  await b.mouse("mouseReleased", to[0], to[1], { modifiers });
  await sleep(150);
}
async function click(b, pt, modifiers = 0, clickCount = 1) {
  await b.mouse("mouseMoved", pt[0], pt[1], { modifiers });
  await b.mouse("mousePressed", pt[0], pt[1], { modifiers, clickCount });
  await b.mouse("mouseReleased", pt[0], pt[1], { modifiers, clickCount });
  await sleep(120);
}
const press = async (b, key, code, modifiers = 0) => {
  await b.send("Input.dispatchKeyEvent", { type: "keyDown", key, code, modifiers, windowsVirtualKeyCode: key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0 });
  await b.send("Input.dispatchKeyEvent", { type: "keyUp", key, code, modifiers });
  await sleep(150);
};
const bbox = (st) => {
  const xs = [], ys = [];
  for (const z of st.blocks) { xs.push(z.x, z.x + z.w - 1); ys.push(z.y, z.y + z.h - 1); }
  for (const k of Object.keys(st.rail)) { const [x, y] = k.split(",").map(Number); xs.push(x); ys.push(y); }
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
};

const SKIP = !ready && "needs Google Chrome and the .venv";
const freeCell = (st, x, y) => x >= 0 && y >= 0 && x < st.W && y < st.H && !st.rail[k(x, y)] && !st.blocks.some((z) => x >= z.x && x < z.x + z.w && y >= z.y && y < z.y + z.h);
const checksHave = (b, code) => b.ev(`!!(FabEditorPage.checks() && FabEditorPage.checks().issues && FabEditorPage.checks().issues.some(i => i.code === ${JSON.stringify(code)}))`);

test("SM7 a route runs past the floor's edge and the floor grows to take it, up to its limit", () => {
  // a floor one row high with a machine across it: the only way round is past the edge
  const st = blank(6, 1);
  st.blocks.push({ id: 1, kind: "stocker", x: 2, y: 0, w: 1, h: 1 });
  const r = E.route(st, k(0, 0), k(5, 0));
  assert.equal(r.ok, true, r.why);
  assert.equal(r.path.length, 8, "round the machine in one row past the edge");
  assert.equal(r.state.H, 2, "the floor grew a row");
  for (const c of r.path) { const [x, y] = c.split(",").map(Number); assert.ok(x >= 0 && y >= 0 && x < r.state.W && y < r.state.H, `${c} is on the grown floor`); }
  followsPath(r.state, r.path);
  const m = r.state.blocks.find((z) => z.id === 1);
  assert.deepEqual([m.x - r.shift[0], m.y - r.shift[1]], [2, 0], "the machine stays where it was, moved over with everything");
  assert.equal(st.H, 1, "the old floor is unchanged");
  // starting left of the floor moves everything over
  const s2 = E.route(blank(6, 1), k(-2, 0), k(5, 0));
  assert.equal(s2.ok, true, s2.why);
  assert.deepEqual(s2.shift, [2, 0]); assert.equal(s2.state.W, 8); assert.equal(s2.path[0], k(0, 0));
  assert.equal(s2.path[s2.path.length - 1], k(7, 0));
  // past the limit
  const s3 = E.route(blank(E.ROOM_MAX, 1), k(-1, 0), k(5, 0));
  assert.equal(s3.ok, false); assert.match(s3.why, /as far as the floor goes/i);
});

test("SR7 on Free build a route from past the left edge grows the floor; one undo puts it back", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    const st = await snap(b);
    const target = Object.keys(st.rail).map((r) => r.split(",").map(Number)).sort((p, q) => p[0] - q[0] || p[1] - q[1])[0];
    const start = [-2, target[1]], want = E.route(st, k(...start), k(...target));
    assert.equal(want.ok, true, want.why);
    assert.ok(want.shift[0] > 0, "the floor grows to the left");
    await press(b, "t", "KeyT");
    await click(b, await cellPt(b, ...start));
    await b.mouse("mouseMoved", ...(await cellPt(b, ...target))); await sleep(150);
    await click(b, await cellPt(b, ...target));
    const now = await snap(b);
    assert.equal(now.W, want.state.W, "the floor grew");
    assert.deepEqual(now.rail, want.state.rail, "the track route gives, everything moved over");
    await press(b, "z", "KeyZ", MOD.meta);
    const back = await snap(b);
    assert.equal(back.W, st.W); assert.deepEqual(back.rail, st.rail, "one undo puts it all back");
  } finally { close(); }
});

test("SR1 the Route tool lays the track route gives between two clicks; one undo takes it away", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    const st = await snap(b);
    let pair = null;
    for (let y = 0; y < st.H && !pair; y++) for (let x = 0; x + 4 < st.W && !pair; x++) {
      if (![0, 1, 2, 3, 4].every((i) => freeCell(st, x + i, y))) continue;
      const r = E.route(st, k(x, y), k(x + 4, y));
      if (r.ok && r.path.length === 5) pair = [x, y, r];
    }
    assert.ok(pair, "five free tiles in a row");
    await press(b, "t", "KeyT");
    assert.equal(await page(b, "F.tool()"), "route");
    await click(b, await cellPt(b, pair[0], pair[1]));
    await b.mouse("mouseMoved", ...(await cellPt(b, pair[0] + 4, pair[1]))); await sleep(150);
    await click(b, await cellPt(b, pair[0] + 4, pair[1]));
    assert.deepEqual((await snap(b)).rail, pair[2].state.rail, "the track route gives");
    await press(b, "z", "KeyZ", MOD.meta);
    assert.deepEqual((await snap(b)).rail, st.rail, "one undo takes it all away");
  } finally { close(); }
});

test("SR2 erasing a piece in the middle of a run offers to reconnect, and reconnects as heal says", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    const st = await snap(b);
    let pick = null;
    for (const key of Object.keys(st.rail)) {
      const g = E.cutGaps(st, [key]);
      if (g.preds.length !== 1 || g.succs.length !== 1) continue;
      const h = E.heal(E.deleteSel(st, { blocks: [], rails: [key] }, "track"), g);
      if (h.ok) { pick = [key, h]; break; }
    }
    assert.ok(pick, "a piece whose cut can be healed");
    assert.equal(await b.ev(`document.getElementById("heal").hidden`), true, "no offer before a cut");
    await press(b, "e", "KeyE");
    await click(b, await cellPt(b, ...pick[0].split(",").map(Number)));
    assert.equal(await b.ev(`document.getElementById("heal").hidden`), false, "the offer shows");
    await b.ev(`document.getElementById("heal").click(), 1`); await sleep(200);
    assert.deepEqual((await snap(b)).rail, pick[1].state.rail);
    assert.equal(await b.ev(`document.getElementById("heal").hidden`), true, "and goes");
  } finally { close(); }
});

test("SR3 storage pointed one tile off the track is placed beside it; with Alt, where pointed", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    const st = await snap(b);
    const spots = [];
    for (let y = 0; y + 1 < st.H; y++) for (let x = 0; x + 1 < st.W; x++) {
      if (!E.isFree(st, x, y, 2, 2).ok || E.beside(st, { x, y, w: 2, h: 2 }).length) continue;
      const s2 = E.snapBeside(st, x, y, 2, 2);
      if (s2) spots.push([x, y, s2]);
    }
    assert.ok(spots.length >= 2, "spots off the track with track near");
    await b.ev(`document.querySelector('#pal [data-t="stocker"]').click(), 1`); await sleep(150);
    const [x, y, to] = spots[0];
    const n0 = st.blocks.filter((z) => z.kind === "stocker").length;
    await click(b, await cellPt(b, x, y));
    let now = await snap(b), stores = now.blocks.filter((z) => z.kind === "stocker");
    assert.equal(stores.length, n0 + 1);
    assert.ok(stores.some((z) => z.x === to[0] && z.y === to[1]), `placed beside the track at ${to}`);
    const far = spots.find(([sx, sy]) => E.isFree(now, sx, sy, 2, 2).ok && !E.beside(now, { x: sx, y: sy, w: 2, h: 2 }).length);
    await click(b, await cellPt(b, far[0], far[1]), MOD.alt);
    now = await snap(b);
    assert.ok(now.blocks.some((z) => z.kind === "stocker" && z.x === far[0] && z.y === far[1]), "with Alt, where pointed");
  } finally { close(); }
});

test("SR4 Fix buttons: a machine off the track goes beside it; quality holds with no rework get rework", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    const st = await snap(b);
    // move one machine to free floor that does not touch the track
    let pick = null;
    for (const z of st.blocks.filter((y) => y.kind === "group")) {
      for (let dy = -4; dy <= 4 && !pick; dy++) for (let dx = -4; dx <= 4 && !pick; dx++) {
        const m = E.moveSel(st, { blocks: [z.id], rails: [] }, dx, dy);
        if (m.ok && !E.beside(m.state, m.state.blocks.find((y) => y.id === z.id)).length) pick = [z, dx, dy];
      }
      if (pick) break;
    }
    assert.ok(pick, "a machine can be moved off the track");
    const [z, dx, dy] = pick;
    await click(b, await cellPt(b, z.x, z.y), MOD.shift);
    await drag(b, await cellPt(b, z.x, z.y), await cellPt(b, z.x + dx, z.y + dy));
    assert.ok(await until(b, `!!(FabEditorPage.checks() && FabEditorPage.checks().issues && FabEditorPage.checks().issues.some(i => i.code === "missing_stops"))`, 15000), "the checks say it has no stop");
    assert.ok(await until(b, `!!document.querySelector('#issues [data-fix]')`, 5000), "with a Fix button");
    await b.ev(`(() => { const li = [...document.querySelectorAll("#issues li")].find(l => /stop/i.test(l.textContent) && l.querySelector("[data-fix]")); li.querySelector("[data-fix]").click(); return 1; })()`);
    await sleep(200);
    const moved = (await snap(b)).blocks.find((y) => y.id === z.id);
    assert.ok(E.beside(await snap(b), moved).length, "beside the track again");
    assert.ok(await until(b, `!!(FabEditorPage.checks() && FabEditorPage.checks().issues && !FabEditorPage.checks().issues.some(i => i.code === "missing_stops"))`, 15000), "the check clears");
    // quality holds with no rework
    await b.ev(`document.querySelector('#ctl-tabs [data-tab="fab"]').click(), 1`); await sleep(150);
    await b.ev(`(() => { const s = document.getElementById("ctl-fab-holds"); s.value = "1"; s.dispatchEvent(new Event("change")); return 1; })()`);
    assert.ok(await until(b, `!!(FabEditorPage.checks() && FabEditorPage.checks().issues && FabEditorPage.checks().issues.some(i => i.code === "holds_without_rework"))`, 15000), "the warning shows");
    await b.ev(`(() => { const li = [...document.querySelectorAll("#issues li")].find(l => /rework/i.test(l.textContent)); li.querySelector("[data-fix]").click(); return 1; })()`);
    assert.match(await page(b, "F.fab()"), /^step\tLitho_Met_T\t.*\t0\.01\t/m, "rework set");
    assert.ok(await until(b, `!!(FabEditorPage.checks() && FabEditorPage.checks().issues && !FabEditorPage.checks().issues.some(i => i.code === "holds_without_rework"))`, 15000), "the warning clears");
  } finally { close(); }
});

test("SR5 Same for every machine group copies the selected group's breakdowns to all", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    const g = (await snap(b)).blocks.find((z) => z.kind === "group");
    await page(b, `F.select(${g.id})`); await sleep(150);
    await b.ev(`(() => { const s = document.getElementById("fsel"); s.value = "none"; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(150);
    await b.ev(`document.querySelector('#insp [data-same="all"]').click(), 1`); await sleep(150);
    for (const z of (await snap(b)).blocks.filter((y) => y.kind === "group")) assert.deepEqual(z.fail, { kind: "none" }, z.group);
  } finally { close(); }
});

test("SR6 a selection saved as a blueprint is listed, kept after a reload, and placed by two clicks", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    const st = await snap(b);
    await press(b, "a", "KeyA", MOD.meta);
    await b.ev(`document.querySelector('#insp [data-act="save"]').click(), 1`); await sleep(100);
    await b.ev(`(() => { const i = document.getElementById("bp-name"); i.value = "Whole teaching fab"; document.getElementById("bp-save").click(); return 1; })()`); await sleep(150);
    assert.match(await b.ev(`document.querySelector("#pal [data-bp]") ? document.querySelector("#pal [data-bp]").textContent : ""`), /Whole teaching fab/);
    await b.send("Page.reload"); await sleep(500);
    for (let i = 0; i < 200; i++) { await sleep(50); if (await b.ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
    await toTab(b, 4);
    assert.match(await b.ev(`document.querySelector("#pal [data-bp]") ? document.querySelector("#pal [data-bp]").textContent : ""`), /Whole teaching fab/, "kept after a reload");
    // clear the floor, then place the blueprint where the fab stood
    await press(b, "a", "KeyA", MOD.meta); await press(b, "Delete", "Delete");
    assert.equal((await snap(b)).blocks.length, 0);
    await b.ev(`document.querySelector("#pal [data-bp]").click(), 1`); await sleep(150);
    assert.equal(await page(b, "F.pasting()"), true, "in hand");
    const x0 = Math.min(...st.blocks.map((z) => z.x), ...Object.keys(st.rail).map((r) => +r.split(",")[0]));
    const y0 = Math.min(...st.blocks.map((z) => z.y), ...Object.keys(st.rail).map((r) => +r.split(",")[1]));
    const pt = await cellPt(b, x0, y0);
    await b.mouse("mouseMoved", pt[0], pt[1]); await sleep(150);
    await click(b, pt);
    const now = await snap(b);
    assert.equal(now.blocks.length, st.blocks.length, "every piece placed");
    assert.equal(Object.keys(now.rail).length, Object.keys(st.rail).length, "and all the track");
  } finally { close(); }
});
