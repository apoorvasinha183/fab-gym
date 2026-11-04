"""Local HTTP boundary and shared model-budget regressions."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import helper, spend


class HelperRequests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        web = self.root / "web"
        (web / "data").mkdir(parents=True)
        (web / "data/areas.tsv").write_text("A\tCMP\n")
        self.h = helper.Helper(web=web, jobs=self.root / "jobs", runs=self.root / "runs", no_model=True)
        self.srv = helper.serve(self.h, 0)
        thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def request(self, body=b'{}', headers=None, path="/api/bar/log"):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("POST", path, body, headers or {"Content-Type": "application/json"})
        res = conn.getresponse()
        return res.status, res.read()

    def test_unrelated_website_cannot_write_a_run(self):
        with patch.object(self.h, "record_run", return_value={"id": "F-0001"}) as record:
            code, _ = self.request(b'{"kind":"floor"}', {
                "Content-Type": "text/plain", "Origin": "https://unrelated.example",
            }, "/api/runs/record")
            self.assertEqual(code, 403)
            record.assert_not_called()

    def test_rebound_host_cannot_reach_the_api(self):
        code, _ = self.request(headers={"Host": "unrelated.example", "Content-Type": "application/json"})
        self.assertEqual(code, 403)

    def test_local_page_and_native_clients_work(self):
        for origin in (None, f"http://127.0.0.1:{self.srv.server_port}"):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            code, body = self.request(headers=headers)
            self.assertEqual(code, 200)
            self.assertIsInstance(json.loads(body), dict)

    def test_bad_request_returns_json_instead_of_dropping_connection(self):
        for raw in (b'[]', b'null', b'{"seed":"oops"}', b'{"days":NaN}', b'{"days":1e309}'):
            code, body = self.request(raw, path="/api/fab/run")
            self.assertEqual(code, 400, raw)
            self.assertIn("error", json.loads(body))

    def test_negative_or_oversized_body_is_refused_before_reading(self):
        for size, expected in (("-1", 400), (str(32 * 1024 * 1024), 413)):
            code, _ = self.request(b'', {"Content-Type": "application/json", "Content-Length": size})
            self.assertEqual(code, expected)

    def test_ask_meter_obeys_spend_from_other_features(self):
        self.h.poster_meter.add_usd(self.h.total_cap)
        with self.assertRaises(spend.CapReached):
            self.h.meter.check()

    def test_concurrent_features_share_one_budget_gate(self):
        first_inside, second_started = threading.Event(), threading.Event()
        outcomes = []

        def first():
            with self.h.poster_meter.request():
                first_inside.set()
                self.assertTrue(second_started.wait(5))
                self.h.poster_meter.add_usd(self.h.total_cap)

        def second():
            first_inside.wait(5)
            second_started.set()
            try:
                with self.h.meter.request():
                    outcomes.append("sent")
            except spend.CapReached:
                outcomes.append("blocked")

        threads = [threading.Thread(target=f) for f in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes, ["blocked"])


if __name__ == "__main__":
    unittest.main()
