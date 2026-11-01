// Build: select and act on a selection, part 7 (docs/BUILD-CONTROLS.md). Written before the code. On a teaching fab of
// our own, built from the SMT2020 testbed's shapes; not a real fab.
//
//     node --test web/tests/editorselect.test.mjs   (needs Google Chrome and the .venv for SB1 to SB6)

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

/** A small floor: a machine, storage, wafers in, a loop of track and a separate track piece. */
function floor() {
  const k = E.key;
  return {
    W: 20, H: 12,
    blocks: [
      { id: 1, kind: "group", area: "litho", group: "L1", count: 3, x: 0, y: 0, w: 2, h: 2 },
      { id: 2, kind: "stocker", x: 4, y: 0, w: 2, h: 2 },
      { id: 3, kind: "entry", x: 7, y: 0, w: 1, h: 2 },
    ],
    // a loop: (0,3) east (1,3) east (2,3) south (2,4) west (1,4) west (0,4) north; and a lone piece at (12,8) east
    rail: { [k(0, 3)]: { o: [1, 0, 0, 0] }, [k(1, 3)]: { o: [1, 0, 0, 0] }, [k(2, 3)]: { o: [0, 1, 0, 0] }, [k(2, 4)]: { o: [0, 0, 1, 0] },
      [k(1, 4)]: { o: [0, 0, 1, 0] }, [k(0, 4)]: { o: [0, 0, 0, 1] }, [k(12, 8)]: { o: [1, 0, 0, 0] } },
  };
}
const sorted = (a) => [...a].sort();

test("SE1 a box selects what is wholly inside it, or, crossing, whatever it touches", () => {
  const st = floor();
  const win = E.inBox(st, 0, 0, 4, 3);
  assert.deepEqual(sorted(win.blocks), [1], "only the machine lies wholly inside");
  assert.deepEqual(sorted(win.rails), sorted([E.key(0, 3), E.key(1, 3), E.key(2, 3)]));
  const cross = E.inBox(st, 0, 0, 4, 3, true);
  assert.deepEqual(sorted(cross.blocks), [1, 2], "the storage is touched");
  assert.deepEqual(sorted(cross.rails), sorted(win.rails));
});

test("SE2 the track joined to a piece, either way of travel, and nothing else", () => {
  const st = floor();
  const loop = [E.key(0, 3), E.key(1, 3), E.key(2, 3), E.key(2, 4), E.key(1, 4), E.key(0, 4)];
  assert.deepEqual(sorted(E.connectedRail(st, E.key(1, 4))), sorted(loop));
  assert.deepEqual(E.connectedRail(st, E.key(12, 8)), [E.key(12, 8)]);
});

test("SE3 a move shifts pieces and track, directions kept, or says why it does not fit", () => {
  const st = floor(), before = JSON.stringify(st);
  const sel = { blocks: [1], rails: [E.key(0, 3), E.key(1, 3)] };
  const m = E.moveSel(st, sel, 10, 5);
  assert.equal(m.ok, true, m.why);
  const b = m.state.blocks.find((z) => z.id === 1);
  assert.deepEqual([b.x, b.y], [10, 5]);
  assert.deepEqual(m.state.rail[E.key(10, 8)], { o: [1, 0, 0, 0] });
  assert.ok(!m.state.rail[E.key(0, 3)], "the old place is empty");
  assert.ok(m.state.rail[E.key(2, 3)], "track not selected stays");
  const onto = E.moveSel(st, { blocks: [1], rails: [] }, 4, 0);
  assert.equal(onto.ok, false); assert.match(onto.why, /in the way/i);
  const own = E.moveSel(st, { blocks: [], rails: [E.key(0, 3), E.key(1, 3)] }, 1, 0);
  assert.equal(own.ok, false, "onto track that is not selected"); 
  const self = E.moveSel(st, { blocks: [], rails: [E.key(0, 3), E.key(1, 3), E.key(2, 3)] }, 0, 0);
  assert.equal(self.ok, true, "the selection's own place does not block it");
  const off = E.moveSel(st, sel, -1, 0);
  assert.equal(off.ok, false); assert.match(off.why, /edge/i);
  assert.equal(JSON.stringify(st), before, "the old floor is unchanged");
});

