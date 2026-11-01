// The last star's hint (docs/THIRD-STAR.md). Written before the code. On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/thirdstar.test.mjs   (TS3 needs Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
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
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// the page's pure parts, as the other editor tests load them
const E = createRequire(import.meta.url)(join(HERE, "..", "editor-core.js"));
const TIP = "try a cap on the lots inside";

test("TS1 the advice names the stars and gives the tip until the third", () => {
  const tip = "try a cap on the lots inside (click empty floor, then Cap on lots inside).";
  const one = E.advise({ brokenJam: false, worst: null, met: true, stars: 1, tip });
  const two = E.advise({ brokenJam: false, worst: null, met: true, stars: 2, tip });
  const three = E.advise({ brokenJam: false, worst: null, met: true, stars: 3, tip });
  assert.match(one, /One star/); assert.ok(one.includes(tip));
  assert.match(two, /Two stars/); assert.ok(two.includes(tip));
  assert.match(three, /Three stars/); assert.ok(!three.includes(tip));
  assert.match(E.advise({ brokenJam: false, worst: null, met: true, stars: 2 }), /met/i, "no tip: today's line");
});

test("TS2 the three challenges that need the cap carry the tip; Breakdown, no spare does not", () => {
  const by = Object.fromEntries(E.CHALLENGES.map((c) => [c.id, c]));
  for (const id of ["rush", "polisher", "lean"]) assert.ok(by[id].tip && by[id].tip.includes(TIP), `${id} has the tip`);
  assert.ok(!by.breakdown.tip, "breakdown needs none");
});

async function openEditor() {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--port", String(hp)], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html?ch=2`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("star-")}`, "about:blank"], { stdio: "ignore" });
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
  await send("Page.navigate", { url: `http://127.0.0.1:${hp}/editor.html?ch=2` });
  for (let i = 0; i < 200; i++) { await sleep(50); if (await ev("!!(window.FabEditorPage && FabEditorPage.runs() >= 1)")) break; }
  return { ev, send, mouse, key, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}

test("TS3 on the gassed polisher: two stars show the tip, the cap's third star takes it away", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await openEditor();
  try {
    const run = async (expr) => {
      const n = await p.ev("FabEditorPage.runs()");
      await p.ev(`(async () => JSON.stringify(await (${expr})))()`);
      for (let i = 0; i < 300; i++) { await sleep(100); if ((await p.ev("FabEditorPage.runs()")) > n) break; }
      await sleep(400);
      return JSON.parse(await p.ev(`(async () => JSON.stringify({ look: await FabEditorTools.call("look", {}), advice: document.getElementById("advice").textContent }))()`));
    };
    const two = await run(`FabEditorTools.call("set_machines", { group: "Planar_T", count: 2 })`);
    assert.equal(two.look.stars, 2, "two polishers: two stars");
    assert.ok(two.advice.includes(TIP), `the tip shows: ${two.advice}`);
    const three = await run(`FabEditorTools.call("set_cap", { lots: 20 })`);
    assert.equal(three.look.stars, 3, "a cap of 20: three stars");
    assert.ok(!three.advice.includes(TIP), `no tip at three stars: ${three.advice}`);
  } finally { p.close(); }
});
