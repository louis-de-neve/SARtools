"""ASF adapter contract tests from a public Sentinel-1 GRD response."""

import copy
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from sartool.models import SearchQuery
from sartool.providers.asf import (
    GRD_LEVELS,
    STRIPMAP_BEAMS,
    ASFAdapter,
    ASFQueryError,
    ASFResultError,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/asf_sentinel1_grd.json").read_text()
)


def product(feature: dict):
    return SimpleNamespace(geojson=lambda: feature)


class ASFAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = SearchQuery(
            (-0.5, 51.3, 0.3, 51.7),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 8, tzinfo=UTC),
            max_results=10,
        )

    def test_search_passes_grd_filters_and_normalizes_result(self) -> None:
        captured = {}

        def search_pages(**options):
            captured.update(options)
            yield [product(FIXTURE)]

        scenes = ASFAdapter(search_pages).search(self.query)
        self.assertEqual(captured["dataset"], "SENTINEL-1")
        self.assertEqual(set(captured["processingLevel"]), set(GRD_LEVELS))
        self.assertEqual(
            captured["intersectsWith"],
            "POLYGON((-0.5 51.3,0.3 51.3,0.3 51.7,-0.5 51.7,-0.5 51.3))",
        )
        self.assertEqual(captured["start"], "2025-01-01T00:00:00Z")
        self.assertEqual(captured["maxResults"], 10)
        self.assertEqual(len(scenes), 1)
        scene = scenes[0]
        self.assertEqual(scene.id, f"asf:{FIXTURE['properties']['fileID']}")
        self.assertEqual(scene.product_type, "GRD_HD")
        self.assertEqual(scene.polarizations, ("VV", "VH"))
        self.assertEqual(scene.beam_mode, "IW")
        self.assertEqual(scene.size_bytes, 1012537715)
        self.assertEqual(scene.geometry, FIXTURE["geometry"])
        self.assertEqual(scene.download_url, FIXTURE["properties"]["url"])
        self.assertEqual(
            scene.to_feature()["properties"]["start"], "2025-01-06T17:58:16Z"
        )

    def test_deduplicates_across_pages_and_caps_results(self) -> None:
        second = copy.deepcopy(FIXTURE)
        second["properties"]["fileID"] = "another-grd-id"

        def search_pages(**_options):
            yield [product(FIXTURE)]
            yield [product(FIXTURE), product(second)]

        scenes = ASFAdapter(search_pages).search(self.query)
        self.assertEqual(
            [scene.id for scene in scenes],
            [f"asf:{FIXTURE['properties']['fileID']}", "asf:another-grd-id"],
        )
        limited = SearchQuery(
            self.query.bbox, self.query.start, self.query.end, max_results=1
        )
        self.assertEqual(len(ASFAdapter(search_pages).search(limited)), 1)

    def test_rejects_non_grd_or_incomplete_result(self) -> None:
        non_grd = copy.deepcopy(FIXTURE)
        non_grd["properties"]["processingLevel"] = "SLC"
        incomplete = copy.deepcopy(FIXTURE)
        del incomplete["properties"]["startTime"]
        for feature in (non_grd, incomplete):
            with (
                self.subTest(feature=feature["properties"]["processingLevel"]),
                self.assertRaises(ASFResultError),
            ):
                ASFAdapter(
                    lambda feature=feature, **_options: [[product(feature)]]
                ).search(self.query)

    def test_rejects_invalid_source_identity_and_download_metadata(self) -> None:
        for field, value in (
            ("platform", "Other satellite"),
            ("url", "http://example.com/product.zip"),
            ("bytes", True),
            ("stopTime", "2025-01-06T17:58:15Z"),
        ):
            feature = copy.deepcopy(FIXTURE)
            feature["properties"][field] = value
            with self.subTest(field=field), self.assertRaises(ASFResultError):
                ASFAdapter(
                    lambda feature=feature, **_options: [[product(feature)]]
                ).search(self.query)

    def test_normalizes_result_times_to_utc(self) -> None:
        feature = copy.deepcopy(FIXTURE)
        feature["properties"]["startTime"] = "2025-01-06T18:58:16+01:00"
        feature["properties"]["stopTime"] = "2025-01-06T18:58:41+01:00"
        scene = ASFAdapter(lambda **_options: [[product(feature)]]).search(self.query)[
            0
        ]
        self.assertEqual(
            scene.to_feature()["properties"]["start"], "2025-01-06T17:58:16Z"
        )

    def test_empty_search_returns_no_scenes(self) -> None:
        self.assertEqual(ASFAdapter(lambda **_options: []).search(self.query), [])

    def test_exact_dual_polarization_uses_single_asf_value(self) -> None:
        captured = {}

        def search_pages(**options):
            captured.update(options)
            return [[product(FIXTURE)]]

        query = SearchQuery(
            self.query.bbox,
            self.query.start,
            self.query.end,
            polarizations=("VV", "VH"),
        )
        ASFAdapter(search_pages).search(query)
        self.assertEqual(captured["polarization"], "VV+VH")
        unsupported = SearchQuery(
            self.query.bbox,
            self.query.start,
            self.query.end,
            polarizations=("VH",),
        )
        with self.assertRaisesRegex(ASFQueryError, "polarization combination"):
            ASFAdapter(search_pages).search(unsupported)

    def test_stripmap_queries_all_six_asf_beams(self) -> None:
        captured = {}

        def search_pages(**options):
            captured.update(options)
            return [[]]

        query = SearchQuery(
            self.query.bbox, self.query.start, self.query.end, beam_mode="SM"
        )
        ASFAdapter(search_pages).search(query)
        self.assertEqual(captured["beamMode"], STRIPMAP_BEAMS)


if __name__ == "__main__":
    unittest.main()
