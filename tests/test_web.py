"""Combined GUI search validation and API behavior."""

import io
import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sartool.providers.iceye import ICEYEResultError
from sartool.web import GUIHandler, parse_query

INPUT = {
    "bbox": [-0.5, 51.3, 0.3, 51.7],
    "start": "2025-01-01T00:00:00Z",
    "end": "2025-01-08T00:00:00Z",
    "max_results": 10,
    "polarization": "any",
}


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


class GUITests(unittest.TestCase):
    def test_query_parses_shared_filters(self) -> None:
        query = parse_query(INPUT)
        self.assertIsNone(query.polarizations)
        self.assertEqual(query.max_results, 10)
        self.assertEqual(
            parse_query({**INPUT, "polarization": "VV+VH"}).polarizations,
            ("VV", "VH"),
        )
        self.assertEqual(parse_query({**INPUT, "sentinel_mode": "SM"}).beam_mode, "SM")

    def test_bad_query_is_rejected(self) -> None:
        for change in (
            {"bbox": [-0.5, 51.3, 0.3]},
            {"end": "2024-01-01T00:00:00Z"},
            {"max_results": 201},
            {"polarization": "VH"},
            {"provider": "asf"},
            {"beam_mode": "SM"},
            {"sentinel_mode": "spotlight"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_query({**INPUT, **change})

    def test_page_and_combined_search(self) -> None:
        page = handler("/")
        page.do_GET()
        self.assertEqual(page.status, 200)
        self.assertIn(b"Search all satellites", page.wfile.getvalue())
        self.assertIn(b"tile.openstreetmap.org", page.wfile.getvalue())
        self.assertNotIn(b'id="provider"', page.wfile.getvalue())

        start = datetime(2025, 1, 2, tzinfo=UTC)
        scene = SimpleNamespace(
            id="iceye:test", start=start, to_feature=lambda: {"id": "iceye:test"}
        )
        adapters = {
            "asf": Mock(search=Mock(return_value=[])),
            "iceye": Mock(search=Mock(return_value=[scene])),
            "capella": Mock(search=Mock(return_value=[])),
            "umbra": Mock(search=Mock(return_value=[])),
            "nisar": Mock(search=Mock(return_value=[])),
        }
        request = handler("/api/search", json.dumps(INPUT).encode())
        with patch(
            "sartool.web.make_adapter", side_effect=adapters.__getitem__
        ) as factory:
            request.do_POST()
        self.assertEqual(request.status, 200)
        self.assertEqual(
            [call.args[0] for call in factory.call_args_list],
            ["asf", "iceye", "capella", "umbra", "nisar"],
        )
        result = json.loads(request.wfile.getvalue())
        self.assertEqual(
            result["counts"],
            {"asf": 0, "iceye": 1, "capella": 0, "umbra": 0, "nisar": 0},
        )
        self.assertEqual(result["sources"]["nisar"], "NISAR")
        self.assertEqual(result["features"], [{"id": "iceye:test"}])

    def test_sentinel_mode_does_not_filter_other_satellites(self) -> None:
        adapters = {
            "asf": Mock(search=Mock(return_value=[])),
            "iceye": Mock(search=Mock(return_value=[])),
            "capella": Mock(search=Mock(return_value=[])),
            "umbra": Mock(search=Mock(return_value=[])),
            "nisar": Mock(search=Mock(return_value=[])),
        }
        request = handler(
            "/api/search", json.dumps({**INPUT, "sentinel_mode": "SM"}).encode()
        )
        with patch("sartool.web.make_adapter", side_effect=adapters.__getitem__):
            request.do_POST()
        self.assertEqual(request.status, 200)
        self.assertEqual(adapters["asf"].search.call_args.args[0].beam_mode, "SM")
        self.assertIsNone(adapters["iceye"].search.call_args.args[0].beam_mode)
        self.assertIsNone(adapters["capella"].search.call_args.args[0].beam_mode)
        self.assertIsNone(adapters["umbra"].search.call_args.args[0].beam_mode)
        self.assertIsNone(adapters["nisar"].search.call_args.args[0].beam_mode)

    def test_partial_and_total_failures(self) -> None:
        adapters = {
            "asf": Mock(search=Mock(return_value=[])),
            "iceye": Mock(search=Mock(side_effect=ICEYEResultError("offline"))),
            "capella": Mock(search=Mock(return_value=[])),
            "umbra": Mock(search=Mock(return_value=[])),
            "nisar": Mock(search=Mock(return_value=[])),
        }
        request = handler("/api/search", json.dumps(INPUT).encode())
        with patch("sartool.web.make_adapter", side_effect=adapters.__getitem__):
            request.do_POST()
        self.assertEqual(request.status, 200)
        self.assertIn("iceye", json.loads(request.wfile.getvalue())["errors"])

        adapters["asf"].search.side_effect = ICEYEResultError("offline")
        adapters["capella"].search.side_effect = ICEYEResultError("offline")
        adapters["umbra"].search.side_effect = ICEYEResultError("offline")
        adapters["nisar"].search.side_effect = ICEYEResultError("offline")
        request = handler("/api/search", json.dumps(INPUT).encode())
        with patch("sartool.web.make_adapter", side_effect=adapters.__getitem__):
            request.do_POST()
        self.assertEqual(request.status, 502)
        self.assertEqual(len(json.loads(request.wfile.getvalue())["errors"]), 5)

    def test_bad_request(self) -> None:
        request = handler("/api/search", b"{}")
        request.do_POST()
        self.assertEqual(request.status, 400)


if __name__ == "__main__":
    unittest.main()
