// The referee's sixth rule on Build's runs (docs/LEAN-FINISH.md, R9). Written before the code: a challenge's receipt
// is Build's own run, so the wafers Build scores are exactly the lots the receipt lists as finished.
// On a teaching fab of our own; not a real fab.
//
//     node --test web/tests/leanfinish.test.mjs   (needs a release build)

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const FABSIM = join(ROOT, "target", "release", "fabsim");
const require = createRequire(import.meta.url);
const E = require(join(ROOT, "web", "editor-core.js"));
const DAYS = 2, SEED = 1; // as Build scores a challenge: two days, run #1

test("R9 each challenge's receipt is Build's run: the wafers it scores are the lots the receipt lists as finished", { skip: !existsSync(FABSIM) && "needs a release build" }, () => {
  const dir = mkdtempSync(join(tmpdir(), "leanfinish-"));
  try {
    for (const c of E.CHALLENGES) {
      for (const variant of ["start", "fix"]) {
        let x = c.setup();
        if (variant === "fix") x = c.fix(x);
        const fab = join(dir, `${c.id}-${variant}.fab.txt`), ov = join(dir, `${c.id}-${variant}.overrides.json`);
        writeFileSync(fab, E.fabText(x.base, x.state, { vehicles: x.state.vehicles }));
        const overrides = E.overridesFor(x.state);
        const ovArgs = overrides ? (writeFileSync(ov, JSON.stringify(overrides)), ["--overrides", ov]) : [];
        const moods = JSON.parse(execFileSync(FABSIM, ["moods", fab, String(SEED), "--until", String(DAYS * 1440), "--every", "60", ...ovArgs], { maxBuffer: 1 << 28 }).toString());
        const receipt = execFileSync(FABSIM, ["receipt", fab, "--seed", String(SEED), "--until", String(DAYS * 1440), ...ovArgs], { maxBuffer: 1 << 28 }).toString();
        const lines = receipt.trim().split("\n");
        assert.equal(lines[0], "fabgym-receipt 2", `${c.id} ${variant}: a version 2 receipt`);
        const size = new Map(lines.filter((l) => l.startsWith("lot ")).map((l) => { const f = l.split(" "); return [f[1], +f[3]]; }));
        const finished = lines.filter((l) => l.startsWith("F ")).map((l) => l.split(" ")[1]);
        assert.ok(finished.length > 0, `${c.id} ${variant}: some lots finish`);
        const wafers = finished.reduce((a, lot) => a + size.get(lot), 0);
        assert.equal(wafers / DAYS, moods.score.wafers_per_day, `${c.id} ${variant}: Build's wafers a day are the receipt's finished lots`);
        const end = lines[lines.length - 1].split(" ");
        assert.equal(+end[5], finished.length, `${c.id} ${variant}: the end line counts the finished lots`);
      }
    }
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
