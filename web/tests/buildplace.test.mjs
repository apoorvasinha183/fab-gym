// Build: placing machines, part 2 (docs/BUILD-CONTROLS.md). Written before the code. On a teaching fab of our own,
// built from the SMT2020 testbed's shapes; not a real fab.
//
//     node --test web/tests/buildplace.test.mjs   (needs Google Chrome and the .venv)

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
    `--user-data-dir=${profileDir("bp-")}`, "about:blank"], { stdio: "ignore" });
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


// one machine-sized spot beside the track, free, and a row of them for a fill
const spot = (b) => page(b, "F.freeBeside(2, 2)");
const clickAt = async (b, x, y, modifiers = 0) => { const [sx, sy] = await page(b, `F.screenOf(${x}, ${y})`); await b.mouse("mouseMoved", sx, sy, { modifiers }); await b.mouse("mousePressed", sx, sy, { modifiers }); await b.mouse("mouseReleased", sx, sy, { modifiers }); await sleep(150); };
const group = (b, g) => page(b, `F.blocks().filter(z => z.kind === "group" && z.group === ${JSON.stringify(g)})`);
const total = async (b, g) => (await group(b, g)).reduce((a, z) => a + z.count, 0);
/** The fab file's facts for a group: its count, its stations and its stops' machine numbers. */
const fileOf = async (b, g) => {
  const t = await page(b, "F.fab()");
  const lines = t.split("\n").map((l) => l.split("\t"));
  const grp = lines.find((f) => f[0] === "group" && f[1] === g);
  return { count: grp ? +grp[2] : null, stations: lines.filter((f) => f[0] === "station" && f[1] === g).length,
    stops: lines.filter((f) => f[0] === "stop" && f[1] === g).map((f) => +f[2]).sort((a, c) => a - c) };
};

test("BP1 a machine from the palette is in hand and its controls open; Esc puts it down", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await b.ev(`document.querySelector('#pal [data-kind="dry"]').click(), 1`); await sleep(150);
    assert.equal(await page(b, "F.tool()"), "dry", "dry etch in hand");
    assert.match(await b.ev(`document.getElementById("insp").innerText`), /Dry etch/, "its controls open");
    await b.key("Escape", "Escape"); await sleep(100);
    assert.equal(await page(b, "F.tool()"), "select", "Esc puts it down");
  } finally { close(); }
});

test("BP2 BP3 a click places one machine where it is clicked; on its own kind, one more there", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    const g = "Dry_Etch_T", t0 = await total(b, g), n0 = (await group(b, g)).length;
    const [x, y] = await spot(b);
    await b.ev(`document.querySelector('#pal [data-kind="dry"]').click(), 1`); await sleep(100);
    await clickAt(b, x, y);
    const blocks = await group(b, g);
    assert.equal(blocks.length, n0 + 1, "a new block of the group");
    assert.ok(blocks.some((z) => z.x === x && z.y === y && z.count === 1), "with one machine, where it was clicked");
    assert.equal(await total(b, g), t0 + 1, "the group's total rises by one");
    let f = await fileOf(b, g);
    assert.equal(f.count, t0 + 1, "the fab file counts the group's machines across its blocks");
    assert.equal(f.stations, n0 + 1, "a station per block");
    assert.deepEqual(f.stops, Array.from({ length: t0 + 1 }, (_, i) => i), "a stop per machine, numbered once");
    // on a block of the same kind: one more there, no new block
    await clickAt(b, x, y);
    assert.equal((await group(b, g)).length, n0 + 1, "no new block");
    assert.equal(await total(b, g), t0 + 2, "one more machine");
    f = await fileOf(b, g);
    assert.equal(f.count, t0 + 2);
    assert.deepEqual(f.stops, Array.from({ length: t0 + 2 }, (_, i) => i));
  } finally { close(); }
});

