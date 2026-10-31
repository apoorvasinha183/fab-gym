// The editor, top down (docs/EDITOR-TOPDOWN.md): straight down, Factorio tiles, engraved icons, no text on the map,
// raised keys; the map fits the window (D7, D8). Written before the code. On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/editortop.test.mjs   (from the repo root; D2 to D6 need Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync } from "node:fs";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const require = createRequire(import.meta.url);
const E = require(join(HERE, "..", "editor-core.js"));
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");

const rgb = (c) => {
  const m = c.match(/rgba?\(([^)]+)\)/);
  if (m) return m[1].split(",").map((x) => parseFloat(x));
  const n = parseInt(c.slice(1), 16);
  return [n >> 16, (n >> 8) & 255, n & 255, 1];
};
const lum = ([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

test("D1 an engraved icon: a cut darker than the tile and a light see-through line", () => {
  for (const c of ["#F2B33D", "#3FD0C4", "#5FA8FF", "#C9D3DA"]) {
    const e = E.engrave(c);
    assert.ok(lum(rgb(e.cut)) < lum(rgb(c)) * 0.6, `${c}: the cut ${e.cut} is clearly darker`);
    const l = rgb(e.light);
    assert.ok(l[0] === 255 && l[1] === 255 && l[2] === 255 && l[3] > 0 && l[3] < 1, `${c}: the line ${e.light} is see-through white`);
  }
});

// ---------------------------------------------------------------- headless Chrome, a helper of its own

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openEditor(size = "1440,1000") {
  const hp = 8800 + Math.floor(Math.random() * 600);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, `--window-size=${size}`, "--hide-scrollbars", `--user-data-dir=${mkdtempSync(join(tmpdir(), "top-"))}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  await send("Page.enable");
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/editor.html` });
  for (let i = 0; i < 200; i++) { await sleep(50); if (await ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
  return { ev, send, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}

test("D2 straight down: a step right moves only across, a step down only down, by the same distance", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const [a, b, c] = JSON.parse(await p.ev("JSON.stringify([FabEditorPage.screenOf(3, 3), FabEditorPage.screenOf(4, 3), FabEditorPage.screenOf(3, 4)])"));
    assert.ok(Math.abs(b[1] - a[1]) < 0.01 && b[0] - a[0] > 5, `right: ${b[0] - a[0]} across, ${b[1] - a[1]} down`);
    assert.ok(Math.abs(c[0] - a[0]) < 0.01 && c[1] - a[1] > 5, `down: ${c[0] - a[0]} across, ${c[1] - a[1]} down`);
    assert.ok(Math.abs((b[0] - a[0]) - (c[1] - a[1])) < 0.01, "square tiles");
  } finally { p.close(); }
});

test("D3 no text is drawn on the map while it plays", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    await p.ev(`(() => { window.__texts = []; const f = CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText = function (t, ...r) { if (this.canvas.id === "map") window.__texts.push(String(t)); return f.call(this, t, ...r); }; })()`);
    await sleep(1500);
    const texts = JSON.parse(await p.ev("JSON.stringify([...new Set(window.__texts)])"));
    const notices = ["Updating the run with your changes…", "Your changes run as soon as the checks pass."];
    assert.deepEqual(texts.filter((t) => !notices.includes(t)), [], `text on the map: ${texts.join(" | ")}`);
  } finally { p.close(); }
});

test("D4 in challenge 1, a free 3 × 4 patch can now be pointed at", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    assert.notEqual(await p.ev("JSON.stringify(FabEditorPage.firstFree(3, 4))"), "null");
  } finally { p.close(); }
});

test("D5 pointing at a machine tile shows its hover card with its name", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const m = JSON.parse(await p.ev("JSON.stringify(FabEditorPage.blocks().find((b) => b.kind === 'group'))"));
    const [x, y] = JSON.parse(await p.ev(`JSON.stringify(FabEditorPage.screenOf(${m.x}, ${m.y}))`));
    await p.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await sleep(200);
    const card = JSON.parse(await p.ev(`JSON.stringify({ shown: !document.getElementById("hover").hidden, text: document.getElementById("hover").textContent })`));
    assert.ok(card.shown, "the hover card shows");
    assert.ok(card.text.length > 3, `it names the group: ${card.text.slice(0, 80)}`);
  } finally { p.close(); }
});

test("D6 raised keys: palette buttons raised, the chosen one pressed; play raised", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const o = JSON.parse(await p.ev(`JSON.stringify({
      up: getComputedStyle(document.querySelector('#pal button[aria-pressed="false"]')).boxShadow,
      down: getComputedStyle(document.querySelector('#pal button[aria-pressed="true"]')).boxShadow,
      play: getComputedStyle(document.getElementById("play")).boxShadow })`));
    assert.ok(o.up !== "none" && !/inset/.test(o.up), `a raised palette button: ${o.up}`);
    assert.match(o.down, /inset/, `the chosen one pressed: ${o.down}`);
    assert.ok(o.play !== "none" && !/^inset/.test(o.play), `play raised: ${o.play}`);
  } finally { p.close(); }
});

// ---------------------------------------------------------------- the map fits the window (the founder: "make the figure compact")

const WHOLE = `JSON.stringify((() => { const [W, H] = FabEditorPage.size(), a = FabEditorPage.screenOf(-0.5, -0.5), b = FabEditorPage.screenOf(W - 0.5, H - 0.5),
  r = document.getElementById("map").getBoundingClientRect();
  return { a, b, map: [r.left, r.top, r.right, r.bottom], inner: innerHeight }; })())`;

test("D7 on a 1440 x 900 screen the whole map shows without scrolling, the whole floor inside it", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor("1440,900");
  try {
    const o = JSON.parse(await p.ev(WHOLE));
    assert.ok(o.map[3] <= o.inner + 0.5, `the map ends at ${o.map[3]}, the window at ${o.inner}`);
    const inside = (q) => q[0] >= o.map[0] - 0.5 && q[0] <= o.map[2] + 0.5 && q[1] >= o.map[1] - 0.5 && q[1] <= o.map[3] + 0.5;
    assert.ok(inside(o.a) && inside(o.b), `the floor's corners ${o.a} and ${o.b} sit inside the map ${o.map}`);
    const [a, b, c] = JSON.parse(await p.ev("JSON.stringify([FabEditorPage.screenOf(3, 3), FabEditorPage.screenOf(4, 3), FabEditorPage.screenOf(3, 4)])"));
    assert.ok(Math.abs((b[0] - a[0]) - (c[1] - a[1])) < 0.01, "tiles stay square");
  } finally { p.close(); }
});

test("D8 in a short window the map keeps a usable height of at least 360 px", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor("1440,640");
  try {
    const o = JSON.parse(await p.ev(WHOLE));
    assert.ok(o.map[3] - o.map[1] >= 359.5, `the map is ${o.map[3] - o.map[1]} px tall`);
    assert.ok(o.b[1] - o.a[1] >= 300, `the floor is ${o.b[1] - o.a[1]} px tall`);
  } finally { p.close(); }
});
