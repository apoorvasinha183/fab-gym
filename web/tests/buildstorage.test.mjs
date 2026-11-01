// Build: storage made real, part 3 (docs/BUILD-CONTROLS.md). Written before the code. On a teaching fab of our own,
// built from the SMT2020 testbed's shapes; not a real fab.
//
//     node --test web/tests/buildstorage.test.mjs   (needs Google Chrome and the .venv)

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
    `--user-data-dir=${profileDir("bs-")}`, "about:blank"], { stdio: "ignore" });
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
const portsLine = async (b) => { const m = /^inports\t(\d+)$/m.exec(await page(b, "F.fab()")); return m ? +m[1] : null; };
const setPorts = async (b, v) => {
  await b.ev(`document.querySelector('#ctl-tabs [data-tab="fab"]').click(), 1`); await sleep(150);
  await b.ev(`(() => { const s = document.getElementById("ctl-fab-ports"); s.value = ${JSON.stringify(v)}; s.dispatchEvent(new Event("change")); return 1; })()`); await sleep(200);
};

test("BS1 Free build's fab file has two load ports a machine; no challenge's has a limit", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    for (let k = 0; k < 4; k++) {
      if (k) await toTab(b, k);
      assert.equal(await portsLine(b), null, `challenge ${k + 1}: no port limit`);
    }
    await toTab(b, 4);
    assert.equal(await portsLine(b), 2, "Free build: inports 2");
  } finally { close(); }
});

test("BS2 Load ports per machine sets the line; in a challenge a limit is an experiment with no stars", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    await toTab(b, 4);
    await b.ev(`document.querySelector('#ctl-tabs [data-tab="fab"]').click(), 1`); await sleep(150);
    const opts = await b.ev(`[...document.querySelectorAll("#ctl-fab-ports option")].map(o => o.textContent.trim())`);
    assert.deepEqual(opts, ["Unlimited", "1", "2", "3", "4"]);
    await setPorts(b, "3");
    assert.equal(await portsLine(b), 3);
    await setPorts(b, "");
    assert.equal(await portsLine(b), null, "Unlimited writes no line");
    // in challenge 2, a limit makes the run an experiment: no stars, and the page says why
    await toTab(b, 1);
    const r0 = await page(b, "F.runs()");
    await setPorts(b, "2");
    assert.equal(await portsLine(b), 2);
    await until(b, `FabEditorPage.runs() > ${r0}`, 20000);
    assert.equal(await page(b, "F.experiment()"), true, "the run is an experiment");
    assert.equal(await page(b, "F.starsNow()"), 0, "no stars");
    assert.match(await b.ev(`document.querySelector(".banner").innerText`), /experiment/i, "the banner says it is an experiment");
  } finally { close(); }
});

test("BS3 Storage says what it does, and that nothing waits there with unlimited ports", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const { b, close } = await openEditor();
  try {
    const store = await page(b, `F.blocks().find(z => z.kind === "stocker")`);
    assert.ok(store, "the teaching fab has storage");
    await page(b, `F.select(${store.id})`); await sleep(150);
    let t = await b.ev(`document.getElementById("insp").innerText`);
    assert.match(t, /ports are full/i, "what it does");
    assert.match(t, /nothing waits here/i, "challenge 1 has unlimited ports");
    await toTab(b, 4);
    const s2 = await page(b, `F.blocks().find(z => z.kind === "stocker")`);
    await page(b, `F.select(${s2.id})`); await sleep(150);
    t = await b.ev(`document.getElementById("insp").innerText`);
    assert.match(t, /ports are full/i);
    assert.doesNotMatch(t, /nothing waits here/i, "Free build has a limit, so lots may wait here");
  } finally { close(); }
});
