// The editor's foreman keys (docs/EDITOR-MOVES.md): R to turn, Q to pick, a 1–9 hotbar, box select with copy and
// paste. Written before the code. On a teaching fab of our own and the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/editormoves.test.mjs   (from the repo root; P1 to P4 need Google Chrome and the .venv)

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

// a small floor: a lithography group, storage, wafers in, and two pieces of track
function floor() {
  return {
    W: 20, H: 10,
    blocks: [
      { id: 1, kind: "group", area: "litho", group: "L1", count: 3, x: 0, y: 0, w: 2, h: 2 },
      { id: 2, kind: "stocker", x: 4, y: 0, w: 2, h: 2 },
      { id: 3, kind: "entry", x: 7, y: 0, w: 1, h: 2 },
    ],
    rail: { [E.key(0, 3)]: { o: [1, 0, 0, 0] }, [E.key(1, 3)]: { o: [0, 0, 1, 0] } },
  };
}

// ---------------------------------------------------------------- in Node, on editor-core.js

test("M1 turning: wafers in and out swap; square pieces stay", () => {
  assert.deepEqual(E.turn("entry", 1, 2), { w: 2, h: 1, changed: true });
  assert.deepEqual(E.turn("exit", 2, 1), { w: 1, h: 2, changed: true });
  assert.deepEqual(E.turn("group", 2, 2), { w: 2, h: 2, changed: false });
  assert.deepEqual(E.turn("stocker", 2, 2), { w: 2, h: 2, changed: false });
});

test("M2 picking what is under the pointer", () => {
  const st = floor();
  assert.equal(E.pickAt(st, 1, 1), "litho");
  assert.equal(E.pickAt(st, 5, 1), "stocker");
  assert.equal(E.pickAt(st, 7, 1), "entry");
  assert.equal(E.pickAt(st, 0, 3), "rail");
  assert.equal(E.pickAt(st, 15, 8), "select");
});

test("M3 a box selects what is wholly inside it", () => {
  const st = floor();
  const a = E.inBox(st, 0, 0, 5, 3), b = E.inBox(st, 5, 3, 0, 0);
  assert.deepEqual(a.blocks.sort(), [1, 2]);
  assert.deepEqual(a.rails.sort(), [E.key(0, 3), E.key(1, 3)].sort());
  assert.deepEqual(b, a, "the corners in any order");
  assert.deepEqual(E.inBox(st, 0, 0, 4, 3).blocks, [1], "storage only partly inside is left out");
});

test("M4 copy and paste: same layout moved; machines take the next unplaced group, else more of their own; nothing changes until placed", () => {
  const st = floor();
  const before = JSON.stringify(st);
  const clip = E.copySel(st, E.inBox(st, 0, 0, 5, 3));
  assert.deepEqual(clip.blocks.map((b) => [b.kind, b.dx, b.dy]).sort(), [["group", 0, 0], ["stocker", 4, 0]]);
  assert.deepEqual(clip.rails.map((r) => [r.dx, r.dy]).sort(), [[0, 3], [1, 3]]);
  const p = E.pasteAt(st, clip, 10, 0, { litho: ["L2"] });
  assert.equal(p.ok, true, p.why);
  const g = p.blocks.find((b) => b.kind === "group");
  assert.deepEqual([g.x, g.y, g.group, g.area, g.count], [10, 0, "L2", "litho", 3]);
  assert.deepEqual([p.blocks.find((b) => b.kind === "stocker").x, p.blocks.find((b) => b.kind === "stocker").y], [14, 0]);
  assert.deepEqual(p.rails[E.key(10, 3)], { o: [1, 0, 0, 0] }, "track directions kept");
  assert.deepEqual(p.rails[E.key(11, 3)], { o: [0, 0, 1, 0] });
  const none = E.pasteAt(st, clip, 10, 0, {});
  const more = none.blocks.find((b) => b.kind === "group");
  assert.deepEqual(more && [more.group, more.count], ["L1", 3], "no unplaced lithography group: more machines of its own group (docs/BUILD-CONTROLS.md, part 7)");
  assert.deepEqual(none.skipped, []);
  const over = E.pasteAt(st, clip, 0, 0, { litho: ["L2"] });
  assert.equal(over.ok, false);
  assert.match(over.why, /in the way|track/i);
  assert.equal(JSON.stringify(st), before, "pasting changes nothing until placed");
});