test("SE4 a quarter turn turns pieces and track in the selection's box; four turns or two mirrors give it back", () => {
  const st = floor();
  // wafers in (1 x 2 at 7,0) and the track piece east of the box below it
  st.rail[E.key(7, 2)] = { o: [1, 0, 0, 0] };
  const sel = { blocks: [3], rails: [E.key(7, 2)] };
  const t = E.turnSel(st, sel);
  assert.equal(t.ok, true, t.why);
  // box 1 x 3 at (7,0); turned clockwise it is 3 x 1 at (7,0): the entry becomes 2 x 1 at its right, the track at its left
  const e = t.state.blocks.find((z) => z.id === 3);
  assert.deepEqual([e.x, e.y, e.w, e.h], [8, 0, 2, 1]);
  assert.deepEqual(t.state.rail[E.key(7, 0)], { o: [0, 1, 0, 0] }, "east turns to south");
  let s4 = st, sel4 = sel;
  for (let i = 0; i < 4; i++) { const r = E.turnSel(s4, sel4); assert.equal(r.ok, true, r.why); s4 = r.state; sel4 = r.sel; }
  assert.deepEqual(s4, st, "four turns give it back");
  const m = E.turnSel(st, sel, true);
  assert.equal(m.ok, true);
  assert.deepEqual(m.state.rail[E.key(7, 2)], { o: [0, 0, 1, 0] }, "a mirror turns east to west");
  const m2 = E.turnSel(m.state, m.sel, true);
  assert.deepEqual(m2.state, st, "two mirrors give it back");
  // the machine and storage in a 6 x 2 box turned to 2 x 6 run into the track below
  const no = E.turnSel(st, { blocks: [1, 2], rails: [] });
  assert.equal(no.ok, false); assert.ok(no.why.length > 5, no.why);
});

test("SE5 deleting all, only track, only machines, or only storage and doors", () => {
  const st = floor(), sel = E.inBox(st, 0, 0, 19, 11);
  const kinds = (s) => sorted(s.blocks.map((b) => b.kind));
  const all = E.deleteSel(st, sel, "all");
  assert.equal(all.blocks.length, 0); assert.equal(Object.keys(all.rail).length, 0);
  const tr = E.deleteSel(st, sel, "track");
  assert.deepEqual(kinds(tr), kinds(st)); assert.equal(Object.keys(tr.rail).length, 0);
  const mc = E.deleteSel(st, sel, "machines");
  assert.deepEqual(kinds(mc), ["entry", "stocker"]); assert.equal(Object.keys(mc.rail).length, 7);
  const inf = E.deleteSel(st, sel, "infra");
  assert.deepEqual(kinds(inf), ["group"]);
  assert.equal(st.blocks.length, 3, "the old floor is unchanged");
});

test("SE6 a pasted machine with no unplaced group of its kind becomes more machines of its own group", () => {
  const st = floor();
  const clip = E.copySel(st, { blocks: [1], rails: [] });
  const p = E.pasteAt(st, clip, 10, 6, {});
  assert.equal(p.ok, true, p.why);
  const g = p.blocks.find((b) => b.kind === "group");
  assert.ok(g, "the machine is placed");
  assert.deepEqual([g.group, g.area, g.count, g.x, g.y], ["L1", "litho", 3, 10, 6]);
  assert.deepEqual(p.skipped, []);
  const q = E.pasteAt(st, clip, 10, 6, { litho: ["L2"] });
  assert.equal(q.blocks.find((b) => b.kind === "group").group, "L2", "an unplaced group is still taken first");
});
// ---------------------------------------------------------------- the page in headless Chrome, with its own helper

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function helper() {
  const port = 8800 + Math.floor(Math.random() * 400);
  const p = spawn(PY, ["-m", "agent.helper", "--port", String(port), "--runs", profileDir("se-runs-")], { cwd: ROOT, stdio: "ignore" });
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
    `--user-data-dir=${profileDir("se-")}`, "about:blank"], { stdio: "ignore" });
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

