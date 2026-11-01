// Sketch to fab (docs/SKETCH.md). Written before the code. The helper answers from a recorded reading (--stand-in), so
// no model is called and nothing is spent. On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/sketch.test.mjs   (needs Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, rmSync as rmProfile } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
const PROFILES = [];
const profileDir = (prefix) => { const d = mkdtempSync(join(tmpdir(), prefix)); PROFILES.push(d); return d; };
process.on("exit", () => { for (const d of PROFILES) { try { rmProfile(d, { recursive: true, force: true }); } catch { /* already gone */ } } });

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");
const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function open() {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp), "--stand-in", join(HERE, "fixtures", "sketch")], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("sketch-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const until = async (expr, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await ev(expr)) return true; } catch { /* busy */ } await sleep(80); } return false; };
  await send("Page.enable"); await send("DOM.enable");
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/editor.html` });
  await until("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)");
  await sleep(400);
  const pick = async (file) => {
    const doc = await send("DOM.getDocument", {});
    const q = await send("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#sketch-file" });
    await send("DOM.setFileInputFiles", { nodeId: q.nodeId, files: [file] });
  };
  return { ev, until, pick, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}
const J = async (p, e) => JSON.parse(await p.ev(`JSON.stringify(${e})`));

test("SK5 a picture becomes a fab in Free build, with a panel naming what was read", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open();
  try {
    await p.pick(join(HERE, "fixtures", "sketch", "drawing.png"));
    assert.ok(await p.until(`!document.getElementById("sketch-panel").hidden && /Lithography/.test(document.getElementById("sketch-panel").textContent)`, 15000), "the panel");
    const panel = await p.ev(`document.getElementById("sketch-panel").textContent`);
    assert.match(panel, /Polishing/); assert.match(panel, /coffee/); assert.match(panel, /stand-in/);
    assert.match(await p.ev(`document.getElementById("cheye").textContent`), /Free build/);
    const blocks = await J(p, "FabEditorPage.blocks()");
    assert.deepEqual(blocks.filter((b) => b.kind === "group").map((b) => b.area).sort(), ["cmp", "litho"]);
    assert.ok((await J(p, "FabEditorPage.railKeys()")).length >= 8, "track laid");
  } finally { p.close(); }
});

test("SK6 Discard puts back the layout from before", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open();
  try {
    await p.ev(`[...document.querySelectorAll("#chtabs .tab")].pop().click()`);
    await p.until(`/Free build/.test(document.getElementById("cheye").textContent)`, 8000);
    await sleep(500);
    const before = await J(p, "({ blocks: FabEditorPage.blocks().length, rails: FabEditorPage.railKeys().length, size: FabEditorPage.size() })");
    await p.pick(join(HERE, "fixtures", "sketch", "drawing.png"));
    assert.ok(await p.until(`!document.getElementById("sketch-discard").hidden`, 15000), "the sketch is built");
    await p.ev(`document.getElementById("sketch-discard").click()`);
    await sleep(300);
    const after = await J(p, "({ blocks: FabEditorPage.blocks().length, rails: FabEditorPage.railKeys().length, size: FabEditorPage.size() })");
    assert.deepEqual(after, before);
  } finally { p.close(); }
});

test("SK8 when the checks fail after a sketch, the old run is no longer drawn on the new floor", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open();
  try {
    assert.equal(await p.ev("FabEditorPage.showsRun()"), true, "a run is on screen before");
    await p.pick(join(HERE, "fixtures", "sketch", "drawing.png"));
    assert.ok(await p.until(`!document.getElementById("sketch-discard").hidden`, 15000), "the sketch is built");
    assert.ok(await p.until(`document.querySelectorAll("#issues .fix, #issues [data-sev=fix]").length > 0 || /FIX/i.test(document.getElementById("issues").textContent)`, 8000), "the checks fail");
    await sleep(800);
    assert.equal(await p.ev("FabEditorPage.showsRun()"), false, "the old run is out of date");
    assert.equal(await p.ev("FabEditorPage.cars()"), 0, "no cars from the old run");
    assert.equal(await p.ev(`document.getElementById("again").hidden`), true, "no Run again while the checks fail");
    assert.equal(await p.ev(`document.querySelectorAll("#score .sc.stale").length`), 3, "the score cards look out of date");
    assert.match(await p.ev(`document.getElementById("score").textContent`), /before your changes/);
    assert.doesNotMatch(await p.ev(`document.getElementById("goaltext").textContent`), /on your layout/);
  } finally { p.close(); }
});
