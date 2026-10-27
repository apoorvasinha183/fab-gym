"""The agent loop (docs/AGENT.md), with a stand-in model and the real scorer on the toy shop.
Written before the code. Run: python3 -m unittest agent.tests.test_loop  (from the repo root)."""

import contextlib
import http.server
import io
import json
import os
import re
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "target" / "release" / "fabrule"
SHOP = ROOT / "golden" / "toy" / "mixed.shop.txt"

from agent.fabgym_agent import HttpModel, Scorer, StandInModel, finalise, search, sign  # noqa: E402

FIFO = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { -c.waited_minutes }"
SPT = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { c.proc_minutes - 1e-6 * c.waited_minutes }"
SLACK = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { c.cqt_slack_minutes.min(600.0) - 0.5 * c.waited_minutes }"
BROKEN = "pub fn key(c: &Cand, _x: &Ctx) -> f64 { c.nope }"


def fenced(src):
    return "Here is a rule.\n\n```rust\n" + src + "\n```\n"


class Recording(StandInModel):
    """A stand-in that also keeps every message it was sent."""

    def __init__(self, replies):
        super().__init__(replies)
        self.seen = []

    def complete(self, messages):
        self.seen.append(json.dumps(messages))
        return super().complete(messages)


def build_cli():
    if not CLI.exists():
        subprocess.run(["cargo", "build", "--release", "-p", "fabrule"], cwd=ROOT, check=True)


def scorer():
    return Scorer(cli=CLI, shop=SHOP, train=range(100, 104), threads=2)


class Loop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_cli()

    def test_a_search_ends_in_an_unsigned_card_of_the_scorers_numbers(self):
        model = StandInModel([fenced(FIFO), fenced(SPT), fenced(BROKEN), fenced(SLACK)])
        s = search("Etch is down tomorrow, what do we do?", model, scorer(), generations=2, per_generation=2)
        self.assertEqual(len(s.candidates), 4)
        self.assertEqual(sum(1 for c in s.candidates if c["ok"]), 3)
        with tempfile.TemporaryDirectory() as d:
            card = finalise(s, scorer(), top=2, out_dir=Path(d))
            self.assertTrue((Path(d) / "card.json").exists())
            self.assertTrue((Path(d) / "card.md").exists())
            self.assertIsNone(card["signed_by"])
            self.assertEqual(card["seeds"], list(range(10)))
            self.assertEqual(len(card["finalists"]), 2)
            for f in card["finalists"]:
                # the card's numbers are the scorer's, run again here on the held-out seeds
                again = scorer().score(f["source"], held_out=True)
                self.assertEqual(f["held_out"], again)
                self.assertTrue(f["held_out"]["held_out"])
            md = (Path(d) / "card.md").read_text()
            self.assertIn("SMT2020 model", md)
            self.assertIn("Not signed", md)
            for f in card["finalists"]:
                rew = [m for m in f["held_out"]["vs_today"] if m["key"] == "reward"][0]["interval"]
                for k in ("mean", "lo", "hi"):
                    self.assertIn(f"{rew[k]:+.2f}", md)

    def test_the_model_never_sees_a_held_out_score(self):
        model = Recording([fenced(FIFO), fenced(SPT), fenced(SLACK)])
        s = search("q", model, scorer(), generations=3, per_generation=1)
        with tempfile.TemporaryDirectory() as d:
            finalise(s, scorer(), top=2, out_dir=Path(d))
        self.assertTrue(model.seen)
        for m in model.seen:
            self.assertNotIn('\\"held_out\\": true', m)
            self.assertNotIn('"held_out": true', m)
            self.assertIsNone(re.search(r"seeds?\D{0,12}\[0, 1, 2", m), "held-out seeds named to the model")

    def test_the_compilers_words_reach_the_model(self):
        model = Recording([fenced(BROKEN), fenced(FIFO)])
        s = search("q", model, scorer(), generations=2, per_generation=1)
        self.assertFalse(s.candidates[0]["ok"])
        self.assertIn("nope", s.candidates[0]["error"])
        self.assertIn("nope", model.seen[1])

    def test_a_reply_without_code_is_recorded_and_the_search_goes_on(self):
        model = StandInModel(["I would run first in first out.", fenced(FIFO)])
        s = search("q", model, scorer(), generations=2, per_generation=1)
        self.assertFalse(s.candidates[0]["ok"])
        self.assertIn("no rust code", s.candidates[0]["error"].lower())
        self.assertTrue(s.candidates[1]["ok"])

    def test_signing(self):
        model = StandInModel([fenced(FIFO), fenced(SPT)])
        s = search("q", model, scorer(), generations=1, per_generation=2)
        with tempfile.TemporaryDirectory() as d:
            finalise(s, scorer(), top=2, out_dir=Path(d))
            path = Path(d) / "card.json"
            signed = sign(path, "Operations head")
            self.assertEqual(signed["signed_by"], "Operations head")
            self.assertTrue(signed["signed_at"])
            self.assertIn("Signed by Operations head", (Path(d) / "card.md").read_text())
            with self.assertRaises(ValueError):
                sign(path, "Someone else")
        with tempfile.TemporaryDirectory() as d:
            finalise(s, scorer(), top=2, out_dir=Path(d))
            path = Path(d) / "card.json"
            card = json.loads(path.read_text())
            card["finalists"][0]["held_out"]["arms"][0]["reward"][0] += 1.0
            path.write_text(json.dumps(card))
            with self.assertRaises(ValueError):
                sign(path, "Operations head")


class Key(unittest.TestCase):
    def test_the_key_is_sent_and_never_shown(self):
        secret = "sk-TEST-" + "Z9" * 12
        heard = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                heard["auth"] = self.headers.get("Authorization")
                heard["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = json.dumps({"choices": [{"message": {"role": "assistant", "content": fenced(FIFO)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                kf = Path(d) / "key"
                kf.write_text(secret + "\n")
                os.chmod(kf, 0o600)
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    m = HttpModel(base_url=f"http://127.0.0.1:{srv.server_port}/v1", model="test-model", key_file=kf)
                    reply = m.complete([{"role": "user", "content": "write a rule"}])
                    shown = repr(m) + str(m)
            self.assertIn("```rust", reply)
            self.assertEqual(heard["auth"], "Bearer " + secret)
            self.assertEqual(heard["body"]["model"], "test-model")
            for text in (out.getvalue(), err.getvalue(), shown, json.dumps(heard["body"])):
                self.assertNotIn(secret, text)
        finally:
            srv.shutdown()

    def test_a_missing_key_says_where_it_should_be_without_guessing(self):
        with self.assertRaises(FileNotFoundError) as e:
            HttpModel(base_url="http://127.0.0.1:9/v1", model="m", key_file=Path("/nonexistent/fab-gym.key"))
        self.assertIn("/nonexistent/fab-gym.key", str(e.exception))


if __name__ == "__main__":
    unittest.main()
