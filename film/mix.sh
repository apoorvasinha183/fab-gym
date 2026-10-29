#!/bin/sh
# Lay the music under a cut of From Sand to Chip (docs/CHIP-FILM.md, web/film/script.js MUSIC):
# The Budding of Consciousness (Yoiyami, CC0) from 0:00, fading out 1:13 to 1:17, and New Sunrise (nene, CC0) from
# 1:13, fading in over 4 s and out over the last 3 s. Usage: film/mix.sh <silent cut.mp4> <out.mp4>
set -e
cd "$(dirname "$0")/.."
M=data/film/music
nice -n 10 ffmpeg -v error -y -i "$1" -i $M/budding/the_budding_of_consciousness.wav -i $M/new-sunrise/new_sunrise_V2.wav -filter_complex \
 "[1:a]aresample=48000,atrim=0:77,afade=t=out:st=73:d=4,volume=0.9[a1];\
  [2:a]aresample=48000,atrim=0:91,afade=t=in:st=0:d=4,afade=t=out:st=88:d=3,adelay=73000|73000,volume=0.85[a2];\
  [a1][a2]amix=inputs=2:normalize=0,atrim=0:164[a]" \
 -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart "$2"
