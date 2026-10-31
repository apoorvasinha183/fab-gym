"""Sketch to fab (docs/SKETCH.md). Written before the code; no model is called.
Run: python3 -m unittest agent.tests.test_sketch  (from the repo root)."""

import base64
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

try:  # arrives with the code
    from agent import sketch
except ImportError:
    sketch = None
from agent import helper

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAAABJRU5ErkJggg==")
URL = "data:image/png;base64," + base64.b64encode(PNG).decode()
READ = {"boxes": [{"box": [60, 60, 160, 140], "word": "litho", "kind": "litho"},
                  {"box": [300, 60, 400, 140], "word": "polish", "kind": ""},
                  {"box": [440, 60, 470, 140], "word": "coffee", "kind": "kitchen"}],
        "lines": [[[110, 140], [110, 240], [350, 240], [350, 140]]]}


def tmpdir(case):
    d = tempfile.TemporaryDirectory()
    case.addCleanup(d.cleanup)
    return Path(d.name)


def key_in(d):
    k = d / "meta.key"
    k.write_text("LLM_TEST\n")
    os.chmod(k, 0o600)
    return k


class Read(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(sketch, "agent/sketch.py is missing")
        self.fab = sketch.to_fab(READ)

    def test_SK1_kinds_words_and_what_is_left_out(self):
        self.assertEqual([p["piece"] for p in self.fab["pieces"]], ["litho", "cmp"])
        self.assertTrue(any("coffee" in n for n in self.fab["notes"]), self.fab["notes"])
        self.assertEqual(sketch.kind_of("", "store"), "stocker")
        self.assertEqual(sketch.kind_of("", "in"), "entry")
        self.assertEqual(sketch.kind_of("", "out"), "exit")
        self.assertIsNone(sketch.kind_of("", "coffee"))

    def test_SK2_the_scale_and_the_snap(self):
        a, b = self.fab["pieces"]
        self.assertEqual(b["x"] - a["x"], 5, "100-pixel boxes are 2 tiles, so a tile is 50 pixels: centres 240 apart are 5 tiles")
        self.assertEqual(a["y"], b["y"])
        w, h = self.fab["floor"]
        for p in self.fab["pieces"]:
            self.assertTrue(1 <= p["x"] and p["x"] + 2 <= w - 1 and 1 <= p["y"] and p["y"] + 2 <= h - 1, "a margin all round")

    def test_SK3_lines_become_neighbouring_tiles_and_stop_at_pieces(self):
        paths = self.fab["paths"]
        self.assertTrue(paths)
        taken = {(p["x"] + i, p["y"] + j) for p in self.fab["pieces"] for i in range(2) for j in range(2)}
        for path in paths:
            for (x0, y0), (x1, y1) in zip(path, path[1:]):
                self.assertEqual(abs(x1 - x0) + abs(y1 - y0), 1, "neighbours")
            for c in path:
                self.assertNotIn(tuple(c), taken, "no track under a piece")
        self.assertEqual(sketch.manhattan([[1, 1], [4, 1], [4, 3]]), [[1, 1], [2, 1], [3, 1], [4, 1], [4, 2], [4, 3]])


class Stubs(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(sketch, "agent/sketch.py is missing")

    def test_SK7_a_line_that_ends_at_a_machine_goes_there_and_back(self):
        reading = {"boxes": [{"box": [100, 0, 200, 100], "word": "litho", "kind": "litho"}],
                   "lines": [[[0, 250], [400, 250]], [[150, 250], [150, 100]]]}
        fab = sketch.to_fab(reading)
        stub = [p for p in fab["paths"] if len(p) > 1 and p[0][0] == p[-1][0] and p[0][1] == p[-1][1]]
        self.assertTrue(stub, f"the stub comes back to where it left the line: {fab['paths']}")
        for (x0, y0), (x1, y1) in zip(stub[0], stub[0][1:]):
            self.assertEqual(abs(x1 - x0) + abs(y1 - y0), 1)

    def test_SK7_a_spur_off_a_spine_that_runs_beside_machines(self):
        # the spine passes right under two machines; the spur leaves it downwards to storage
        reading = {"boxes": [{"box": [100, 0, 200, 100], "word": "litho", "kind": "litho"},
                             {"box": [200, 0, 300, 100], "word": "etch", "kind": "dry"},
                             {"box": [200, 200, 300, 300], "word": "store", "kind": "stocker"}],
                   "lines": [[[0, 125], [400, 125]], [[275, 125], [275, 200]]]}
        fab = sketch.to_fab(reading)
        stub = [p for p in fab["paths"] if len(p) > 1 and p[0] == p[-1]]
        self.assertTrue(stub, f"the spur to storage comes back: {fab['paths']}")
        self.assertEqual([p for p in fab["paths"] if len(p) > 1 and p[0] != p[-1] and len(p) > 5][0][0][1],
                         stub[0][0][1], "the spur starts on the spine")


    def test_SK7_a_line_from_a_machine_across_the_spine_to_another(self):
        # read live: one line from dry etch, across the spine, down to storage; both ends are spurs off the spine
        reading = {"boxes": [{"box": [200, 0, 300, 100], "word": "etch", "kind": "dry"},
                             {"box": [200, 300, 300, 400], "word": "store", "kind": "stocker"}],
                   "lines": [[[0, 175], [500, 175]], [[275, 100], [275, 300]]]}
        fab = sketch.to_fab(reading)
        spine = max(fab["paths"], key=lambda q: abs(q[-1][0] - q[0][0]))
        y = spine[0][1]
        cross = [q for q in fab["paths"] if q is not spine][0]
        self.assertEqual(cross[0], cross[-1], f"starts and ends on the spine: {cross}")
        self.assertEqual(cross[0][1], y)
        ys = [c[1] for c in cross]
        self.assertTrue(min(ys) < y < max(ys), "goes up to etch and down to storage")
        for (x0, y0), (x1, y1) in zip(cross, cross[1:]):
            self.assertEqual(abs(x1 - x0) + abs(y1 - y0), 1)


class Route(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(sketch, "agent/sketch.py is missing")
        self.d = tmpdir(self)

    def test_SK4_only_a_picture_and_a_stand_in_costs_nothing(self):
        s = self.d / "standin"
        s.mkdir()
        (s / "sketch.json").write_text(json.dumps(READ))
        h = helper.Helper(jobs=self.d / "jobs", key_file=key_in(self.d), stand_in=s)
        self.assertIn("error", h.sketch_read({"image": "https://example.com/x.png"}))
        r = h.sketch_read({"image": URL})
        self.assertEqual(r["model"], "stand-in")
        self.assertEqual(r["cost_usd"], 0)
        self.assertEqual([p["piece"] for p in r["pieces"]], ["litho", "cmp"])

    def test_SK4_live_spark_is_sent_the_picture_and_counted(self):
        heard = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                heard.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                out = json.dumps({"choices": [{"message": {"role": "assistant", "content": json.dumps(READ)}, "finish_reason": "stop"}],
                                  "usage": {"prompt_tokens": 296, "completion_tokens": 486}}).encode()
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
        h = helper.Helper(jobs=self.d / "jobs", key_file=key_in(self.d), meta_key_file=key_in(self.d),
                          meta_base_url=f"http://127.0.0.1:{srv.server_port}/v1")
        r = h.sketch_read({"image": URL})
        sent = heard[0]
        self.assertEqual(sent["model"], "muse-spark-1.3-contributor")
        parts = sent["messages"][-1]["content"]
        self.assertTrue(any(p.get("type") == "image_url" and p["image_url"]["url"] == URL for p in parts))
        self.assertEqual([p["piece"] for p in r["pieces"]], ["litho", "cmp"])
        self.assertGreater(h.sketch_meter.usd, 0)
        self.assertEqual(h.sketch_meter.cap_usd, 2.0)  # raised 1 Nov by quiz
        h.sketch_meter.usd = h.sketch_meter.cap_usd
        n = len(heard)
        self.assertIn("error", h.sketch_read({"image": URL}))
        self.assertEqual(len(heard), n, "nothing sent at the cap")


if __name__ == "__main__":
    unittest.main()