test("SB1 a drag on empty floor selects: right, wholly inside; left, whatever is touched; Space-drag moves the view", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    // the box's top edge runs through a machine's second row, so dragging left touches it and dragging right does not
    const st = await snap(b), bb = bbox(st), cut = st.blocks.find((z) => z.kind === "group" && z.h > 1), mid = cut.y + 1;
    const A = [bb.x0 - 1, mid], B = [bb.x1 + 1, bb.y1 + 1];
    await drag(b, await cellPt(b, ...A), await cellPt(b, ...B));
    const win = await page(b, "F.selection()");
    const want = E.inBox(st, ...A, ...B);
    assert.deepEqual(sorted(win.blocks), sorted(want.blocks), "to the right: wholly inside");
    await press(b, "Escape", "Escape");
    await drag(b, await cellPt(b, ...B), await cellPt(b, ...A));
    const cross = await page(b, "F.selection()");
    assert.deepEqual(sorted(cross.blocks), sorted(E.inBox(st, ...A, ...B, true).blocks), "to the left: whatever is touched");
    assert.ok(cross.blocks.length > win.blocks.length, "touching takes more");
    await press(b, "Escape", "Escape");
    const v0 = await page(b, "F.view()"), p = await cellPt(b, ...B);
    await b.send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space" });
    await drag(b, p, [p[0] + 60, p[1] + 30]);
    await b.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space" });
    const v1 = await page(b, "F.view()");
    assert.ok(Math.abs(v1.ox - v0.ox - 60) <= 1 && Math.abs(v1.oy - v0.oy - 30) <= 1, `Space-drag moves the view (${v1.ox - v0.ox}, ${v1.oy - v0.oy})`);
    assert.deepEqual((await page(b, "F.selection()")).blocks, [], "and selects nothing");
  } finally { close(); }
});

test("SB2 Shift-click adds and takes away; Alt-drag takes a box away; Cmd-A selects everything; Esc clears", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    const st = await snap(b), [p, q] = st.blocks.filter((z) => z.kind === "group");
    const ctr = (z) => cellPt(b, z.x + (z.w - 1) / 2, z.y + (z.h - 1) / 2);
    await click(b, await ctr(p), MOD.shift);
    await click(b, await ctr(q), MOD.shift);
    assert.deepEqual(sorted((await page(b, "F.selection()")).blocks), sorted([p.id, q.id]));
    await click(b, await ctr(p), MOD.shift);
    assert.deepEqual((await page(b, "F.selection()")).blocks, [q.id], "Shift-click again takes it away");
    await press(b, "a", "KeyA", MOD.meta);
    const all = await page(b, "F.selection()");
    assert.equal(all.blocks.length, st.blocks.length, "every piece"); assert.equal(all.rails.length, Object.keys(st.rail).length, "all the track");
    const bb = bbox(st), mid = Math.floor((bb.y0 + bb.y1) / 2);
    const A = [bb.x0 - 1, mid], B = [bb.x1 + 1, bb.y1 + 1];
    await drag(b, await cellPt(b, ...A), await cellPt(b, ...B), MOD.alt);
    const left = await page(b, "F.selection()"), gone = E.inBox(st, ...A, ...B);
    assert.deepEqual(sorted(left.blocks), sorted(st.blocks.map((z) => z.id).filter((id) => !gone.blocks.includes(id))), "Alt-drag took the box away");
    await press(b, "Escape", "Escape");
    assert.deepEqual(await page(b, "F.selection()"), { blocks: [], rails: [] });
  } finally { close(); }
});

test("SB3 double-click a machine: every block of its group; double-click track: the track joined to it", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    // a second place for the polishing group (part 2)
    const spot = await page(b, "F.freeBeside(2, 2)");
    await b.ev(`document.querySelector('#pal [data-kind="cmp"]').click(), 1`); await sleep(150);
    await click(b, await cellPt(b, spot[0], spot[1]));
    await press(b, "Escape", "Escape");
    const st = await snap(b), cmp = st.blocks.filter((z) => z.kind === "group" && z.area === "cmp");
    assert.equal(cmp.length, 2, "two polishing blocks");
    await click(b, await cellPt(b, cmp[0].x, cmp[0].y), 0, 1);
    await click(b, await cellPt(b, cmp[0].x, cmp[0].y), 0, 2);
    assert.deepEqual(sorted((await page(b, "F.selection()")).blocks), sorted(cmp.map((z) => z.id)));
    const k = Object.keys(st.rail)[0], [rx, ry] = k.split(",").map(Number);
    await click(b, await cellPt(b, rx, ry), 0, 1);
    await click(b, await cellPt(b, rx, ry), 0, 2);
    assert.deepEqual(sorted((await page(b, "F.selection()")).rails), sorted(E.connectedRail(st, k)));
  } finally { close(); }
});

