"""Tests for provider-independent search validation."""

import unittest
from datetime import UTC, datetime, timedelta, timezone

from sartool.models import SearchQuery


class SearchQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2025, 1, 1, tzinfo=UTC)
        self.end = datetime(2025, 2, 1, tzinfo=UTC)

    def test_accepts_wgs84_bbox_and_aware_interval(self) -> None:
        query = SearchQuery((-5.0, 50.0, -4.0, 51.0), self.start, self.end)
        self.assertEqual(query.bbox, (-5.0, 50.0, -4.0, 51.0))

    def test_rejects_reversed_or_out_of_range_bbox(self) -> None:
        for bbox in ((-4.0, 50.0, -5.0, 51.0), (-181.0, 50.0, -4.0, 51.0)):
            with self.subTest(bbox=bbox), self.assertRaisesRegex(ValueError, "WGS84"):
                SearchQuery(bbox, self.start, self.end)

    def test_rejects_naive_or_reversed_interval(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            SearchQuery((-5.0, 50.0, -4.0, 51.0), datetime(2025, 1, 1), self.end)
        with self.assertRaisesRegex(ValueError, "earlier"):
            SearchQuery((-5.0, 50.0, -4.0, 51.0), self.end, self.start)

    def test_normalizes_aware_interval_to_utc(self) -> None:
        london_winter = timezone(timedelta(hours=1))
        local_start = datetime(2025, 1, 1, 1, tzinfo=london_winter)
        query = SearchQuery((-5.0, 50.0, -4.0, 51.0), local_start, self.end)
        self.assertEqual(query.start, self.start)
        self.assertEqual(query.start.tzinfo, UTC)

    def test_rejects_nonpositive_result_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_results"):
            SearchQuery((-5.0, 50.0, -4.0, 51.0), self.start, self.end, max_results=0)

    def test_rejects_duplicate_polarizations(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicates"):
            SearchQuery(
                (-5.0, 50.0, -4.0, 51.0),
                self.start,
                self.end,
                polarizations=("VV", "VV"),
            )


if __name__ == "__main__":
    unittest.main()
