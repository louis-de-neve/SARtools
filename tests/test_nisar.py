"""NISAR GCOV normalization through ASF search."""

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

import asf_search

from sartool.models import SearchQuery
from sartool.providers.nisar import NISARAdapter

FEATURE = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[-84, 13], [-81, 13], [-81, 16], [-84, 16], [-84, 13]]],
    },
    "properties": {
        "fileID": "NISAR_L2_PR_GCOV_EXAMPLE",
        "sceneName": "NISAR_L2_PR_GCOV_EXAMPLE",
        "platform": "NISAR",
        "processingLevel": "GCOV",
        "startTime": "2026-07-01T00:00:22Z",
        "stopTime": "2026-07-01T00:00:27Z",
        "url": "https://nisar.asf.earthdatacloud.nasa.gov/example.h5",
        "fileName": "example.h5",
        "bytes": {"example.h5": {"bytes": 123456, "format": "HDF5"}},
        "mainBandPolarization": ["HH", "HV"],
        "sideBandPolarization": ["HH", "HV"],
        "browse": ["https://nisar.asf.earthdatacloud.nasa.gov/example_LATLON.png"],
        "flightDirection": "ASCENDING",
    },
}


class NISARTests(unittest.TestCase):
    def test_search_normalizes_gcov_and_filter_options(self) -> None:
        options = {}
        product = SimpleNamespace(geojson=lambda: FEATURE)

        def search_pages(**kwargs):
            options.update(kwargs)
            return [[product]]

        query = SearchQuery(
            (-84, 13, -81, 16),
            datetime(2026, 6, 30, tzinfo=UTC),
            datetime(2026, 7, 2, tzinfo=UTC),
        )
        scenes = NISARAdapter(search_pages).search(query)
        self.assertEqual(options["dataset"], asf_search.DATASET.NISAR)
        self.assertEqual(options["processingLevel"], asf_search.PRODUCT_TYPE.GCOV)
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0].product_type, "GCOV_HDF5")
        self.assertEqual(scenes[0].polarizations, ("HH", "HV"))
        self.assertEqual(scenes[0].size_bytes, 123456)
        self.assertEqual(
            scenes[0].source_metadata["browse"][0], FEATURE["properties"]["browse"][0]
        )


if __name__ == "__main__":
    unittest.main()