test("SB4 the arrows nudge the selection in one undo step; dragging a selected piece moves it; Cmd-D takes a copy", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    // the whole layout, which has floor around it to move into
    let st = await snap(b);
    await press(b, "a", "KeyA", MOD.meta);
    const all = await page(b, "F.selection()");
    const dirs = [["ArrowRight", 1, 0], ["ArrowLeft", -1, 0], ["ArrowDown", 0, 1], ["ArrowUp", 0, -1]];
    const d = dirs.find(([, dx, dy]) => E.moveSel(st, all, dx, dy).ok);
    assert.ok(d, "a nudge fits somewhere");
    const one = st.blocks[0];
    await press(b, d[0], d[0]);
    let now = (await snap(b)).blocks.find((z) => z.id === one.id);
    assert.deepEqual([now.x, now.y], [one.x + d[1], one.y + d[2]], `${d[0]} nudges one tile`);
    assert.deepEqual((await snap(b)).rail, E.moveSel(st, all, d[1], d[2]).state.rail, "the track moves with it");
    await press(b, "z", "KeyZ", MOD.meta);
    now = (await snap(b)).blocks.find((z) => z.id === one.id);
    assert.deepEqual([now.x, now.y], [one.x, one.y], "one undo puts it back");
    // drag a selected piece by a move that fits
    st = await snap(b);
    await press(b, "a", "KeyA", MOD.meta);
    const sel = await page(b, "F.selection()");
    let mv = null;
    for (let r = 1; r <= 3 && !mv; r++) for (const [dx, dy] of [[r, 0], [-r, 0], [0, r], [0, -r]]) if (!mv && E.moveSel(st, sel, dx, dy).ok) mv = [dx, dy];
    assert.ok(mv, "a move fits somewhere");
    const g = st.blocks.find((z) => z.kind === "group");
    await drag(b, await cellPt(b, g.x, g.y), await cellPt(b, g.x + mv[0], g.y + mv[1]));
    now = (await snap(b)).blocks.find((z) => z.id === g.id);
    assert.deepEqual([now.x, now.y], [g.x + mv[0], g.y + mv[1]], "dragged with the selection");
    assert.equal((await snap(b)).blocks.find((z) => z.id === one.id).x, one.x + mv[0], "and the rest came along");
    await press(b, "d", "KeyD", MOD.meta);
    assert.ok(await page(b, "F.clipboard()"), "Cmd-D copies");
    assert.equal(await page(b, "F.pasting()"), true, "and takes the copy in hand");
  } finally { close(); }
});

test("SB5 R turns the selection and Shift-R mirrors it, as turnSel says, or says why not", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    for (const mirror of [false, true]) {
      const st = await snap(b);
      await press(b, "a", "KeyA", MOD.meta);
      const sel = await page(b, "F.selection()"), want = E.turnSel(st, sel, mirror);
      await press(b, mirror ? "R" : "r", "KeyR", mirror ? MOD.shift : 0);
      const after = await snap(b);
      if (want.ok) {
        assert.deepEqual(after.blocks.map((z) => [z.id, z.x, z.y, z.w, z.h]), want.state.blocks.map((z) => [z.id, z.x, z.y, z.w, z.h]), `${mirror ? "mirror" : "turn"}: pieces`);
        assert.deepEqual(after.rail, want.state.rail, `${mirror ? "mirror" : "turn"}: track`);
      } else {
        assert.deepEqual(after, st, "nothing changes");
        assert.ok((await b.ev(`document.getElementById("status").textContent`)).length > 5, "the status says why");
      }
      await press(b, "Escape", "Escape");
    }
    assert.equal(E.turnSel(await snap(b), { blocks: [], rails: [] }, true).ok, true);
  } finally { close(); }
});

test("SB6 with everything selected, Selected sets every machine group's breakdowns; only the track deletes only track", { skip: SKIP }, async () => {
  const { b, close } = await openEditor();
  try {
    const st = await snap(b);
    await press(b, "a", "KeyA", MOD.meta);
    await b.ev(`document.querySelector('#ctl-tabs [data-tab="sel"]').click(), 1`); await sleep(150);
    const txt = await b.ev(`document.getElementById("insp").innerText`);
    const groups = st.blocks.filter((z) => z.kind === "group").length;
    assert.match(txt, new RegExp(`${groups} machine`), "Selected says what is in the selection");
    await b.ev(`(() => { const s = document.getElementById("bulk-fail"); s.value = "none"; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(200);
    const after = await snap(b);
    for (const z of after.blocks.filter((y) => y.kind === "group")) assert.deepEqual(z.fail, { kind: "none" }, `${z.group}: breakdowns set`);
    await b.ev(`document.querySelector('#insp [data-del="track"]').click(), 1`); await sleep(200);
    const cut = await snap(b);
    assert.equal(Object.keys(cut.rail).length, 0, "the track is gone");
    assert.deepEqual(cut.blocks.map((z) => z.id), after.blocks.map((z) => z.id), "every piece stays");
  } finally { close(); }
});
