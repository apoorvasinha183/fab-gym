#!/bin/sh
# Copy the film's parts and scene into the explore project (data/ is not in git).
# Run from the repo root after viz/look/kit.py, viz/prep.py --real and viz/film/film.py.
set -e
mkdir -p viz/godot-real/data
cp data/layout-real/scene-optimised.json viz/godot-real/data/scene.json
cp data/layout-real/models.json viz/godot-real/data/models.json
[ -f data/layout-real/film.json ] && cp data/layout-real/film.json viz/godot-real/data/film.json
[ -f data/layout-real/visitor.json ] && cp data/layout-real/visitor.json viz/godot-real/data/visitor.json
[ -f data/assets/polypizza-hazmat/character-hazmat.glb ] && cp data/assets/polypizza-hazmat/character-hazmat.glb viz/godot-real/data/hazmat.glb
echo "copied into viz/godot-real/data"
