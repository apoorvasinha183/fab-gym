"""Serve web/ on 127.0.0.1 for the From Sand to Chip film, and save the frames the film posts (docs/CHIP-FILM.md).

    python3 film/serve.py            then open http://127.0.0.1:8770/film/

POST /save/<folder>/<name>.png|jpg writes the body to data/film/<folder>/<name>. Names are checked; nothing else is
written. Local only."""

import http.server
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OUT = ROOT / "data" / "film"
NAME = re.compile(r"^/save/([a-z0-9-]+)/([a-z0-9-]+\.(png|jpg))$")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB), **k)

    def do_POST(self):
        m = NAME.match(self.path)
        if not m:
            self.send_error(400, "bad name")
            return
        n = int(self.headers.get("Content-Length", "0"))
        if n <= 0 or n > 50_000_000:
            self.send_error(400, "bad size")
            return
        folder = OUT / m.group(1)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / m.group(2)).write_bytes(self.rfile.read(n))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    print(f"serving {WEB} at http://127.0.0.1:{port}/film/ ; frames to {OUT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
