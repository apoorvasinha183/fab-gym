#!/bin/sh
# Build the browser page's simulator and its data (the SMT2020 files are not committed).
set -e
cd "$(dirname "$0")/.."
cargo build --release --target wasm32-unknown-unknown -p fabweb
cp target/wasm32-unknown-unknown/release/fabweb.wasm web/
cargo run --release -q --bin fabsim -- web-data web/data "${1:-data/smt2020/hvlm}"
echo "serve with: python3 -m http.server 8765 --bind 127.0.0.1 --directory web"
