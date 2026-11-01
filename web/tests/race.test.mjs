// Race the AI (docs/RACE-AI.md): Muse Wonder plays a challenge through the editor's own moves. Written before the code.
// The helper answers from recorded games (--stand-in), so no model is called and nothing is spent. On a teaching fab of
// our own; not a real fab.
//
//     node --test web/tests/race.test.mjs   (needs Google Chrome and the .venv)

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

async function openWith(game) {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--no-model", "--runs", mkdtempSync(join(tmpdir(), "test-runs-")), "--port", String(hp), "--stand-in", join(HERE, "fixtures", game)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("race-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const until = async (expr, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await ev(expr)) return true; } catch { /* busy */ } await sleep(80); } return false; };
  await send("Page.enable");
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/editor.html` });
  await until("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)");
  await sleep(500);
  return { ev, send, until, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}
const J = async (p, expr) => JSON.parse(await p.ev(`JSON.stringify(${expr})`));

test("RA6 the AI plays challenge 1: its moves and reasons in the panel, the break routed round, a star", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openWith("race-ok");
  try {
    assert.equal(await J(p, `(FabEditorPage.railAt(3, 6) || {}).rec && FabEditorPage.railAt(3, 6).rec.kind`), "wait", "cars wait at first");
    await p.ev(`document.getElementById("ai-go").click()`);
    assert.ok(await p.until(`!document.getElementById("ai-panel").hidden`, 3000), "the panel opens");
    assert.ok(await p.until(`/ended|stopped|three stars/i.test(document.getElementById("ai-status").textContent)`, 20000), "the game ends");
    const moves = await J(p, `[...document.querySelectorAll("#ai-moves .ai-move")].map((m) => m.textContent)`);
    assert.ok(moves.length >= 3, `moves: ${moves.length}`);
    assert.match(moves[0], /look/); assert.match(moves[0], /read the map/);
    assert.match(moves[1], /set_when_it_breaks|routes? round|route_around/i);
    assert.match(moves[2], /run/);
    assert.equal(await J(p, `FabEditorPage.railAt(3, 6).rec.kind`), "route_around", "the break is routed round");
    assert.ok(await p.until(`!document.getElementById("win").hidden || /★/.test(document.getElementById("ai-panel").textContent)`, 5000), "a star");
    const panel = await p.ev(`document.getElementById("ai-panel").textContent`);
    assert.match(panel, /stand-in/i); assert.match(panel, /\$0\.00/);
  } finally { p.close(); }
});

test("RA7 an unknown tool is refused with a line in the panel, and the game still ends", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openWith("race-bad");
  try {
    await p.ev(`document.getElementById("ai-go").click()`);
    assert.ok(await p.until(`/ended|stopped/i.test(document.getElementById("ai-status").textContent)`, 15000), "the game ends");
    assert.match(await p.ev(`document.getElementById("ai-moves").textContent`), /refused|unknown/i);
  } finally { p.close(); }
});

test("RA8 one undo after the game takes back the AI's last change", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openWith("race-ok");
  try {
    await p.ev(`document.getElementById("ai-go").click()`);
    assert.ok(await p.until(`/ended|stopped|three stars/i.test(document.getElementById("ai-status").textContent)`, 20000));
    await p.ev(`document.getElementById("win").hidden = true`);
    await p.send("Input.dispatchKeyEvent", { type: "keyDown", key: "z", code: "KeyZ", modifiers: 2, windowsVirtualKeyCode: 90 });
    await p.send("Input.dispatchKeyEvent", { type: "keyUp", key: "z", code: "KeyZ", modifiers: 2 });
    await sleep(200);
    assert.equal(await J(p, `FabEditorPage.railAt(3, 6).rec.kind`), "wait");
  } finally { p.close(); }
});