test("BP4 Shift-drag fills free spots beside the track, and one undo takes them all", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    const g = "Wet_Etch_T", t0 = await total(b, g), n0 = (await group(b, g)).length;
    const row = await page(b, "F.freeRowBeside(3)"); // three free machine spots in a row beside the track
    assert.ok(row && row.length === 3, `three spots: ${JSON.stringify(row)}`);
    await b.ev(`document.querySelector('#pal [data-kind="wet"]').click(), 1`); await sleep(100);
    const pts = [];
    for (const [x, y] of row) pts.push(await page(b, `F.screenOf(${x}, ${y})`));
    await b.mouse("mouseMoved", pts[0][0], pts[0][1], { modifiers: 8 }); await b.mouse("mousePressed", pts[0][0], pts[0][1], { modifiers: 8 });
    for (const [px, py] of pts.slice(1)) { await b.mouse("mouseMoved", px, py, { buttons: 1, modifiers: 8 }); await sleep(40); }
    await b.mouse("mouseReleased", pts[2][0], pts[2][1], { modifiers: 8 }); await sleep(200);
    assert.equal((await group(b, g)).length, n0 + 3, "a machine at each spot along the drag");
    assert.equal(await total(b, g), t0 + 3);
    await b.key("z", "KeyZ", 2); await sleep(200);
    assert.equal((await group(b, g)).length, n0, "one undo takes the fill away");
    assert.equal(await total(b, g), t0);
  } finally { close(); }
});

test("BP5 a group's breakdown settings are the group's; spending counts each machine and the spares once", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    const g = "Litho_T";
    const first = (await group(b, g))[0];
    // the first block breaks at random and swaps in a spare
    await page(b, `F.select(${first.id})`); await sleep(100);
    await b.ev(`(() => { const s = document.getElementById("fsel"); s.value = "random"; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(100);
    await b.ev(`(() => { const s = document.getElementById("rsel"); s.value = "swap_to_spare"; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(100);
    const spend0 = await page(b, "F.spend()");
    const [x, y] = await spot(b);
    await b.ev(`document.querySelector('#pal [data-kind="litho"]').click(), 1`); await sleep(100);
    await clickAt(b, x, y);
    const blocks = await group(b, g);
    assert.equal(blocks.length, 2);
    for (const z of blocks) {
      assert.equal(z.fail && z.fail.kind, "random", "the new block takes its group's breakdowns");
      assert.equal(z.rec && z.rec.kind, "swap_to_spare", "and its recovery");
    }
    assert.equal(await page(b, "F.spend()") - spend0, 60e6, "one more machine at its price; the spares counted once");
    // changing them on the new block changes them on both
    const nb = blocks.find((z) => z.id !== first.id);
    await page(b, `F.select(${nb.id})`); await sleep(100);
    await b.ev(`(() => { const s = document.getElementById("fsel"); s.value = "none"; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(100);
    for (const z of await group(b, g)) assert.equal(z.fail && z.fail.kind, "none", "both blocks changed");
    const ov = await page(b, "F.overrides()");
    assert.equal(Object.keys(ov.groups).filter((k) => k === g).length, 1, "one entry for the group");
  } finally { close(); }
});

test("BP6 one group in two places passes the checks and runs, counting all its machines", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    const g = "Planar_T", t0 = await total(b, g);
    const [x, y] = await spot(b);
    const r0 = await page(b, "F.runs()");
    await b.ev(`document.querySelector('#pal [data-kind="cmp"]').click(), 1`); await sleep(100);
    await clickAt(b, x, y);
    for (let i = 0; i < 300 && (await page(b, "F.runs()")) <= r0; i++) await sleep(100);
    assert.ok((await page(b, "F.runs()")) > r0, "the layout ran");
    const c = await page(b, "F.checks()");
    assert.ok(c && c.ok, `the layout checks pass: ${JSON.stringify(c && c.issues)}`);
    assert.equal((await fileOf(b, g)).count, t0 + 1, "the run's fab file counts the group's machines");
  } finally { close(); }
});
