// Tests for the map editor's pure parts (docs/EDITOR.md). Written before the code.
// On the SMT2020 model, a published model of a fab, and a teaching fab of our own; not a real fab.
//
//     node --test web/tests/editor.test.mjs          (from the repo root; needs `cargo build --release`)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
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
const FABSIM = join(ROOT, "target", "release", "fabsim");
const SHOP = join(ROOT, "web", "data", "shop.txt");
const AREAS = join(ROOT, "web", "data", "areas.tsv");

function check(text) {
  const d = profileDir("fabed-");
  const f = join(d, "x.fab.txt");
  writeFileSync(f, text);
  const r = spawnSync(FABSIM, ["fab-check", f, "--json"]);
  const out = r.stdout.toString();
  return { code: r.status, issues: out ? JSON.parse(out) : [], err: r.stderr.toString() };
}
const errors = (r) => r.issues.filter((i) => i.severity === "error");

test("the teaching fab passes the checks", () => {
  const s = E.template("teaching");
  const r = check(E.fabText(E.TEACHING_SHOP, s));
  assert.equal(r.code, 0, r.err + JSON.stringify(errors(r).slice(0, 3)));
  assert.equal(errors(r).length, 0);
});

test("every block has a stop for each of its tools, on rail beside it", () => {
  const s = E.template("teaching");
  const lines = E.toPlan(s);
  for (const b of s.blocks.filter((b) => b.group)) {
    const stops = lines.filter((l) => l.startsWith(`stop\t${b.group}\t`));
    assert.equal(stops.length, b.count, b.group);
    for (const l of stops) {
      const [x, y] = E.cellOfNode(l.split("\t")[3]);
      const beside = x >= b.x - 1 && x <= b.x + b.w && y >= b.y - 1 && y <= b.y + b.h && !(x >= b.x && x < b.x + b.w && y >= b.y && y < b.y + b.h);
      assert.ok(beside, `${l} is beside ${b.group}`);
    }
  }
});

test("links are 3 m a tile and node ids are unique", () => {
  const lines = E.toPlan(E.template("teaching"));
  const nodes = lines.filter((l) => l.startsWith("node\t")).map((l) => l.split("\t")[1]);
  assert.equal(new Set(nodes).size, nodes.length);
  const links = lines.filter((l) => l.startsWith("link\t"));
  assert.ok(links.length > 0);
  for (const l of links) assert.equal(Number(l.split("\t")[3]), E.TILE_M);
  assert.equal(E.TILE_M, 3);
});

test("the fab text keeps the base shop and changes only the counts it is given", () => {
  const s = E.template("teaching");
  const b = s.blocks.find((b) => b.group);
  b.count += 2;
  const text = E.fabText(E.TEACHING_SHOP, s);
  const groupLine = text.split("\n").find((l) => l.startsWith(`group\t${b.group}\t`));
  assert.equal(Number(groupLine.split("\t")[2]), b.count);
  const base = E.TEACHING_SHOP.split("\n").filter((l) => !l.startsWith("group\t") && l);
  for (const l of base) assert.ok(text.includes(l), `kept: ${l}`);
});

test("cutting the loop is caught by the checks", () => {
  const s = E.template("teaching");
  const spine = Object.keys(s.rail).find((k) => s.rail[k].spine);
  delete s.rail[spine];
  const r = check(E.fabText(E.TEACHING_SHOP, s));
  assert.equal(r.code, 2);
  assert.ok(errors(r).some((i) => ["trap", "unreachable", "no_way_out", "route_gap"].includes(i.code)), JSON.stringify(errors(r).slice(0, 3)));
});

test("the SMT2020 template places every group once with its count and passes", { skip: !existsSync(SHOP) && "needs web/build.sh" }, () => {
  const shop = readFileSync(SHOP, "utf8");
  const s = E.template("smt2020", { shop, areas: readFileSync(AREAS, "utf8") });
  const groups = shop.split("\n").filter((l) => l.startsWith("group\t")).map((l) => l.split("\t"));
  for (const [, name, count] of groups) {
    if (s.stores.includes(name)) continue;
    const placed = s.blocks.filter((b) => b.group === name);
    assert.equal(placed.length, 1, name);
    assert.equal(placed[0].count, Number(count), name);
  }
  assert.deepEqual(s.stores, ["Delay_32"]);
  const r = check(E.fabText(shop, s, { vehicles: 120 }));
  assert.equal(r.code, 0, r.err + JSON.stringify(errors(r).slice(0, 3)));
});

test("a block's mood is the most common among its tools, ties to the more serious", () => {
  const m = { tool_moods: ["work", "sleep", "tired", "full", "batch", "setup", "pm", "hurt", "physio", "hold"], tools: ["A#1", "A#2", "A#3", "B#1", "B#2"], groups: ["A", "A", "A", "B", "B"], frames: [{ t: 0, tools: [1, 1, 0, 7, 0] }] };
  assert.equal(E.blockMood(m, 0, "A"), "sleep");
  assert.equal(E.blockMood(m, 0, "B"), "hurt");
  assert.equal(E.blockMood(m, 0, "C"), null);
});
