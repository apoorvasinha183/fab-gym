#!/bin/sh
# Build the helper's live 3D inputs from the bundled SMT2020 data.
set -eu
cd "$(dirname "$0")/.."
cargo build --release --locked -p fabsim
target/release/fabsim layout --real --chase 1.6 --cross 1.6 \
  --out data/layout-real-dd --data data/layout-real-dd
target/release/fabsim layout-trace --real --chase 1.6 --cross 1.6 \
  --data data/layout-real-dd --day 1 --hours 1
python3 viz/prep.py --real --layout data/layout-real-dd/layout.json \
  --trace data/layout-real-dd/trace-optimised.json --out data/layout-real-dd/scene-optimised.json
target/release/fabsim fleet-trace --vehicles 160 --day 1 --minutes 60
python3 viz/fleet/building.py --out web/data
echo "3D live inputs ready; start python3 -m agent.helper --port 8766"
