"""Join the recorded segments (data/video/rec/s1..s4.mov) into the demo video, with the founder's voiced lines laid
where the director marked them (the browser beats) or at fixed offsets (the 3D fab, the cinema); no subtitles.
Trims are [start, end] seconds per segment; a browser segment's end defaults to its end mark.

    python3 video/cut.py '{"s1":[3,null],"s2":[20,52],"s3":[4,14],"s4":[3,null]}' [OUT.mp4]
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / "data" / "video" / "rec"
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"


def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def sub_filter(text):
    lines = textwrap.wrap(text, 70)
    out, y = [], 140
    for ln in lines:
        out.append(f"drawtext=fontfile={FONT}:text='{esc(ln)}':fontcolor=white:fontsize=50:x=(w-text_w)/2:y={y}:"
                   "box=1:boxcolor=0x080a1c@0.86:boxborderw=18")
        y += 78
    return ",".join(out)


def mark_ends():
    """Each browser segment's end, in seconds into its recording: when the director's end mark reached the log."""
    import datetime as dt
    import re
    starts = {}
    for ln in (REC / "times.txt").read_text().split("\n"):
        if ln.strip():
            k, v = ln.split()
            starts[k] = int(v) / (1000.0 if int(v) > 10**11 else 1.0)
    marks = {}
    for ln in (REC / "marks.log").read_text().split("\n"):
        m = re.search(r"\[(\d\d/\w+/\d{4} \d\d:\d\d:\d\d)\] \"GET /mark/(end-\d+)", ln)
        if m:
            marks[m.group(2)] = dt.datetime.strptime(m.group(1), "%d/%b/%Y %H:%M:%S").timestamp()
    lines = []
    for ln in (REC / "marks.log").read_text().split("\n"):
        m = re.search(r"GET /mark/(\d{13})-(\d+)-(\d+)", ln)
        if m:
            lines.append((int(m.group(1)) / 1000.0, int(m.group(2)), int(m.group(3))))
    out = {"lines": lines, "starts": starts}
    for seg, mark in (("s1", "end-6"), ("s4", "end-7")):
        if seg in starts and mark in marks and marks[mark] > starts[seg]:
            out[seg] = round(marks[mark] - starts[seg] + 1.0, 1)
    return out


def main():
    trims = json.loads(sys.argv[1])
    me = mark_ends()
    for seg in ("s1", "s4"):
        if seg in me and trims[seg][1] is None:
            trims[seg][1] = me[seg]
    print("trims", trims)
    sc = json.loads((ROOT / "video" / "script.json").read_text())
    beats, godot = sc["beats"], sc["godot"]
    first = {"s1": 0, "s4": 7}          # the beats each browser segment begins with
    voice = ROOT / "data" / "video" / "voice"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "video" / "fab-gym-demo.mp4"
    gaps = {"s2": 4.0, "s3": 0.8}       # where the founder's line starts in the 3D fab and the cinema, after the trim
    parts = []
    # the wait for the model's answer in the ask beat is cut down to a beat at each end (a jump cut)
    pieces = []
    for seg in ("s1", "s2", "s3", "s4"):
        a, b = trims[seg]
        if seg == "s1" and me.get("lines"):
            t0 = me["starts"]["s1"]
            at = {(bn, it): t - t0 for t, bn, it in me["lines"] if t > t0}
            if (3, 0) in at and (3, 1) in at:
                x1 = at[(3, 0)] + beats[3]["items"][0][2] + 1.0
                x2 = at[(3, 1)] - 1.5
                if x2 - x1 > 2:
                    pieces += [("s1", "s1a", a, x1), ("s1", "s1b", x2, b)]
                    print(f"cut the wait: {x2 - x1:.1f} s")
                    continue
        pieces.append((seg, seg, a, b))
    for seg, name, a, b in pieces:
        clips = []
        if seg in ("s1", "s4"):
            lo, hi = first[seg], (6 if seg == "s1" else 7)
            for t, bn, it in me.get("lines", []):
                if lo <= bn <= hi and t > me["starts"][seg]:
                    at = t - me["starts"][seg] - a
                    if at >= 0 and (b is None or at < b - a):
                        clips.append((at, voice / beats[bn]["items"][it][3]))
        else:
            g = godot[0 if seg == "s2" else 1]
            clips.append((gaps[seg], voice / g["audio"]))
        part = REC / f"{name}-cut.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(a)] + (["-to", str(b)] if b else []) + ["-i", str(REC / f"{seg}.mov")]
        for _, c in clips:
            cmd += ["-i", str(c)]
        fl = ["[0:v]scale=1920:1200:flags=lanczos,fps=30[v]"]
        mix = []
        for j, (at, _) in enumerate(clips, 1):
            ms = int(at * 1000)
            fl.append(f"[{j}:a]adelay={ms}|{ms},aresample=48000[a{j}]")
            mix.append(f"[a{j}]")
        fl.append("anullsrc=r=48000:cl=stereo[s0]")
        fl.append("[s0]" + "".join(mix) + f"amix=inputs={len(mix) + 1}:normalize=0:duration=first[am]")
        dur = (b - a) if b else None
        cmd += ["-filter_complex", ";".join(fl), "-map", "[v]", "-map", "[am]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
        if dur:
            cmd += ["-t", f"{dur:.2f}"]
        cmd.append(str(part))
        subprocess.run(cmd, check=True)
        print(name, f"{len(clips)} lines", f"{dur or 0:.1f} s")
        parts.append(part)
    lst = REC / "parts.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True).stdout.strip()
    print(f"{out}: {float(d):.1f} s")


if __name__ == "__main__":
    main()
