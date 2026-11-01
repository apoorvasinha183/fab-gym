// The demo path (docs/SUBMISSION.md): the three-minute walk through the live product, clicked end to end, so the demo
// cannot break without a test failing. Written before the pack. On the SMT2020 testbed and a teaching fab of our own; not
// a real fab. No model is called and no credit is spent.
//
//     node --test web/tests/demopath.test.mjs   (needs Google Chrome and the .venv)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, rmSync as rmProfile } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
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

test("the demo path, clicked end to end", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const hp = 8800 + Math.floor(Math.random() * 400);
  const helper = spawn(PY, ["-m", "agent.helper", "--no-model", "--port", String(hp), "--runs", mkdtempSync(join(tmpdir(), "fg-runs-")), "--quick"], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/index.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,900", "--hide-scrollbars", `--user-data-dir=${profileDir("demo-")}`, "about:blank"], { stdio: "ignore" });
  let ws = null;
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${cp}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch { /* not up */ } if (!ws) await sleep(200); }
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const wait = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d.result); wait.delete(d.id); } };
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.value;
  const until = async (expr, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await ev(expr)) return true; } catch { /* busy */ } await sleep(80); } return false; };
  const go = async (path) => { await send("Page.navigate", { url: `http://127.0.0.1:${hp}/${path}` }); await sleep(300); };
  const key = async (k, code) => { await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code }); await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code }); };
  try {
    await send("Page.enable");

    // 1. Home: the hook and two doors
    await go("index.html#home");
    assert.ok(await until(`/Play a challenge/.test(document.body.innerText) && /Watch the whole fab at work/.test(document.body.innerText)`), "home: two doors");

    // 2. The floor: the full fab draws, plays at 12×, and follows one lot
    await go("index.html#floor");
    assert.ok(await until(`document.body.dataset.floor === "full"`, 20000), "the floor loads");
    for (let i = 0; i < 4 && (await ev(`document.querySelector(".speeds button").textContent.trim()`)) !== "12×"; i++) await ev(`document.querySelector(".speeds button").click()`);
    assert.equal(await ev(`document.querySelector(".speeds button").textContent.trim()`), "12×");
    await ev(`document.getElementById("follow-open").click()`);
    assert.ok(await until(`/Back to the floor/.test(document.getElementById("follow-open").textContent)`, 8000), "following one lot");

    // 3. Build: challenge 1, the advice, the jam map, a fix that meets it and the stars
    await go("editor.html");
    assert.ok(await until(`!!(window.FabEditorPage && FabEditorPage.runs() >= 1)`, 15000), "the editor runs");
    assert.ok(await until(`document.getElementById("advice").textContent.trim().length > 10`, 5000), "advice under the map");
    await key("j", "KeyJ");
    assert.equal(await ev("FabEditorPage.jamMap()"), true, "the jam map");
    await key("j", "KeyJ");
    await ev(`document.getElementById("showfix").click()`);
    assert.ok(await until(`!document.getElementById("win").hidden`, 10000), "Challenge met");
    assert.ok((await ev(`document.querySelectorAll("#win .star.on").length`)) >= 1, "a star");

    // 4. Ask the fab: a worked example's question, answered from its written answer (no model, no credit)
    await go("index.html#floor");
    // the worked examples are the Floor's ask bar's suggestions (docs/HOME-GATE.md)
    assert.ok(await until(`!!document.querySelector("#cmd-examples button")`, 20000), "worked examples");
    await ev(`(() => { const q = document.getElementById("cmd-q"); q.value = document.querySelector("#cmd-examples button").textContent; document.getElementById("cmd").requestSubmit(); })()`);
    assert.ok(await until(`!document.getElementById("pane-ask").closest("[hidden]")`, 8000), "the answer opens");

    // 5. Evidence: four findings, the last one 120 of 120
    await go("index.html#evidence");
    assert.ok(await until(`document.querySelectorAll("#findings .find").length === 4`, 20000), "four findings");
    assert.match(await ev(`document.getElementById("find-checked").textContent`), /120 \/ 120|120 of 120/);
  } finally { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); }
});
