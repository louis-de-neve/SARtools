"""CLI tests for discovery manifest and user-facing failures."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import asf_search

from sartool.cli import main
from sartool.models import SearchQuery
from sartool.providers.asf import ASFAdapter

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/asf_sentinel1_grd.json").read_text()
)
EXAMPLE = Path(__file__).parent.parent / "examples/sentinel1-grd.yaml"
ARGS = [
    "search",
    "asf",
    "--bbox",
    "-0.5",
    "51.3",
    "0.3",
    "51.7",
    "--start",
    "2025-01-01T00:00:00Z",
    "--end",
    "2025-01-08T00:00:00Z",
    "--limit",
    "1",
]


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        query = SearchQuery(
            (-0.5, 51.3, 0.3, 51.7),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 8, tzinfo=UTC),
            max_results=1,
        )
        product = SimpleNamespace(geojson=lambda: FIXTURE)
        self.scene = ASFAdapter(lambda **_options: [[product]]).search(query)[0]

    def test_stdout_manifest_contains_query_and_scene(self) -> None:
        stdout = io.StringIO()
        with patch("sartool.cli.ASFAdapter") as adapter_class, redirect_stdout(stdout):
            adapter_class.return_value.search.return_value = [self.scene]
            result = main(ARGS)
        self.assertEqual(result, 0)
        manifest = json.loads(stdout.getvalue())
        self.assertEqual(manifest["type"], "FeatureCollection")
        self.assertEqual(
            manifest["query"],
            {
                "provider": "asf",
                "product": "sentinel-1-grd",
                "bbox": [-0.5, 51.3, 0.3, 51.7],
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-08T00:00:00Z",
                "max_results": 1,
                "polarizations": None,
            },
        )
        self.assertEqual(manifest["features"][0]["id"], self.scene.id)

    def test_output_file_is_valid_geojson_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.geojson"
            with patch("sartool.cli.ASFAdapter") as adapter_class:
                adapter_class.return_value.search.return_value = []
                result = main([*ARGS, "--output", str(path)])
            self.assertEqual(result, 0)
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest["features"], [])
            self.assertEqual(manifest["query"]["provider"], "asf")

    def test_provider_error_returns_nonzero_without_manifest(self) -> None:
        stderr = io.StringIO()
        with patch("sartool.cli.ASFAdapter") as adapter_class, redirect_stderr(stderr):
            adapter_class.return_value.search.side_effect = asf_search.ASFSearchError(
                "service unavailable"
            )
            result = main(ARGS)
        self.assertEqual(result, 1)
        self.assertIn("ASF search failed: service unavailable", stderr.getvalue())

    def test_output_write_error_is_reported(self) -> None:
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            missing_parent = Path(directory) / "missing" / "results.geojson"
            with (
                patch("sartool.cli.ASFAdapter") as adapter_class,
                redirect_stderr(stderr),
            ):
                adapter_class.return_value.search.return_value = [self.scene]
                result = main([*ARGS, "--output", str(missing_parent)])
        self.assertEqual(result, 2)
        self.assertIn("Cannot write discovery manifest", stderr.getvalue())

    def test_search_uses_validated_config(self) -> None:
        stdout = io.StringIO()
        with patch("sartool.cli.ASFAdapter") as adapter_class, redirect_stdout(stdout):
            adapter_class.return_value.search.return_value = [self.scene]
            result = main(["search", "asf", "--config", str(EXAMPLE)])
        self.assertEqual(result, 0)
        query = adapter_class.return_value.search.call_args.args[0]
        self.assertEqual(query.polarizations, ("VV", "VH"))
        self.assertEqual(
            json.loads(stdout.getvalue())["query"]["polarizations"], ["VV", "VH"]
        )

    def test_config_validate_remains_available(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = main(["config", "validate", "--config", str(EXAMPLE)])
        self.assertEqual(result, 0)
        self.assertIn("Configuration valid", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
