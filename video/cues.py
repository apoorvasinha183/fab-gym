"""Rebuild the cue list inside web/lou-cue.js from video/lou-cues.json (run from the repo root)."""
import json, re
from pathlib import Path

js = Path("web/lou-cue.js")
cues = [{"id": c["id"], "text": c["text"]} for c in json.loads(Path("video/lou-cues.json").read_text())["cues"]]
js.write_text(re.sub(r"const CUES = .*?;\n", lambda m: "const CUES = " + json.dumps(cues, ensure_ascii=False) + ";\n",
                     js.read_text(), count=1))
print(len(cues), "cues")
