"""Capella Open Data catalog traversal and scene normalization."""

import unittest
from datetime import UTC, datetime
from unittest.mock import Mock

from sartool.models import SearchQuery
from sartool.providers.capella import CapellaAdapter, CapellaResultError

ROOT = CapellaAdapter.INDEX
YEAR = ROOT.replace("/catalog.json", "/capella-open-data-2025/catalog.json")
MONTH = YEAR.replace("/catalog.json", "/capella-open-data-2025-01/catalog.json")
DAY = MONTH.replace("/catalog.json", "/capella-open-data-2025-01-01/catalog.json")
ITEM_URL = DAY.replace("/catalog.json", "/CAPELLA_C13_SP_GEO_HH_EXAMPLE/item.json")
GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [[-118.2, 34.7], [-118.0, 34.7], [-118.0, 34.9], [-118.2, 34.9], [-118.2, 34.7]]
    ],
}
ITEM = {
    "id": "CAPELLA_C13_SP_GEO_HH_EXAMPLE",
    "geometry": GEOMETRY,
    "properties": {
        "datetime": "2025-01-01T18:07:42Z",
        "start_datetime": "2025-01-01T18:07:41Z",
        "end_datetime": "2025-01-01T18:07:44Z",
        "platform": "capella-13",
        "sar:product_type": "GEO",
        "sar:polarizations": ["HH"],
        "sar:instrument_mode": "spotlight",
        "sat:orbit_state": "ascending",
    },
    "assets": {
        "HH": {
            "href": "https://capella-open-data.s3.amazonaws.com/data/example.tif",
            "roles": ["data"],
        },
        "thumbnail": {
            "href": "https://capella-open-data.s3.amazonaws.com/data/example_thumb.png",
            "roles": ["thumbnail"],
        },
    },
}
PAGES = {
    ROOT: {
        "links": [
            {
                "rel": "child",
                "title": "Capella Open Data 2025",
                "href": "./capella-open-data-2025/catalog.json",
            }
        ]
    },
    YEAR: {
        "links": [
            {
                "rel": "child",
                "title": "Capella Open Data 2025-01",
                "href": "./capella-open-data-2025-01/catalog.json",
            }
        ]
    },
    MONTH: {
        "links": [
            {
                "rel": "child",
                "title": "Capella Open Data 2025-01-01",
                "href": "./capella-open-data-2025-01-01/catalog.json",
            }
        ]
    },
    DAY: {
        "links": [
            {"rel": "item", "href": "./CAPELLA_C13_SP_SLC_HH_EXAMPLE/item.json"},
            {"rel": "item", "href": "./CAPELLA_C13_SP_GEO_HH_EXAMPLE/item.json"},
        ]
    },
    ITEM_URL: ITEM,
}


class CapellaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = SearchQuery(
            (-118.2, 34.7, -118.0, 34.9),
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 1, 2, tzinfo=UTC),
            max_results=10,
        )
        self.session = Mock()
        self.session.get.side_effect = lambda url, **_kwargs: Mock(
            json=lambda: PAGES[url]
        )

    def test_finds_detected_scene_and_skips_slc_item(self) -> None:
        scenes = CapellaAdapter(self.session).search(self.query)
        self.assertEqual(len(scenes), 1)
        self.assertEqual(self.session.get.call_count, 5)
        scene = scenes[0]
        self.assertEqual(scene.provider, "capella")
        self.assertEqual(scene.product_type, "GEO_COG")
        self.assertEqual(scene.platform, "Capella-13")
        self.assertEqual(scene.beam_mode, "spotlight")
        self.assertEqual(scene.download_url, ITEM["assets"]["HH"]["href"])
        self.assertEqual(
            scene.source_metadata["assets"]["thumbnail"]["href"],
            ITEM["assets"]["thumbnail"]["href"],
        )

    def test_filters_spatial_extent_and_polarization(self) -> None:
        other_area = SearchQuery((0, 0, 1, 1), self.query.start, self.query.end)
        self.assertEqual(CapellaAdapter(self.session).search(other_area), [])
        vv_query = SearchQuery(
            self.query.bbox, self.query.start, self.query.end, polarizations=("VV",)
        )
        self.assertEqual(CapellaAdapter(self.session).search(vv_query), [])

    def test_rejects_item_asset_outside_public_bucket(self) -> None:
        bad_item = {
            **ITEM,
            "assets": {
                "HH": {"href": "https://example.com/data.tif", "roles": ["data"]}
            },
        }
        pages = {**PAGES, ITEM_URL: bad_item}
        self.session.get.side_effect = lambda url, **_kwargs: Mock(
            json=lambda: pages[url]
        )
        with self.assertRaises(CapellaResultError):
            CapellaAdapter(self.session).search(self.query)


if __name__ == "__main__":
    unittest.main()
