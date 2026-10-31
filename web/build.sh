#!/bin/sh
# Build the browser page's simulator and its data (the SMT2020 files are not committed).
set -e
cd "$(dirname "$0")/.."
cargo build --release --target wasm32-unknown-unknown -p fabweb
cp target/wasm32-unknown-unknown/release/fabweb.wasm web/
cargo run --release -q --bin fabsim -- web-data web/data "${1:-data/smt2020/hvlm}"
cp results/lean-long-units/summary.json web/data/lean-long.json
# every scored run's Lean referee verdict, summed for Evidence (docs/EVIDENCE-PLAIN.md)
python3 results/lean-check/summary.py
# the two-family sweep with today's baselines, and the recorded example questions (docs/FLOOR-UI.md)
node -e '
const fs = require("fs"); const U = require("./web/ui.js");
const s = JSON.parse(fs.readFileSync("results/two-families/summary.json", "utf8"));
s.baseline = U.baselineFromRuns(fs.readFileSync("results/two-families/runs.tsv", "utf8"));
if (fs.existsSync("results/two-families/pl.json")) s.pl = JSON.parse(fs.readFileSync("results/two-families/pl.json", "utf8"));
fs.writeFileSync("web/data/two-families.json", JSON.stringify(s));
const ex = fs.readdirSync("agent/examples/ask").filter((f) => f.endsWith(".json")).sort()
  .map((f) => JSON.parse(fs.readFileSync("agent/examples/ask/" + f, "utf8"))).map((e) => ({ question: e.question, example: true }));
fs.writeFileSync("web/data/examples.json", JSON.stringify(ex));
'
# the Live view's real building (docs/LIVE-REAL.md): the track from an hour of the fleet, then
# web/data/building.json and web/data/shop-real.txt (today's US building with 160 vehicles)
if [ -f data/layout-real-dd/optimised.shop.txt ]; then
  cargo run --release -q --bin fabsim -- fleet-trace --vehicles 160 --day 1 --minutes 60
  python3 viz/fleet/building.py --out web/data
  # one lot of product 3 from its release on day 20 to its finish: web/data/journey.json
  cargo run --release -q --bin fabsim -- follow --out web/data/journey.json
fi
# the Results tab: every saved experiment with its settings and numbers
node web/tools/results-build.js > web/data/results.json
echo "serve with: python3 -m http.server 8765 --bind 127.0.0.1 --directory web"
