#!/bin/sh
# Copy the CC0 assets the render uses (docs/ASSETS.md) from data/assets to a folder of short names,
# then to the machine that renders. Usage: viz/blender/push_assets.sh [HOST:DIR]   (default: stage only)
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
A="$ROOT/data/assets"
S="$ROOT/data/assets/stage"
rm -rf "$S"; mkdir -p "$S/tex" "$S/cars/Textures" "$S/people"
cp "$A/polyhaven/kloofendal_48d_partly_cloudy_puresky_4k.hdr" "$S/sky.hdr"
for pair in concrete:Concrete034 asphalt:Asphalt012 grass:Grass004 metal:MetalPlates006; do
  n=${pair%%:*}; d=${pair#*:}
  cp "$A/ambientcg/${d}_2K-JPG/${d}_2K-JPG_Color.jpg" "$S/tex/${n}_color.jpg"
  cp "$A/ambientcg/${d}_2K-JPG/${d}_2K-JPG_Displacement.jpg" "$S/tex/${n}_height.jpg"
  cp "$A/ambientcg/${d}_2K-JPG/${d}_2K-JPG_Roughness.jpg" "$S/tex/${n}_rough.jpg"
done
K="$A/kenney/kenney_car-kit/Models/GLB format"
for c in sedan suv hatchback-sports van taxi delivery; do cp "$K/$c.glb" "$S/cars/"; done
cp "$K/Textures/colormap.png" "$S/cars/Textures/"
Q="$A/quaternius/universal-base-characters-standard/Universal Base Characters[Standard]/Base Characters/Godot - UE"
for p in Superhero_Male_FullBody Superhero_Female_FullBody; do cp "$Q/$p.gltf" "$Q/$p.bin" "$S/people/"; done
cp "$A/quaternius/universal-animation-library-standard/Universal Animation Library[Standard]/Unreal-Godot/UAL1_Standard.glb" "$S/people/ual.glb"
cp "$A/polypizza-hazmat/character-hazmat.glb" "$S/people/hazmat.glb"
du -sh "$S"
if [ -n "$1" ]; then rsync -a --delete "$S/" "$1/"; fi
