// Tests for the ask box's pure parts (docs/ASK-FAMILIES.md, part 5). Written before the code.
// On the SMT2020 model, a published model of a fab; not a real fab.
//
//     node --test web/tests/ask.test.mjs          (from the repo root)
//
// The reports in fixtures/ are smoke runs kept for these tests, not results.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const A = require(join(HERE, "..", "ask.js"));
const fam = JSON.parse(readFileSync(join(HERE, "fixtures", "ask-families.json"), "utf8"));
const one = JSON.parse(readFileSync(join(HERE, "fixtures", "ask-one-family.json"), "utf8"));

const TEXT = [
  "fabgym-scenario 1",
  "question\tIf breakdowns get worse, do we hold prototypes at the door?",
  "family\tshare\t1\tassumed",
  "shock\tbreakdowns\t1.5\tsaid",
  "shock\toutage\tPlanar_FE_79\t30\t8\tassumed",
  "candidate\tcapped\tpolicy\tcap",
  "candidate\tcopies-capped\tfloor\tcopies",
  "candidate\tcopies-capped\tpolicy\tcap",
  "candidate\tfaster\trule\tfifo",
  "",
].join("\n");

test("a scenario reads as plain lines, each said or assumed", () => {
  const s = A.scenarioLines(TEXT);
  assert.equal(s.question, "If breakdowns get worse, do we hold prototypes at the door?");
  assert.deepEqual(s.given.map(g => [g.text, g.said]), [
    ["Prototype lots at 1 times the usual", false],
    ["Breakdowns ×1.5", true],
    ["Polisher group Planar_FE_79 down from hour 30 for 8 hours", false],
  ]);
  assert.deepEqual(s.candidates.map(c => c.name), ["capped", "copies-capped", "faster"]);
  assert.deepEqual(s.candidates[1].changes, ["copies of the busiest groups in the halls", "prototypes held at the door above their usual load"]);
  assert.deepEqual(s.candidates[2].changes, ["first in, first out"]);
});

test("a two-family report becomes rows of money, volume wafers and prototype cycle time", () => {
  const rows = A.resultRows(fam);
  assert.deepEqual(rows.map(r => r.name), ["own-wing", "b-first", "copies", "copies-b-first"]);
  for (const r of rows) {
    assert.deepEqual(r.cells.map(c => c.key), ["money", "a_wafers", "b_cycle_days"]);
    for (const c of r.cells) assert.ok(["better", "worse", "no clear effect"].includes(c.verdict));
  }
  const m = rows[0].cells[0];
  const src = fam.candidates[0].measures.money;
  assert.equal(m.mean, src.mean);
  assert.equal(m.verdict, src.verdict);
  assert.equal(m.today, src.today.reduce((a, b) => a + b, 0) / src.today.length);
  // a measure with no values (no prototype lot finished in a short window) reads as no clear effect
  const ct = rows[0].cells[2];
  if (fam.candidates[0].measures.b_cycle_days.mean === null) {
    assert.equal(ct.verdict, "no clear effect");
    assert.equal(ct.mean, null);
  }
});

test("a one-family report uses the scorer's reward, moves and wait", () => {
  const rows = A.resultRows(one);
  assert.deepEqual(rows[0].cells.map(c => c.key), ["reward", "moves", "wait_per_move_minutes"]);
});

test("the summary says what it is and names the best or today", () => {
  for (const r of [fam, one]) {
    const s = A.summaryLine(r);
    assert.match(s, /SMT2020 model/);
    assert.match(s, /what (this|these changes) would do in a real fab is unknown/i);
    if (r.best) assert.ok(s.includes(r.best));
    else assert.match(s, /today's fab stands/i);
  }
});

test("lots of family B are known by their route", () => {
  const j = { routes: [["part_3", []], ["part_4", []], ["part_E3", []]], families: ["A", "A", "B"] };
  assert.deepEqual(A.familyB(j), [false, false, true]);
  assert.deepEqual(A.familyB({ routes: [["part_3", []]] }), [false]);
});

test("a wing hall appears only when an arm has one", () => {
  assert.deepEqual(A.extraHalls(["TF", "Planar"]), []);
  assert.deepEqual(A.extraHalls(["TF", "P3 wing"]), [["Wing (P3)", ["P3 wing"]]]);
  const wing = fam.arms.find(a => a.name === "own-wing");
  assert.deepEqual(A.extraHalls(wing.extra_areas.map(x => x[1])), [["Wing (P3)", ["P3 wing"]]]);
});

test("an arm's rule maps to the page's simulator", () => {
  assert.deepEqual(A.ruleCode({ rule: "today", bfirst: true }), { code: 3, exact: true });
  assert.deepEqual(A.ruleCode({ rule: "fifo", bfirst: false }), { code: 1, exact: true });
  assert.deepEqual(A.ruleCode({ rule: "spt", bfirst: false }), { code: 2, exact: true });
  assert.deepEqual(A.ruleCode({ rule: "today", bfirst: false }), { code: 0, exact: true });
  assert.deepEqual(A.ruleCode({ rule: "cr", bfirst: false }), { code: 0, exact: false });
});

// Answers in dollars (docs/MONEY-PL.md, deliverable 4): a report with operating profit shows it first, in dollars,
// with each candidate's capital, payback and five-year value; an older report with only money a day still reads.
test("a two-family answer in dollars, and an older one in margin units", () => {
  const dollars = JSON.parse(JSON.stringify(fam));
  for (const c of dollars.candidates) {
    const m = c.measures.money;
    c.measures.profit = { ...m, mean: m.mean === null ? null : m.mean * 6200, lo: m.lo === null ? null : m.lo * 6200, hi: m.hi === null ? null : m.hi * 6200 };
    c.measures.cash = c.measures.profit;
    c.pl = { capital: c.name.includes("wing") || c.name.includes("cop") ? 2e7 : 0, npv: { mean: 1e6, lo: -1e6, hi: 3e6 }, payback_days: { soonest: 40, latest: null } };
  }
  const rows = A.resultRows(dollars);
  assert.equal(rows[0].cells[0].key, "profit");
  assert.match(rows[0].cells[0].label, /Operating profit a day/);
  assert.ok(rows.every(r => r.pl && "capital" in r.pl));
  assert.match(A.summaryLine(dollars), /operating profit/);
  const old = A.resultRows(fam);
  assert.equal(old[0].cells[0].key, "money");
  assert.equal(old[0].pl, null);
});
