"""CLI validation behaves the same as the config library."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sartool.config_cli import main

EXAMPLE = Path(__file__).parent.parent / "examples/sentinel1-grd.yaml"


class ConfigCLITests(unittest.TestCase):
    def test_example_can_be_validated(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = main(["config", "validate", "--config", str(EXAMPLE)])
        self.assertEqual(result, 0)
        self.assertIn("Configuration valid", stdout.getvalue())

    def test_missing_file_reports_error(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = main(
                ["config", "validate", "--config", str(EXAMPLE.parent / "missing.yaml")]
            )
        self.assertEqual(result, 2)
        self.assertIn("config file does not exist", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
