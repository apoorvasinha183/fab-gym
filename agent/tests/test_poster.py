"""The three-star poster (docs/POSTER.md). Written before the code; no model is called.
Run: python3 -m unittest agent.tests.test_poster  (from the repo root)."""

import base64
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

try:  # arrives with the code
    from agent import poster
except ImportError:
    poster = None
from agent import helper

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
URL = "data:image/png;base64," + base64.b64encode(PNG).decode()
ASK = {"image": URL, "title": "Rush hour on the spine", "wafers": 713, "stars": 3}


def tmpdir(case):
    d = tempfile.TemporaryDirectory()
    case.addCleanup(d.cleanup)
    return Path(d.name)


def key_in(d):
    k = d / "meta.key"
    k.write_text("LLM_TEST\n")
    os.chmod(k, 0o600)
    return k


class Prompt(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(poster, "agent/poster.py is missing")

    def test_PO1_the_prompt_carries_the_name_the_wafers_and_the_stars(self):
        p = poster.prompt("Rush hour on the spine", 713, 3)
        self.assertIn("Rush hour on the spine", p)
        self.assertIn("713 wafers a day", p)
        self.assertIn("three", p.lower())

    def test_PO1_a_long_name_is_cut_and_odd_numbers_refused(self):
        self.assertLessEqual(len(poster.clean_title("x" * 200)), 60)
        self.assertIn("error", poster.check({**ASK, "wafers": 712.5}))
        self.assertIn("error", poster.check({**ASK, "stars": 4}))
        self.assertIsNone(poster.check(ASK).get("error"))

    def test_PO2_only_a_png_data_url_under_8_mb(self):
        self.assertIn("error", poster.check({**ASK, "image": "https://example.com/x.png"}))
        self.assertIn("error", poster.check({**ASK, "image": "data:image/jpeg;base64,AAAA"}))
        big = "data:image/png;base64," + "A" * (12 * 1024 * 1024)
        self.assertIn("error", poster.check({**ASK, "image": big}))


class Make(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(poster, "agent/poster.py is missing")
        self.d = tmpdir(self)

    def test_PO3_a_stand_in_poster_costs_nothing_and_is_saved(self):
        s = self.d / "standin"
        s.mkdir()
        (s / "poster.png").write_bytes(PNG)
        h = helper.Helper(jobs=self.d / "jobs", key_file=key_in(self.d), stand_in=s)
        r = h.poster_make(ASK)
        self.assertEqual(r["model"], "stand-in")
        self.assertEqual(r["cost_usd"], 0)
        self.assertTrue(r["image"].startswith("data:image/png;base64,"))
        saved = Path(r["saved"])
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.read_bytes(), PNG)
        self.assertEqual(saved.parent, self.d / "posters")


class Live(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(poster, "agent/poster.py is missing")
        self.d = tmpdir(self)
        self.heard = []
        self.reply = PNG
        heard, case = self.heard, self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                heard.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                out = json.dumps({"created": 1, "data": [{"b64_json": base64.b64encode(case.reply).decode()}], "output_format": "png",
                                  "usage": {"input_tokens": 10089, "output_tokens": 939}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.url = f"http://127.0.0.1:{srv.server_port}/v1"

    def helper(self, **kw):
        return helper.Helper(jobs=self.d / "jobs", key_file=key_in(self.d), meta_key_file=key_in(self.d), meta_base_url=self.url, **kw)

    def test_PO4_muse_image_is_sent_the_map_and_a_cent_is_counted(self):
        h = self.helper()
        r = h.poster_make(ASK)
        path, sent = self.heard[0]
        self.assertEqual(path, "/v1/images/edits")
        self.assertEqual(sent["model"], "muse-image-1.0")
        self.assertEqual(sent["images"][0]["image_url"], URL)
        self.assertIn("713 wafers a day", sent["prompt"])
        self.assertEqual(r["model"], "muse-image-1.0")
        self.assertAlmostEqual(r["cost_usd"], 0.01)
        self.assertAlmostEqual(h.poster_meter.usd, 0.01)
        self.assertEqual(h.poster_meter.cap_usd, 1.0)
        self.assertEqual(Path(r["saved"]).read_bytes(), PNG)

    def test_PO8_a_webp_reply_is_kept_and_labelled_as_webp(self):
        webp = b"RIFF\x10\x00\x00\x00WEBPVP8X" + b"\x00" * 8
        self.reply = webp
        h = self.helper()
        r = h.poster_make(ASK)
        self.assertTrue(r["image"].startswith("data:image/webp;base64,"))
        self.assertTrue(r["saved"].endswith(".webp"))
        self.assertEqual(Path(r["saved"]).read_bytes(), webp)

    def test_PO5_a_meter_at_its_cap_sends_nothing(self):
        h = self.helper()
        h.poster_meter.usd = 1.0
        self.assertIn("error", h.poster_make(ASK))
        h = self.helper(spend_cap=1.0)
        h.meter.usd = 1.0
        self.assertIn("error", h.poster_make(ASK))
        self.assertEqual(self.heard, [])


if __name__ == "__main__":
    unittest.main()