test("M5 the hotbar: three tools, then the six most recent pieces", () => {
  const fill = ["stocker", "entry", "exit", ...E.AREAS.slice(0, 3)];
  assert.deepEqual(E.hotbar([]), ["select", "rail", "erase", ...fill]);
  const h = E.hotbar(["dry", "stocker", "dry"]);
  assert.equal(h.length, 9);
  assert.deepEqual(h.slice(0, 5), ["select", "rail", "erase", "dry", "stocker"]);
  assert.equal(new Set(h).size, 9, "no piece twice");
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
    `--user-data-dir=${profileDir("edm-")}`, "about:blank"], { stdio: "ignore" });
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
  // modifiers: 2 Ctrl, 8 Shift
  const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1, ...extra });
  const key = async (k, code, modifiers = 0, vk) => {
    const v = vk || (k.length === 1 ? k.toUpperCase().charCodeAt(0) : 0);
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code, modifiers, windowsVirtualKeyCode: v });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, modifiers, windowsVirtualKeyCode: v });
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
  return { b, close: () => { b.close(); h.close(); } };
}

const page = (b, expr) => b.ev(`(() => { const F = window.FabEditorPage; return ${expr}; })()`);
const at = (b, x, y) => page(b, `F.screenOf(${x}, ${y})`);
async function click(b, x, y, modifiers = 0) {
  const [sx, sy] = await at(b, x, y);
  await b.mouse("mouseMoved", sx, sy, { modifiers }); await b.mouse("mousePressed", sx, sy, { modifiers }); await b.mouse("mouseReleased", sx, sy, { modifiers });
  await sleep(60);
}
async function hover(b, x, y) { const [sx, sy] = await at(b, x, y); await b.mouse("mouseMoved", sx, sy); await sleep(60); }
async function dragCells(b, from, to, modifiers = 0) {
  const [ax, ay] = await at(b, from[0], from[1]), [bx, by] = await at(b, to[0], to[1]);
  await b.mouse("mouseMoved", ax, ay, { modifiers }); await b.mouse("mousePressed", ax, ay, { modifiers });
  for (let i = 1; i <= 6; i++) { await b.mouse("mouseMoved", ax + ((bx - ax) * i) / 6, ay + ((by - ay) * i) / 6, { buttons: 1, modifiers }); await sleep(15); }
  await b.mouse("mouseReleased", bx, by, { modifiers });
  await sleep(80);
}
const hand = (b, t) => b.ev(`document.querySelector('#pal [data-t="${t}"]').click()`);

test("P1 R turns wafers in, in hand and where it stands", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await hand(b, "entry");
    const [x, y] = await page(b, "F.firstFree(2, 2)");
    await hover(b, x, y);
    let g = await page(b, "F.ghost()");
    assert.deepEqual([g.w, g.h], [1, 2], "wafers in starts 1 × 2");
    await b.key("r", "KeyR");
    await hover(b, x, y);
    g = await page(b, "F.ghost()");
    assert.deepEqual([g.w, g.h], [2, 1], "R turns the ghost");
    await b.key("r", "KeyR");
    await click(b, x, y, 1); // Alt: exactly here, since a piece off the track snaps beside it (docs/BUILD-CONTROLS.md, part 8)
    const placed = await page(b, `F.blocks().find((k) => k.kind === "entry" && k.x === ${x} && k.y === ${y})`);
    assert.ok(placed && placed.w === 1 && placed.h === 2, "placed 1 × 2");
    await b.key("v", "KeyV");
    await click(b, x, y);
    await b.key("r", "KeyR");
    await sleep(80);
    const turned = await page(b, `F.blocks().find((k) => k.id === ${placed.id})`);
    assert.deepEqual([turned.w, turned.h], [2, 1], "R turns a selected piece where it stands");
  } finally { close(); }
});

