"""No paid model in the testing path (docs/RUNS.md, part 3). Written before the code. The founder: "No LLM in the
testing path". Every page test starts its helper with --no-model, the Python tests run with FABGYM_NO_MODEL=1, and a
helper so started cannot reach Meta's models: questions answer only from the examples, and Race the AI, posters and
sketches answer only from recorded replies (--stand-in). A fake model server a test names itself still works."""

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent import helper

ROOT = Path(__file__).resolve().parents[2]


class NoModel(unittest.TestCase):
    def test_every_page_test_helper_is_started_without_a_model(self):
        tracked = subprocess.run(["git", "ls-files", "web/tests"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        spawns = 0
        for name in tracked:
            if not name.endswith(".mjs"):
                continue
            text = (ROOT / name).read_text()
            for m in re.finditer(r'spawn\(\s*PY\s*,\s*\[([^\]]*"agent\.helper"[^\]]*)\]', text):
                spawns += 1
                self.assertIn('"--no-model"', m.group(1), f"{name}: a helper started without --no-model")
        self.assertGreater(spawns, 20, "the page tests' helpers were found")

    def test_the_python_tests_run_without_a_model(self):
        self.assertEqual(os.environ.get("FABGYM_NO_MODEL"), "1", "agent/tests sets FABGYM_NO_MODEL=1")

    def test_a_no_model_helper_reaches_no_model(self):
        with tempfile.TemporaryDirectory() as d:
            h = helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs", no_model=True)
            self.assertFalse(h.model_connected(), "no model for questions")
            self.assertFalse(h.meta_key_file.is_file(), "no key for Race the AI, posters and sketches")
            r = h.ask("What would a second polisher do to cycle time if demand rose by a fifth next quarter?")
            self.assertTrue(r.get("no_model"), r)
            race = h.race_step({"messages": [{"role": "user", "content": "go"}]})
            self.assertIn("error", race, "Race the AI refuses")
            # a fake model server a test names itself is still allowed
            fake = Path(d) / "fake.key"
            fake.write_text("not-a-real-key")
            h2 = helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs2", runs=Path(d) / "runs2", key_file=fake, base_url="http://127.0.0.1:9", no_model=True)
            self.assertTrue(h2.model_connected(), "an explicit key file for a fake server is kept")

    def test_the_environment_switch_is_the_same_as_the_flag(self):
        with tempfile.TemporaryDirectory() as d:
            h = helper.Helper(web=ROOT / "web", jobs=Path(d) / "jobs", runs=Path(d) / "runs")
            self.assertFalse(h.model_connected())
            self.assertFalse(h.meta_key_file.is_file())


if __name__ == "__main__":
    unittest.main()
