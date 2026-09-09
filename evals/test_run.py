import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from evals import run


class BuildPlanTests(unittest.TestCase):
    def test_default_plan_contains_off_on_pair(self):
        self.assertEqual(
            run.build_plan(1),
            [{"arm": "off", "repeat": 1}, {"arm": "on", "repeat": 1}],
        )

    def test_off_plan_contains_only_off(self):
        self.assertEqual(run.build_plan(2, "off"), [
            {"arm": "off", "repeat": 1},
            {"arm": "off", "repeat": 2},
        ])

    def test_on_plan_contains_only_on(self):
        self.assertEqual(run.build_plan(2, "on"), [
            {"arm": "on", "repeat": 1},
            {"arm": "on", "repeat": 2},
        ])


class DryRunTests(unittest.TestCase):
    def test_dry_run_does_not_call_provider(self):
        case = Path(__file__).parent / "cases" / "job-recovery.json"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "dry-run"
            stdout = io.StringIO()
            with patch.object(run.subprocess, "run", side_effect=AssertionError("provider called")):
                with redirect_stdout(stdout):
                    result = run.main([
                        "--engine", "codex",
                        "--case", str(case),
                        "--output", str(output),
                        "--dry-run",
                    ])

            self.assertEqual(result, 0)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(stdout.getvalue())["runs"], run.build_plan(1))


if __name__ == "__main__":
    unittest.main()
