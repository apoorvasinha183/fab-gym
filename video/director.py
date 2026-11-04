"""Build web/director.js from video/director.template.js, video/script.json and video/lou-cues.json (run from the
repo root), and the rule card's page video/card.html. Then copy web/ into the site's play/ as its README says."""
import html
import json
import sys
from pathlib import Path

wps = float(sys.argv[sys.argv.index("--wps") + 1]) if "--wps" in sys.argv else 2.6
script = json.loads(Path("video/script.json").read_text())["beats"]
cues = [{"id": c["id"], "text": c["text"]} for c in json.loads(Path("video/lou-cues.json").read_text())["cues"]]
js = Path("video/director.template.js").read_text()
js = js.replace("__SCRIPT__", json.dumps(script, ensure_ascii=False)).replace("__CUES__", json.dumps(cues, ensure_ascii=False))
Path("web/director.js").write_text(js.replace("__WPS__", str(wps)))
card = Path("video/rule-run/card.md").read_text()
Path("video/card.html").write_text(f"""<!doctype html><html><head><meta charset="utf-8"><title>Rule card</title>
<style>body{{margin:0;background:#0d1117;color:#e6edf3;font:22px/1.5 Menlo,monospace;padding:60px 80px}}
pre{{white-space:pre-wrap;margin:0}}</style></head><body><pre>{html.escape(card)}</pre>
<script src="http://127.0.0.1:8766/lou-cue.js"></script><script src="http://127.0.0.1:8766/director.js"></script></body></html>""")
print("director.js:", len(script), "beats,", len(cues), "cues, at", wps, "words a second")
