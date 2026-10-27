#!/bin/sh
# Copy the film's parts and scene into the explore project (data/ is not in git).
# Run from the repo root after viz/look/kit.py, viz/prep.py --real and viz/film/film.py.
set -e
mkdir -p viz/godot-real/data
cp data/layout-real/scene-optimised.json viz/godot-real/data/scene.json
cp data/layout-real/models.json viz/godot-real/data/models.json
[ -f data/layout-real/film.json ] && cp data/layout-real/film.json viz/godot-real/data/film.json
echo "copied into viz/godot-real/data"