test("P2 Q picks up what is under the pointer", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await hand(b, "stocker");
    const [x, y] = await page(b, "F.firstFree(2, 2)");
    await click(b, x, y);
    await b.key("b", "KeyB");
    const [tx, ty] = await page(b, "F.firstFree(2, 1)");
    await dragCells(b, [tx, ty], [tx + 1, ty]);
    await b.key("v", "KeyV");
    await hover(b, x, y); await b.key("q", "KeyQ");
    assert.equal(await page(b, "F.tool()"), "stocker", "Q over storage takes storage");
    await hover(b, tx, ty); await b.key("q", "KeyQ");
    assert.equal(await page(b, "F.tool()"), "rail", "Q over track takes the Track tool");
    const [ex, ey] = await page(b, "F.firstFree(1, 1)");
    await hover(b, ex, ey); await b.key("q", "KeyQ");
    assert.equal(await page(b, "F.tool()"), "select", "Q over empty floor empties the hand");
  } finally { close(); }
});

test("P3 the hotbar: 1, 2, 3 and the fourth slot, numbers on the palette", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await b.key("2", "Digit2"); assert.equal(await page(b, "F.tool()"), "rail");
    await b.key("3", "Digit3"); assert.equal(await page(b, "F.tool()"), "erase");
    await b.key("1", "Digit1"); assert.equal(await page(b, "F.tool()"), "select");
    const bar = await page(b, "F.hotbar()");
    await b.key("4", "Digit4"); assert.equal(await page(b, "F.tool()"), bar[3]);
    assert.equal(await b.ev(`(document.querySelector('#pal [data-t="${bar[3]}"] kbd') || {}).textContent`), "4", "the palette shows the slot's number");
  } finally { close(); }
});

test("P4 box select, copy, paste and delete, each one undo step", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    // two storage blocks stacked and two pieces of track under them, in a free 2 × 5 patch (the challenge's floor has
    // no wider patch that can be pointed at); the farther block first
    const [x, y] = await page(b, "F.firstFree(2, 5)");
    await hand(b, "stocker");
    await click(b, x, y);
    await click(b, x, y + 2);
    await b.key("b", "KeyB");
    await dragCells(b, [x, y + 4], [x + 1, y + 4]);
    const n0 = await page(b, "F.blocks().length"), r0 = await page(b, "F.rails()");
    await b.key("v", "KeyV");
    await dragCells(b, [x, y], [x + 1, y + 4], 8);
    const sel = await page(b, "F.selection()");
    assert.equal(sel.blocks.length, 2, "two storage blocks selected");
    assert.equal(sel.rails.length, 2, "two track pieces selected");
    await b.key("c", "KeyC", 2);
    assert.ok(await page(b, "F.clipboard() && F.clipboard().blocks.length === 2"), "copied");
    await b.key("v", "KeyV", 2);
    const [px, py] = await page(b, "F.firstFree(2, 5)");
    await hover(b, px, py);
    assert.equal((await page(b, "F.ghost()")).ok, true, "the pasted layout fits there");
    await click(b, px, py);
    assert.equal(await page(b, "F.blocks().length"), n0 + 2, "two blocks pasted");
    assert.equal(await page(b, "F.rails()"), r0 + 2, "two track pieces pasted");
    await b.key("z", "KeyZ", 2);
    await sleep(80);
    assert.equal(await page(b, "F.blocks().length"), n0, "one undo takes the paste back");
    assert.equal(await page(b, "F.rails()"), r0);
    await b.key("Escape", "Escape", 0, 27);
    await dragCells(b, [x, y], [x + 1, y + 4], 8);
    await b.key("Delete", "Delete", 0, 46);
    await sleep(80);
    assert.equal(await page(b, "F.blocks().length"), n0 - 2, "Delete removes the selection");
    assert.equal(await page(b, "F.rails()"), r0 - 2);
    await b.key("z", "KeyZ", 2);
    await sleep(80);
    assert.equal(await page(b, "F.blocks().length"), n0, "one undo puts it back");
    assert.equal(await page(b, "F.rails()"), r0);
  } finally { close(); }
});
