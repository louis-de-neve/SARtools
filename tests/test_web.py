"""Local GUI request validation and API behavior."""

import io
import json
import unittest
from unittest.mock import patch

from sartool.web import GUIHandler, parse_query

INPUT = {
    "bbox": [-0.5, 51.3, 0.3, 51.7],
    "start": "2025-01-01T00:00:00Z",
    "end": "2025-01-08T00:00:00Z",
    "max_results": 10,
    "polarization": "VV+VH",
}


class GUITests(unittest.TestCase):
    def test_query_parses_exact_dual_polarization(self) -> None:
        query = parse_query(INPUT)
        self.assertEqual(query.polarizations, ("VV", "VH"))
        self.assertEqual(query.max_results, 10)
        self.assertEqual(parse_query({**INPUT, "beam_mode": "SM"}).beam_mode, "SM")

    def test_bad_query_is_rejected(self) -> None:
        for change in (
            {"bbox": [-0.5, 51.3, 0.3]},
            {"end": "2024-01-01T00:00:00Z"},
            {"max_results": 201},
            {"polarization": "VH"},
            {"beam_mode": "S1"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_query({**INPUT, **change})

    def test_page_and_search_endpoint(self) -> None:
        def handler(path: str, body: bytes = b"") -> GUIHandler:
            instance = GUIHandler.__new__(GUIHandler)
            instance.path = path
            instance.headers = {"Content-Length": str(len(body))}
            instance.rfile = io.BytesIO(body)
            instance.wfile = io.BytesIO()
            instance.send_response = lambda status: setattr(instance, "status", status)
            instance.send_header = lambda *_args: None
            instance.end_headers = lambda: None
            return instance

        page = handler("/")
        page.do_GET()
        self.assertEqual(page.status, 200)
        self.assertIn(b"Scene footprints", page.wfile.getvalue())
        self.assertIn(b"tile.openstreetmap.org", page.wfile.getvalue())
        self.assertIn(b"Draw search area", page.wfile.getvalue())

        request = handler("/api/search", json.dumps(INPUT).encode())
        with patch("sartool.web.ASFAdapter") as adapter:
            adapter.return_value.search.return_value = []
            request.do_POST()
            self.assertEqual(request.status, 200)
            self.assertEqual(json.loads(request.wfile.getvalue())["features"], [])
            self.assertEqual(adapter.return_value.search.call_count, 1)

        bad_request = handler("/api/search", b"{}")
        bad_request.do_POST()
        self.assertEqual(bad_request.status, 400)


if __name__ == "__main__":
    unittest.main()
