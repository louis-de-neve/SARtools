"""ICEYE Open Data footprint search and STAC normalization."""

import unittest
from datetime import UTC, datetime
from unittest.mock import Mock

from sartool.models import SearchQuery
from sartool.providers.iceye import ICEYEAdapter, ICEYEResultError

HOST = "https://iceye-open-data-catalog.s3.amazonaws.com"
GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[10, 36.7], [10.3, 36.7], [10.3, 37], [10, 37], [10, 36.7]]],
}
ITEM = {
    "id": "ICEYE_EXAMPLE",
    "geometry": GEOMETRY,
    "properties": {
        "start_datetime": "2023-12-20T01:21:10Z",
        "end_datetime": "2023-12-20T01:21:21Z",
        "platform": "ICEYE-X7",
        "sar:instrument_mode": "spotlight",
        "sar:polarizations": ["VV"],
        "sat:orbit_state": "descending",
    },
    "assets": {
        "grd-cog": {"href": f"{HOST}/data/example_GRD.tif"},
        "graphic": {"href": f"{HOST}/data/example_THM.png"},
    },
}
INDEX = {
    "features": [
        {
            "geometry": GEOMETRY,
            "properties": {
                "datetime": "2023-12-20T01:21:15Z",
                "platform": "ICEYE-X7",
                "href": f"{HOST}/stac-items/example.json",
            },
        }
    ]
}


class ICEYETests(unittest.TestCase):
    def setUp(self) -> None:
        self.query = SearchQuery(
            (10, 36.7, 10.3, 37),
            datetime(2023, 12, 20, tzinfo=UTC),
            datetime(2023, 12, 21, tzinfo=UTC),
        )
        self.session = Mock()
        self.session.get.side_effect = [
            Mock(json=lambda: INDEX),
            Mock(json=lambda: ITEM),
        ]

    def test_public_grd_item_is_normalized(self) -> None:
        scenes = ICEYEAdapter(self.session).search(self.query)
        self.assertEqual(len(scenes), 1)
        scene = scenes[0]
        self.assertEqual(scene.platform, "ICEYE-X7")
        self.assertEqual(scene.product_type, "GRD_COG")
        self.assertEqual(scene.beam_mode, "spotlight")
        self.assertEqual(scene.download_url, f"{HOST}/data/example_GRD.tif")
        self.assertEqual(
            scene.source_metadata["assets"]["graphic"]["href"],
            f"{HOST}/data/example_THM.png",
        )

    def test_filters_before_fetching_items(self) -> None:
        other_area = SearchQuery((0, 0, 1, 1), self.query.start, self.query.end)
        self.session.get.side_effect = [Mock(json=lambda: INDEX)]
        self.assertEqual(ICEYEAdapter(self.session).search(other_area), [])
        self.assertEqual(self.session.get.call_count, 1)

    def test_undated_pair_summary_does_not_block_valid_scene(self) -> None:
        pair = {
            "geometry": GEOMETRY,
            "properties": {
                "id": "tenerife-pair-1_2",
                "datetime": None,
                "platform": None,
                "href": f"{HOST}/stac-items/pairs/tenerife/1_2.json",
            },
        }
        index = {"features": [pair, *INDEX["features"]]}
        self.session.get.side_effect = [
            Mock(json=lambda: index),
            Mock(json=lambda: ITEM),
        ]
        scenes = ICEYEAdapter(self.session).search(self.query)
        self.assertEqual([scene.name for scene in scenes], ["ICEYE_EXAMPLE"])
        self.assertEqual(self.session.get.call_count, 2)

    def test_filters_mode_and_polarization(self) -> None:
        query = SearchQuery(
            self.query.bbox,
            self.query.start,
            self.query.end,
            polarizations=("HH",),
            beam_mode="stripmap",
        )
        self.assertEqual(ICEYEAdapter(self.session).search(query), [])

    def test_skips_items_without_grd(self) -> None:
        self.session.get.side_effect = [
            Mock(json=lambda: INDEX),
            Mock(
                json=lambda: {**ITEM, "assets": {"graphic": ITEM["assets"]["graphic"]}}
            ),
        ]
        self.assertEqual(ICEYEAdapter(self.session).search(self.query), [])

    def test_rejects_item_url_outside_public_bucket(self) -> None:
        index = {
            "features": [
                {
                    **INDEX["features"][0],
                    "properties": {
                        "datetime": "2023-12-20T01:21:15Z",
                        "platform": "ICEYE-X7",
                        "href": "https://example.com/item.json",
                    },
                }
            ]
        }
        self.session.get.side_effect = [Mock(json=lambda: index)]
        with self.assertRaises(ICEYEResultError):
            ICEYEAdapter(self.session).search(self.query)


if __name__ == "__main__":
    unittest.main()
