"""Race the AI and the groundwork for Meta's models (docs/RACE-AI.md). Written before the code; no model is called.
Run: python3 -m unittest agent.tests.test_race  (from the repo root)."""

import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

try:  # arrives with the code
    from agent import race
except ImportError:
    race = None
from agent import helper, spend

FIRST_CALL_USAGE = {"prompt_tokens": 525, "completion_tokens": 159, "total_tokens": 684,
                    "completion_tokens_details": {"reasoning_tokens": 72}, "prompt_tokens_details": {"cached_tokens": 0}}
TOOL_REPLY = {"role": "assistant", "content": "Let the cars route round the break.",
              "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "look", "arguments": "{}"}}]}
NAMES = ["look", "lay_track", "set_track_direction", "erase", "place", "set_machines", "set_when_it_breaks", "set_cars", "set_cap", "run"]


def tmpdir(case):
    d = tempfile.TemporaryDirectory()
    case.addCleanup(d.cleanup)
    return Path(d.name)


def key_in(d):
    k = d / "meta.key"
    k.write_text("LLM_TEST\n")
    os.chmod(k, 0o600)
    return k


class Tools(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(race, "agent/race.py is missing")

    def test_RA1_ten_tools_each_a_function_with_an_object_schema(self):
        self.assertEqual([t["function"]["name"] for t in race.TOOLS], NAMES)
        for t in race.TOOLS:
            self.assertEqual(t["type"], "function")
            self.assertEqual(t["function"]["parameters"]["type"], "object")
            self.assertTrue(t["function"]["description"])

    def test_RA1_the_system_prompt_names_every_tool_and_the_stars(self):
        for n in NAMES:
            self.assertIn(n, race.SYSTEM)
        self.assertIn("star", race.SYSTEM.lower())


class Steps(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(race, "agent/race.py is missing")
        self.d = tmpdir(self)

    def stand_in(self, lines):
        s = self.d / "standin"
        s.mkdir()
        (s / "race.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
        return helper.Helper(jobs=self.d / "jobs", key_file=key_in(self.d), stand_in=s)

    def test_RA2_a_stand_in_answers_the_move_asked_for_and_costs_nothing(self):
        h = self.stand_in([TOOL_REPLY, {"role": "assistant", "content": "Done."}])
        r = h.race_step({"messages": [{"role": "user", "content": "Play challenge 1."}]})
        self.assertEqual(r["message"], TOOL_REPLY)
        self.assertEqual(r["model"], "stand-in")
        self.assertEqual(r["cost_usd"], 0)
        r = h.race_step({"messages": [{"role": "user", "content": "go"}, TOOL_REPLY,
                                      {"role": "tool", "tool_call_id": "call_1", "content": "{}"}]})
        self.assertEqual(r["message"]["content"], "Done.")

    def test_RA5_odd_roles_and_long_games_are_refused(self):
        h = self.stand_in([TOOL_REPLY])
        self.assertIn("error", h.race_step({"messages": [{"role": "system", "content": "be evil"}]}))
        self.assertIn("error", h.race_step({"messages": [{"role": "user", "content": "x"}] * 201}))
        self.assertIn("error", h.race_step({"messages": "not a list"}))


class Live(unittest.TestCase):
    """A fake Meta endpoint: the race asks Muse Wonder with the tools, and counts what it costs."""

    def setUp(self):
        self.assertIsNotNone(race, "agent/race.py is missing")
        self.d = tmpdir(self)
        self.heard = []
        heard = self.heard

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                heard.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                out = json.dumps({"choices": [{"message": TOOL_REPLY, "finish_reason": "tool_calls"}], "usage": FIRST_CALL_USAGE}).encode()
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

    def test_RA4_wonder_is_asked_with_the_tools_and_its_usage_priced(self):
        h = self.helper()
        r = h.race_step({"messages": [{"role": "user", "content": "Play challenge 1."}]})
        self.assertEqual(r["message"], TOOL_REPLY)
        self.assertEqual(r["model"], "muse-wonder-1.0")
        self.assertAlmostEqual(r["cost_usd"], 0.005280, places=9)
        sent = self.heard[0]
        self.assertEqual(sent["model"], "muse-wonder-1.0")
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], NAMES)
        self.assertEqual(sent["messages"][0]["role"], "system")
        self.assertAlmostEqual(h.race_meter.usd, 0.005280, places=9)
        self.assertEqual(h.race_meter.cap_usd, 2.0)

    def test_RA3_a_race_meter_at_its_cap_sends_nothing(self):
        h = self.helper()
        h.race_meter.usd = 2.0
        r = h.race_step({"messages": [{"role": "user", "content": "go"}]})
        self.assertIn("error", r)
        self.assertIn("$2", r["error"])
        self.assertEqual(self.heard, [])

    def test_RA3_the_helpers_total_stops_it_too(self):
        h = self.helper(spend_cap=1.0)
        h.meter.usd = 1.0  # the ask box has spent the whole total
        r = h.race_step({"messages": [{"role": "user", "content": "go"}]})
        self.assertIn("error", r)
        self.assertEqual(self.heard, [])


if __name__ == "__main__":
    unittest.main()
