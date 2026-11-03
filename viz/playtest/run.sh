#!/bin/sh
# Play the demo under the playtest harness (viz/playtest/README.md), then analyse it.
#   viz/playtest/run.sh OUT_DIR [--no-intro] [--cinema]
set -e
OUT="$1"; shift
GODOT="${GODOT:-$HOME/Applications/Godot.app/Contents/MacOS/Godot}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$OUT"
cd "$ROOT"
{ git rev-parse HEAD; git diff --stat; git diff | shasum -a 256; } > "$OUT/version.txt"
caffeinate -u -d -t 2900 &
nice "$GODOT" --always-on-top --path viz/fab3d res://playtest/playtest.tscn -- --playtest "$OUT" "$@" > "$OUT/godot.log" 2>&1 || true
python3 viz/playtest/analyse.py "$OUT"
