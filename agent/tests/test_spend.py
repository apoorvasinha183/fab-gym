"""The ask box on Meta, and counting spend (docs/BASETEN-PRICING.md, last section). Written before the code.
Run: python3 -m unittest agent.tests.test_spend  (from the repo root)."""

import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from agent.fabgym_agent import HttpModel

try:  # arrives with the code
    from agent import spend
except ImportError:
    spend = None
try:
    from agent import helper
except ImportError:
    helper = None

CONTRIB = {"input": 0.10, "input_cached": 0.002, "output": 0.20}
USAGE = {"prompt_tokens": 1000, "completion_tokens": 500, "prompt_tokens_details": {"cached_tokens": 200}}
USAGE_USD = (800 * 0.10 + 200 * 0.002 + 500 * 0.20) / 1e6


def tmpdir(case):
    d = tempfile.TemporaryDirectory()
    case.addCleanup(d.cleanup)
    return Path(d.name)


class Prices(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(spend, "agent/spend.py is missing")

    def test_the_contributor_price_comes_from_the_pricing_file(self):
        self.assertEqual(spend.price("meta", "muse-spark-1.3-contributor"), CONTRIB)

    def test_the_open_weights_price_on_baseten(self):
        self.assertEqual(spend.price("baseten", "meta-models/muse-spark-open-1026"),
                         {"input": 1.25, "input_cached": 0.15, "output": 4.25})

    def test_a_model_with_no_price_is_refused_and_never_counted_as_free(self):
        with self.assertRaises(KeyError):
            spend.price("meta", "no-such-model")
        with self.assertRaises(KeyError):
            spend.price("modal", "meta-models/Muse-Spark-Open-816B-A42B")  # its price page needs a sign-in


class Cost(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(spend, "agent/spend.py is missing")

    def test_cached_and_uncached_input_and_output_each_at_their_price(self):
        self.assertAlmostEqual(spend.cost(CONTRIB, USAGE), USAGE_USD, places=12)

    def test_no_cache_field_means_nothing_was_cached(self):
        u = {"prompt_tokens": 1000, "completion_tokens": 500}
        self.assertAlmostEqual(spend.cost(CONTRIB, u), (1000 * 0.10 + 500 * 0.20) / 1e6, places=12)

    def test_an_answer_with_no_usage_is_an_error(self):
        with self.assertRaises(ValueError):
            spend.cost(CONTRIB, None)


class Meter(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(spend, "agent/spend.py is missing")

    def test_it_counts_calls_and_dollars(self):
        m = spend.Meter(CONTRIB, cap_usd=1.0)
        m.add(USAGE)
        m.add(USAGE)
        self.assertEqual(m.calls, 2)
        self.assertAlmostEqual(m.usd, 2 * USAGE_USD, places=12)

    def test_it_refuses_once_the_cap_is_reached(self):
        m = spend.Meter(CONTRIB, cap_usd=0.0001)
        m.check()  # under the cap: fine
        m.add({"prompt_tokens": 0, "completion_tokens": 1000})  # $0.0002
        with self.assertRaises(spend.CapReached) as e:
            m.check()
        self.assertIn("0.0001", str(e.exception))

    def test_a_restart_keeps_the_total(self):
        f = tmpdir(self) / "spend.json"
        m = spend.Meter(CONTRIB, cap_usd=5.0, path=f)
        m.add(USAGE)
        again = spend.Meter(CONTRIB, cap_usd=5.0, path=f)
        self.assertEqual(again.calls, 1)
        self.assertAlmostEqual(again.usd, USAGE_USD, places=12)


class Client(unittest.TestCase):
    """HttpModel(meter=...) counts every request it sends, the retry included."""

    def setUp(self):
        self.assertIsNotNone(spend, "agent/spend.py is missing")

    def serve(self, replies):
        heard = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                heard.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                content, finish = replies[min(len(heard), len(replies)) - 1]
                out = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
                                  "usage": USAGE}).encode()
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
        kf = tmpdir(self) / "key"
        kf.write_text("LLM_TEST\n")
        os.chmod(kf, 0o600)
        return f"http://127.0.0.1:{srv.server_port}/v1", kf, heard

    def test_each_request_is_counted_including_the_retry(self):
        url, kf, heard = self.serve([(None, "length"), ("ok", "stop")])
        meter = spend.Meter(CONTRIB, cap_usd=1.0)
        m = HttpModel(url, "m", key_file=kf, max_tokens=100, meter=meter)
        self.assertEqual(m.complete([{"role": "user", "content": "hi"}]), "ok")
        self.assertEqual(meter.calls, 2)
        self.assertEqual(m.last_usage, USAGE)

    def test_a_meter_at_its_cap_sends_nothing(self):
        url, kf, heard = self.serve([("ok", "stop")])
        meter = spend.Meter(CONTRIB, cap_usd=0.0)
        m = HttpModel(url, "m", key_file=kf, meter=meter)
        with self.assertRaises(spend.CapReached):
            m.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(heard, [])


class AskBox(unittest.TestCase):
    """The floor page's helper asks Meta's contributor model at low effort by default."""

    def setUp(self):
        self.assertIsNotNone(spend, "agent/spend.py is missing")
        self.d = tmpdir(self)
        self.key = self.d / "meta.key"
        self.key.write_text("LLM_TEST\n")
        os.chmod(self.key, 0o600)

    def test_the_default_is_meta_contributor_at_low_effort(self):
        self.assertEqual(helper.PRESETS["meta"]["key_file"], Path.home() / ".config" / "fab-gym" / "meta.key")
        h = helper.Helper(key_file=self.key, jobs=self.d / "jobs")
        self.assertEqual(h.base_url, "https://api.meta.ai/v1")
        self.assertEqual(h.model_name, "muse-spark-1.3-contributor")
        self.assertEqual(h.reasoning_effort, "low")

    def test_the_open_preset_asks_spark_open_on_baseten(self):
        h = helper.Helper(preset="open", key_file=self.key, jobs=self.d / "jobs")
        self.assertEqual(h.base_url, "https://inference.baseten.co/v1")
        self.assertEqual(h.model_name, "meta-models/muse-spark-open-1026")

    def test_the_client_carries_the_effort_and_the_meter(self):
        h = helper.Helper(key_file=self.key, jobs=self.d / "jobs", spend_cap=2.0)
        c = h.client()
        self.assertEqual(c.reasoning_effort, "low")
        self.assertIs(c.meter, h.meter)
        self.assertEqual(h.meter.cap_usd, 2.0)
        self.assertEqual(h.meter.path, self.d / "spend.json")

    def test_status_names_the_model_and_reports_spend(self):
        h = helper.Helper(key_file=self.key, jobs=self.d / "jobs")
        s = h.status()
        self.assertEqual(s["model"], "muse-spark-1.3-contributor on Meta")
        self.assertEqual(set(s["spend"]), {"calls", "usd", "cap_usd"})
        self.assertEqual(s["spend"]["cap_usd"], 5.0)


if __name__ == "__main__":
    unittest.main()
