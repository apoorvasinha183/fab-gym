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

try:  # the command-line pieces arrive with the effort and header-file options
    from agent.fabgym_agent import build_parser, http_model_from_args  # noqa: E402
except ImportError:
    build_parser = http_model_from_args = None

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
            self.assertIn("SMT2020 testbed", md)
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


class Budget(unittest.TestCase):
    """The model thinks before it answers (about 2,000 tokens a real task, docs/BASETEN-PRICING.md), and the
    thinking counts against max_tokens. A reply cut off at the limit is asked again once with twice the room;
    a reply still empty after that is an error, never a silent empty string."""

    def serve(self, replies):
        """A stand-in endpoint answering each request with the next (content, finish_reason) in `replies`."""
        heard = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                heard.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                content, finish = replies[min(len(heard), len(replies)) - 1]
                msg = {"role": "assistant", "content": content}
                out = json.dumps({"choices": [{"message": msg, "finish_reason": finish}]}).encode()
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
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        kf = Path(d.name) / "key"
        kf.write_text("sk-TEST\n")
        os.chmod(kf, 0o600)
        return f"http://127.0.0.1:{srv.server_port}/v1", kf, heard

    def test_the_default_leaves_room_to_think_and_answer(self):
        url, kf, heard = self.serve([(fenced(FIFO), "stop")])
        HttpModel(base_url=url, model="m", key_file=kf).complete([{"role": "user", "content": "write a rule"}])
        self.assertGreaterEqual(heard[0]["max_tokens"], 4000)

    def test_a_reply_cut_off_is_asked_again_with_twice_the_room(self):
        url, kf, heard = self.serve([(None, "length"), (fenced(FIFO), "stop")])
        m = HttpModel(base_url=url, model="m", key_file=kf, max_tokens=1500)
        reply = m.complete([{"role": "user", "content": "write a rule"}])
        self.assertIn("```rust", reply)
        self.assertEqual([h["max_tokens"] for h in heard], [1500, 3000])
        self.assertEqual(heard[0]["messages"], heard[1]["messages"])

    def test_a_reply_cut_off_twice_with_no_text_is_an_error(self):
        url, kf, heard = self.serve([(None, "length")])
        m = HttpModel(base_url=url, model="m", key_file=kf, max_tokens=1500)
        with self.assertRaises(RuntimeError) as e:
            m.complete([{"role": "user", "content": "write a rule"}])
        self.assertEqual(len(heard), 2)
        self.assertIn("max_tokens", str(e.exception))

    def test_a_reply_cut_off_twice_with_some_text_returns_that_text(self):
        url, kf, heard = self.serve([("```rust\npub fn key(", "length")])
        m = HttpModel(base_url=url, model="m", key_file=kf, max_tokens=1500)
        self.assertEqual(m.complete([{"role": "user", "content": "write a rule"}]), "```rust\npub fn key(")
        self.assertEqual(len(heard), 2)

    def test_a_finished_reply_is_asked_once(self):
        url, kf, heard = self.serve([(fenced(FIFO), "stop")])
        HttpModel(base_url=url, model="m", key_file=kf, max_tokens=1500).complete([{"role": "user", "content": "x"}])
        self.assertEqual(len(heard), 1)


class Options(unittest.TestCase):
    """How hard the model thinks is the biggest cost (docs/BASETEN-PRICING.md): the client sends a
    reasoning_effort when one is set. Some endpoints log in with their own headers (Modal's Modal-Key and
    Modal-Secret); their values are read from files and never shown, like the key."""

    SECRET_ID, SECRET = "wk-TESTID" + "Q7" * 6, "ws-TESTSECRET" + "R8" * 6

    def serve(self, status=200, echo_headers=False):
        heard = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                heard.append({"headers": dict(self.headers.items()), "body": body})
                if status == 200:
                    msg = {"role": "assistant", "content": fenced(FIFO)}
                    out = json.dumps({"choices": [{"message": msg, "finish_reason": "stop"}]}).encode()
                else:
                    out = json.dumps({"error": "bad login", "seen": dict(self.headers.items())}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        files = {}
        for name, value in (("key", "sk-TEST"), ("modal.id", self.SECRET_ID), ("modal.secret", self.SECRET)):
            f = Path(d.name) / name
            f.write_text(value + "\n")
            os.chmod(f, 0o600)
            files[name] = f
        return f"http://127.0.0.1:{srv.server_port}/v1", files, heard

    def test_an_effort_is_sent_when_set(self):
        url, files, heard = self.serve()
        HttpModel(base_url=url, model="m", key_file=files["key"], reasoning_effort="low").complete(
            [{"role": "user", "content": "x"}]
        )
        self.assertEqual(heard[0]["body"]["reasoning_effort"], "low")

    def test_no_effort_is_sent_when_none_is_set(self):
        url, files, heard = self.serve()
        HttpModel(base_url=url, model="m", key_file=files["key"]).complete([{"role": "user", "content": "x"}])
        self.assertNotIn("reasoning_effort", heard[0]["body"])

    def modal(self, url, files):
        return HttpModel(
            base_url=url,
            model="m",
            key_file=None,
            header_files={"Modal-Key": files["modal.id"], "Modal-Secret": files["modal.secret"]},
        )

    def test_header_files_are_sent_and_no_key_means_no_bearer_line(self):
        url, files, heard = self.serve()
        self.modal(url, files).complete([{"role": "user", "content": "x"}])
        h = {k.lower(): v for k, v in heard[0]["headers"].items()}
        self.assertEqual(h["modal-key"], self.SECRET_ID)
        self.assertEqual(h["modal-secret"], self.SECRET)
        self.assertNotIn("authorization", h)

    def test_header_values_are_never_shown(self):
        url, files, heard = self.serve(status=401)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            m = self.modal(url, files)
            shown = repr(m) + str(m)
            with self.assertRaises(RuntimeError) as e:
                m.complete([{"role": "user", "content": "x"}])
        self.assertIn("401", str(e.exception))
        for text in (out.getvalue(), err.getvalue(), shown, str(e.exception)):
            self.assertNotIn(self.SECRET_ID, text)
            self.assertNotIn(self.SECRET, text)

    def test_a_missing_header_file_says_which(self):
        with self.assertRaises(FileNotFoundError) as e:
            HttpModel(base_url="http://127.0.0.1:9/v1", model="m", key_file=None,
                      header_files={"Modal-Secret": Path("/nonexistent/modal.secret")})
        self.assertIn("/nonexistent/modal.secret", str(e.exception))

    def test_the_command_line_takes_effort_header_files_and_no_key(self):
        url, files, heard = self.serve()
        a = build_parser().parse_args([
            "run", "--question", "q", "--shop", "s", "--out", "o", "--model", "m", "--base-url", url,
            "--key-file", "none", "--reasoning-effort", "low",
            "--header-file", f"Modal-Key={files['modal.id']}", "--header-file", f"Modal-Secret={files['modal.secret']}",
        ])
        http_model_from_args(a).complete([{"role": "user", "content": "x"}])
        h = {k.lower(): v for k, v in heard[0]["headers"].items()}
        self.assertEqual(heard[0]["body"]["reasoning_effort"], "low")
        self.assertEqual(h["modal-secret"], self.SECRET)
        self.assertNotIn("authorization", h)


if __name__ == "__main__":
    unittest.main()
