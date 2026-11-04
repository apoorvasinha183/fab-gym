#!/bin/sh
# Record the demo video's screens (run from the repo root, the helper on :8766 and the site on :8777 up): the browser
# beats play themselves (director.js), the 3D fab answers a question live, the cinema plays a film. Each capture
# has a hard time limit; times.txt notes when each began, and video/cut.py trims at the director's marks.
#   sh video/record.sh [s1 s2 s3 s4]
set -u
R=$(pwd)/data/video/rec
LOG=$R/marks.log
GODOT=~/Applications/Godot.app/Contents/MacOS/Godot
mkdir -p "$R"
pgrep -f 'http.server 8778' > /dev/null || (cd video && nohup python3 -m http.server 8778 --bind 127.0.0.1 >> "$LOG" 2>&1 &)
sleep 1
segs=${*:-s1 s2 s3 s4}
cap() {       # $1 file, $2 seconds: the main screen, hardware-encoded, no cursor
  ffmpeg -y -loglevel error -f avfoundation -capture_cursor 0 -framerate 30 -pixel_format nv12 -i "Capture screen 0" -t "$2" \
    -c:v h264_videotoolbox -b:v 14M -pix_fmt yuv420p -movflags frag_keyframe+empty_moov "$1" < /dev/null 2>> "$R/ffmpeg.log"
}
browser() {   # $1 segment, $2 start beat, $3 end mark, $4 seconds at most, $5 the beat's page
  rm -rf "$R/profile" "$R/$1.mov"
  echo "$1 $(python3 -c 'import time;print(int(time.time()*1000))')" >> "$R/times.txt"
  cap "$R/$1.mov" "$4" &
  sleep 1.5
  open -na "Google Chrome" --args --user-data-dir="$R/profile" --no-first-run --no-default-browser-check --kiosk "$5"
  sleep "$4"; sleep 3
  kill $(pgrep -f "user-data-dir=$R/profile" | head -1) 2>/dev/null; sleep 2; rm -rf "$R/profile"
}
godot() {     # $1 segment, $2 seconds, then the flags
  seg=$1; secs=$2; shift 2
  rm -f "$R/$seg.mov"
  echo "$seg $(python3 -c 'import time;print(int(time.time()*1000))')" >> "$R/times.txt"
  cap "$R/$seg.mov" "$secs" &
  sleep 1
  "$GODOT" --path viz/fab3d -f -- "$@" > "$R/$seg.log" 2>&1 & G=$!
  sleep "$secs"; sleep 2; kill $G 2>/dev/null; sleep 2
}
for s in $segs; do
  case $s in
    s1) browser s1 0 end-6 160 'http://127.0.0.1:8777/?auto=0' ;;
    s2) godot s2 38 --no-intro --aisle --cues --say 6 --lou-ask "Where do wafers get polished?" ;;
    s3) godot s3 16 --no-intro --seat ;;
    s4) browser s4 7 end-7 30 'http://127.0.0.1:8777/?auto=7#new' ;;
  esac
done
wait
ls -la "$R"/s*.mov
