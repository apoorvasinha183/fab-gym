"""Voice the founder's lines with their own ElevenLabs voice (the founder's request, 5 Nov), one clip per line, into
data/video/voice/; each line's spoken length goes back into video/script.json as "dur" so the director and the cut
follow it. Clips already made are kept. The key stays in ~/.config/elevenlabs/key and is never printed."""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

VOICE = "cjVigY5qzO86Huf0OWal"          # "Eric", smooth and trustworthy, from ElevenLabs' library (the founder's pick, 5 Nov)
MODEL = "eleven_multilingual_v2"
SPEED = 1.15
OUT = Path("data/video/voice")
KEY = (Path.home() / ".config" / "elevenlabs" / "key").read_text().strip()


def clip(text):
    name = hashlib.sha256(f"{VOICE}|{MODEL}|saved|{SPEED}|{text}".encode()).hexdigest()[:16] + ".mp3"
    p = OUT / name
    if not p.exists():
        # no voice_settings: the voice's own saved settings, as the founder's ElevenLabs instructions do it
        settings = {"stability": 0.6, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True, "speed": SPEED}
        body = json.dumps({"text": text, "model_id": MODEL, "voice_settings": settings}).encode()
        req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_128", data=body,
                                     headers={"xi-api-key": KEY, "Content-Type": "application/json"})
        p.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                             capture_output=True, text=True).stdout)
    return name, round(d, 2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sp = Path("video/script.json")
    d = json.loads(sp.read_text())
    total = 0.0
    for b in d["beats"]:
        for item in b["items"]:
            if item[0] == "you":
                name, dur = clip(item[1])
                del item[2:]
                item += [dur, name]
                total += dur
    for g in d["godot"]:
        g["audio"], g["dur"] = clip(g["say"])
        total += g["dur"]
    sp.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    print(f"voiced: {total:.1f} s of speech")


if __name__ == "__main__":
    main()
