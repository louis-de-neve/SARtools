"""Umbra Open Data STAC and public S3 asset resolution."""

import unittest
from datetime import UTC, datetime
from unittest.mock import Mock

from sartool.models import SearchQuery
from sartool.providers.umbra import UmbraAdapter

ROOT = UmbraAdapter.ROOT
YEAR = ROOT.replace("/catalog.json", "/2025/catalog.json")
MONTH = YEAR.replace("/catalog.json", "/2025-06/catalog.json")
DAY = MONTH.replace("/catalog.json", "/2025-06-22/catalog.json")
ITEM_URL = DAY.replace("/catalog.json", "/example/example.json")
TASK = "3e56976b-fa2b-4035-bb71-385efde84c4a"
KEY = f"sar-data/tasks/{TASK}/2025-06-22_UMBRA-10/2025-06-22_UMBRA-10_GEC.tif"
LISTING = (
    '<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    f"<Contents><Key>{KEY}</Key><Size>12345</Size></Contents></ListBucketResult>"
).encode()
GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [[159.1, -31.9], [159.4, -31.9], [159.4, -31.6], [159.1, -31.6], [159.1, -31.9]]
    ],
}
ITEM = {
    "id": "01e9fe39-3a6e-4458-a5d1-cf92eb21b961",
    "geometry": GEOMETRY,
    "properties": {
        "datetime": "2025-06-22T23:57:59Z",
        "start_datetime": "2025-06-22T23:57:53Z",
        "end_datetime": "2025-06-22T23:58:06Z",
        "platform": "Umbra-10",
        "sar:product_type": "GEC",
        "sar:instrument_mode": "SPOTLIGHT",
        "sar:polarizations": ["HH"],
        "umbra:task_id": TASK,
    },
    "assets": {"image": {"href": "", "roles": ["data"]}},
}
PAGES = {
    ROOT: {"links": [{"rel": "child", "title": "2025", "href": "./2025/catalog.json"}]},
    YEAR: {
        "links": [
            {"rel": "child", "title": "2025-06", "href": "./2025-06/catalog.json"}
        ]
    },
    MONTH: {
        "links": [
            {"rel": "child", "title": "2025-06-22", "href": "./2025-06-22/catalog.json"}
        ]
    },
    DAY: {"links": [{"rel": "item", "href": "./example/example.json"}]},
    ITEM_URL: ITEM,
}


class UmbraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = SearchQuery(
            (159.1, -31.9, 159.4, -31.6),
            datetime(2025, 6, 22, tzinfo=UTC),
            datetime(2025, 6, 23, tzinfo=UTC),
        )
        self.session = Mock()

        def get(url, **_kwargs):
            return (
                Mock(content=LISTING)
                if url == UmbraAdapter.BUCKET
                else Mock(json=lambda: PAGES[url])
            )

        self.session.get.side_effect = get

    def test_resolves_public_gec_asset(self) -> None:
        scenes = UmbraAdapter(self.session).search(self.query)
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0].product_type, "GEC")
        self.assertEqual(scenes[0].size_bytes, 12345)
        self.assertEqual(scenes[0].download_url, UmbraAdapter.BUCKET + KEY)
        self.assertEqual(scenes[0].platform, "Umbra-10")

    def test_area_filter_avoids_bucket_listing(self) -> None:
        query = SearchQuery((0, 0, 1, 1), self.query.start, self.query.end)
        self.assertEqual(UmbraAdapter(self.session).search(query), [])
        self.assertEqual(self.session.get.call_count, 5)


if __name__ == "__main__":
    unittest.main()
