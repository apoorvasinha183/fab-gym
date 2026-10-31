// The supervisor's toy fab (docs/SUPERVISOR-TOY.md): the Build page's free-build layout as a fab file, and its two kinds
// of polishing breakdowns, set to come equally often at today's load. A teaching fab of our own; not a real fab.
//
//     node web/tools/toy-fab.mjs data/supervisor      (writes toy.fab.txt, clock.json, wear.json)
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const require = createRequire(import.meta.url);
const E = require("../editor-core.js");
const out = process.argv[2] || "data/supervisor";
mkdirSync(out, { recursive: true });
const s = E.template("teaching");
writeFileSync(join(out, "toy.fab.txt"), E.fabText(E.TEACHING_SHOP, s));
// polishing (the bottleneck): about every 8 hours a machine at today's load (246 wafers a machine, measured under the clock kind (737 wafers a day)), 1 to 2 hours down
const ov = (b) => JSON.stringify({ "fabgym-overrides": 1, groups: { Planar_T: { breakdowns: b } } }, null, 1) + "\n";
writeFileSync(join(out, "clock.json"), ov({ kind: "random", mttf_hours: 8, mttr_hours: 1.5 }));
writeFileSync(join(out, "wear.json"), ov({ kind: "by_wafers", every: 246, minutes: [60, 120] }));
console.log(`wrote ${out}/toy.fab.txt, clock.json, wear.json`);
