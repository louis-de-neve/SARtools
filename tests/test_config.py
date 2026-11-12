"""Config contract checks for dates, AOI, CRS, and path semantics."""

import json
import tempfile
import unittest
from datetime import UTC
from pathlib import Path

from sartool.config import ConfigError, load_config

EXAMPLES = Path(__file__).parent.parent / "examples"


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "project" / "examples"
        self.directory.mkdir(parents=True)
        self.aoi = self.directory / "aoi.geojson"
        self.aoi.write_text(
            (EXAMPLES / "aoi.geojson").read_text(encoding="utf-8"), encoding="utf-8"
        )
        self.config = self.directory / "sentinel1-grd.yaml"
        self.template = (EXAMPLES / "sentinel1-grd.yaml").read_text(encoding="utf-8")
        self.config.write_text(self.template, encoding="utf-8")

    def change(self, old: str, new: str) -> None:
        self.assertIn(old, self.template)
        self.config.write_text(self.template.replace(old, new), encoding="utf-8")

    def test_example_validates_and_resolves_relative_paths(self) -> None:
        loaded = load_config(self.config)
        self.assertEqual(loaded.schema_version, 1)
        self.assertEqual(loaded.search.bbox, (-0.5, 51.3, 0.3, 51.7))
        self.assertEqual(loaded.search.start.tzinfo, UTC)
        self.assertEqual(loaded.search.providers, ("asf",))
        self.assertEqual(loaded.output.root, self.directory.parent / "data")
        self.assertEqual(loaded.output.target_crs, "EPSG:32630")
        self.assertEqual(loaded.search_query().max_results, 10)
        self.assertEqual(loaded.search_query().polarizations, ("VV", "VH"))

    def test_missing_aoi_and_self_intersecting_polygon_report_field(self) -> None:
        self.change("./aoi.geojson", "./missing.geojson")
        with self.assertRaisesRegex(ConfigError, "search.aoi does not exist"):
            load_config(self.config)
        self.config.write_text(self.template, encoding="utf-8")
        bad = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]],
        }
        self.aoi.write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "search.aoi has invalid geometry"):
            load_config(self.config)

    def test_invalid_date_and_crs_report_field(self) -> None:
        self.change("2025-01-08T00:00:00Z", "2024-12-01T00:00:00Z")
        with self.assertRaisesRegex(ConfigError, "search.start must be earlier"):
            load_config(self.config)
        self.change("EPSG:32630", "EPSG:999999")
        with self.assertRaisesRegex(
            ConfigError, "output.target_crs is not a recognized CRS"
        ):
            load_config(self.config)
        self.change("EPSG:32630", "EPSG:4326")
        with self.assertRaisesRegex(ConfigError, "projected CRS with metre units"):
            load_config(self.config)

    def test_bad_root_and_unsafe_template_report_field(self) -> None:
        bad_root = self.directory.parent / "occupied"
        bad_root.write_text("file", encoding="utf-8")
        self.change("../data", "../occupied")
        with self.assertRaisesRegex(ConfigError, "output.root is an existing file"):
            load_config(self.config)
        self.change("{provider}/{mission}/{year}/{scene_id}", "../{scene_id}")
        with self.assertRaisesRegex(ConfigError, "output.folder_template"):
            load_config(self.config)
        for unsafe in (r"..\{scene_id}", r"C:\data\{scene_id}", "C:/data/{scene_id}"):
            with self.subTest(unsafe=unsafe):
                self.change(
                    'folder_template: "{provider}/{mission}/{year}/{scene_id}"',
                    f"folder_template: '{unsafe}'",
                )
                with self.assertRaisesRegex(ConfigError, "output.folder_template"):
                    load_config(self.config)

    def test_schema_and_provider_values_are_constrained(self) -> None:
        self.change("schema_version: 1", "schema_version: 2")
        with self.assertRaisesRegex(ConfigError, "schema_version must be 1"):
            load_config(self.config)
        self.change("providers: [asf]", "providers: [unknown]")
        with self.assertRaisesRegex(
            ConfigError, "search.providers contains unsupported values"
        ):
            load_config(self.config)

    def test_unknown_keys_are_rejected(self) -> None:
        self.change("max_results: 10", "max_result: 10")
        with self.assertRaisesRegex(ConfigError, "search has unknown key.*max_result"):
            load_config(self.config)
        self.change("schema_version: 1", "schema_version: 1\nunknown: true")
        with self.assertRaisesRegex(ConfigError, "config has unknown key.*unknown"):
            load_config(self.config)


if __name__ == "__main__":
    unittest.main()
