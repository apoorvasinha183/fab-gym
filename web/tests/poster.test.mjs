// The three-star poster (docs/POSTER.md). Written before the code. The helper answers from a recorded poster
// (--stand-in), so no model is called and nothing is spent. On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/poster.test.mjs   (needs Google Chrome and the .venv)

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
  const helper = spawn(PY, ["-m", "agent.helper", "--runs", mkdtempSync(join(tmpdir(), "test-runs-")), "--port", String(hp), "--stand-in", join(HERE, "fixtures", "poster")], { cwd: ROOT, stdio: "ignore" });
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${hp}/editor.html`)).ok) break; } catch { /* not up */ } await sleep(100); }
  const cp = 9300 + Math.floor(Math.random() * 400);
  const ch = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${cp}`, "--window-size=1440,1000", "--hide-scrollbars", `--user-data-dir=${profileDir("poster-")}`, "about:blank"], { stdio: "ignore" });
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
  return { ev, until, close: () => { try { ws.close(); } catch { /* closed */ } ch.kill(); helper.kill(); } };
}
const posterShown = `(() => { const b = document.getElementById("poster-go"); return !!b && !b.hidden && !document.getElementById("win").hidden; })()`;

test("PO6 one star: no poster button; three stars: a poster button", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open();
  try {
    await p.ev(`document.getElementById("showfix").click()`);
    assert.ok(await p.until(`!document.getElementById("win").hidden`, 10000), "the card at one star");
    assert.equal(await p.ev(posterShown), false, "no poster at one star");
    await p.ev(`document.getElementById("win").hidden = true`);
    await p.ev(`FabEditorTools.call("set_cap", { lots: 20 })`);
    assert.ok(await p.until(posterShown, 15000), "the poster button at three stars");
  } finally { p.close(); }
});

test("PO7 the poster shows in the card with who made it, the cost, where it is saved, and a Download", { skip: !ready && "needs Google Chrome and the .venv" }, async () => {
  const p = await open();
  try {
    await p.ev(`document.getElementById("showfix").click()`);
    await p.until(`!document.getElementById("win").hidden`, 10000);
    await p.ev(`document.getElementById("win").hidden = true`);
    await p.ev(`FabEditorTools.call("set_cap", { lots: 20 })`);
    assert.ok(await p.until(posterShown, 15000));
    await p.ev(`document.getElementById("poster-go").click()`);
    assert.ok(await p.until(`(document.getElementById("poster-img") || {}).src && document.getElementById("poster-img").src.startsWith("data:image/png")`, 10000), "the poster");
    const t = await p.ev(`document.getElementById("poster-note").textContent`);
    assert.match(t, /stand-in/); assert.match(t, /\$0\.00/); assert.match(t, /posters/);
    assert.ok(await p.ev(`!!document.querySelector("#poster-box a[download]")`), "a Download");
  } finally { p.close(); }
});
