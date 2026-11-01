// Ask the glossary, part 3 (docs/GLOSSARY-PLUS.md: GE6, GE7). Written before the code. The helper runs with --no-model:
// a recorded reply stands in for Muse Spark, so nothing is spent. On the SMT2020 testbed; not a real fab.
//
//     node --test web/tests/glossaryask.test.mjs   (needs Google Chrome and the .venv)

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
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = join(ROOT, ".venv", "bin", "python");

// ---------------------------------------------------------------- the page in headless Chrome, with its own helper

const ready = existsSync(CHROME) && existsSync(PY);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function helper(extra = []) {
  const port = 8800 + Math.floor(Math.random() * 400);
  const p = spawn(PY, ["-m", "agent.helper", "--no-model", "--port", String(port), "--runs", profileDir("ga-runs-"), ...extra], { cwd: ROOT, stdio: "ignore" });
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
    `--user-data-dir=${profileDir("ga-")}`, "about:blank"], { stdio: "ignore" });
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

const SKIP = !ready && "needs Google Chrome and the .venv";

const STAND_IN = join(HERE, "fixtures", "glossary");
const QUESTION = "Why do lots wait so long at the polisher?";
async function floorWith(extra) {
  const h = await helper(extra);
  const b = await chrome();
  await b.send("Page.enable");
  await b.send("Page.navigate", { url: `http://127.0.0.1:${h.port}/index.html?run=3#floor` });
  for (let i = 0; i < 300; i++) { await sleep(100); if (await b.ev(`document.body && document.body.dataset.floor === "full"`)) break; }
  await b.ev(`window.FabFloorPage.openGlossary("Lot"), 1`); await sleep(300);
  const api = async (q) => (await fetch(`http://127.0.0.1:${h.port}/api/glossary/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) })).json();
  const ask = async (q) => {
    // the Floor's one question bar (web/tests/cleanup.test.mjs 1): a question about what something means goes to the glossary
    await b.ev(`(() => { const i = document.getElementById("cmd-q"); i.value = ${JSON.stringify(q)}; document.getElementById("cmd").requestSubmit(); return 1; })()`);
    for (let i = 0; i < 100; i++) { await sleep(100); if (await b.ev(`!!document.querySelector("#gl-answer .gl-ans-foot")`)) break; }
  };
  return { b, api, ask, close: () => { b.close(); h.close(); } };
}

test("GE6 a recorded reply: links for the cited entries only, each opening its article, and it cost nothing", { skip: SKIP }, async () => {
  const { b, api, ask, close } = await floorWith(["--stand-in", STAND_IN]);
  try {
    const want = await api(QUESTION);
    assert.ok(want.cites && want.cites.length, JSON.stringify(want));
    await ask(QUESTION);
    const cites = await b.ev(`[...document.querySelectorAll("#gl-answer .gl-ans-text [data-term]")].map(x => x.dataset.term)`);
    assert.deepEqual(cites, want.cites, "a link for each cited entry");
    for (const c of cites) assert.ok(want.entries.includes(c), `${c} was among the entries sent`);
    assert.match(await b.ev(`document.querySelector("#gl-answer .gl-ans-text").innerText`), /Polisher queue law/, "the made-up citation's words stay");
    assert.ok(!cites.includes("Polisher queue law"), "without a link");
    assert.match(await b.ev(`document.querySelector("#gl-answer .gl-ans-foot").innerText`), /recorded reply/i);
    assert.match(await b.ev(`document.querySelector("#gl-answer .gl-ans-foot").innerText`), /\$0(\.0+)?\b/);
    await b.ev(`document.querySelector("#gl-answer .gl-ans-text [data-term]").click(), 1`); await sleep(250);
    assert.equal(await b.ev(`document.querySelector("#gl-article h3").textContent`), cites[0], "a link opens its article");
  } finally { close(); }
});

test("GE7 with no model, the box lists the closest entries and says so", { skip: SKIP }, async () => {
  const { b, api, ask, close } = await floorWith([]);
  try {
    const want = await api(QUESTION);
    assert.ok(want.no_model, JSON.stringify(want));
    await ask(QUESTION);
    const listed = await b.ev(`[...document.querySelectorAll("#gl-answer .gl-ans-entries [data-term]")].map(x => x.dataset.term)`);
    assert.deepEqual(listed, want.entries);
    assert.match(await b.ev(`document.getElementById("gl-answer").innerText`), /no model/i);
  } finally { close(); }
});

test("GE8 the Floor's bar sends a question about meaning to the glossary and a what-if to the simulator", () => {
  const require2 = createRequire(import.meta.url);
  const A = require2(join(HERE, "..", "ask.js"));
  for (const q of ["What's a WIP cap?", "What does cycle time mean?", "Why do lots wait so long at the polisher?", "Explain rework", "How does a batch work?"])
    assert.equal(A.wordQuestion(q), true, q);
  for (const q of ["What if breakdowns double?", "Prototype orders double next quarter. Do we give them their own wing or put them first in line?",
    "Polisher group Planar_FE_79 is down for a shift tomorrow morning. Which dispatch rule should we run?",
    "If breakdowns get 50% worse, does holding prototype lots at the door protect the volume product?", "Would a second polisher help?"])
    assert.equal(A.wordQuestion(q), false, q);
});
