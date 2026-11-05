"""Prepare a complete cinema frame and embedded captions for Godot.

python3 viz/fab3d/prepare_film.py SOURCE.mp4 DESTINATION.ogv --blender /path/to/blender
The adjacent .film.json records the source and converter hashes, plus timed captions.
"""

import argparse
import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

CONVERTER = Path(__file__).with_name("film_ogv.py")


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def captions(srt):
    def seconds(value):
        h, m, s, ms = map(int, re.split("[:,.]", value))
        return h * 3600 + m * 60 + s + ms / 1000

    cues = []
    for block in re.split(r"\n\s*\n", srt.replace("\r\n", "\n").strip()):
        lines = block.splitlines()
        timing = next((i for i, line in enumerate(lines) if " --> " in line), None)
        if timing is None:
            continue
        start, end = lines[timing].split(" --> ", 1)
        text = html.unescape(re.sub(r"<[^>]*>", "", "\n".join(lines[timing + 1:])))
        cues.append({"start": seconds(start), "end": seconds(end.split()[0]), "text": text})
    return cues


def prepare(source, output, blender):
    source, output = Path(source), Path(output)
    mark = output.with_suffix(".film.json")
    signature = {"source_sha256": digest(source), "converter_sha256": digest(CONVERTER),
                 "preparer_sha256": digest(__file__)}
    if output.exists() and mark.exists():
        old = json.loads(mark.read_text())
        if all(old.get(k) == v for k, v in signature.items()) and old.get("output_sha256") == digest(output):
            return old
    info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)]))
    cues = []
    if any(s["codec_type"] == "subtitle" for s in info["streams"]):
        cues = captions(subprocess.check_output([
            "ffmpeg", "-v", "error", "-i", str(source), "-map", "0:s:0", "-f", "srt", "-"], text=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.stem + ".partial.ogv")
    try:
        result = subprocess.run([
            str(blender), "--background", "--factory-startup", "--threads", "4",
            "--python", str(CONVERTER), "--", str(source.resolve()), str(temporary.resolve())],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900)
        if result.returncode:
            raise RuntimeError(result.stdout[-6000:])
        check = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(temporary)]))
        duration = check.get("format", {}).get("duration")
        if duration is None or abs(float(duration) - float(info["format"]["duration"])) > 0.15:
            raise RuntimeError("Converted film is incomplete or differs in duration.\n" + result.stdout[-3000:])
        temporary.replace(output)
        metadata = {**signature, "source_name": source.name, "output_sha256": digest(output),
                    "duration": float(info["format"]["duration"]), "captions": cues}
        mark.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        return metadata
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--blender", type=Path, default=Path.home() / "Applications/Blender.app/Contents/MacOS/Blender")
    args = parser.parse_args()
    result = prepare(args.source, args.output, args.blender)
    print(f"Prepared {args.output}: {result['duration']:.2f}s, {len(result['captions'])} captions")
