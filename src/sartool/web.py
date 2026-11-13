"""Local browser interface for ASF scene discovery."""

import json
import math
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

import asf_search
import requests

from sartool.models import SearchQuery
from sartool.providers.asf import ASFAdapter, ASFQueryError, ASFResultError


def parse_query(data: object) -> SearchQuery:
    """Validate browser input before querying ASF."""
    if not isinstance(data, dict):
        raise TypeError("request must be a JSON object")
    try:
        bbox = data["bbox"]
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError("bbox must contain four numbers")
        if any(isinstance(value, bool) for value in bbox):
            raise ValueError("bbox must contain numbers")
        bounds = tuple(float(value) for value in bbox)
        if not all(math.isfinite(value) for value in bounds):
            raise ValueError("bbox must contain finite numbers")
        start = datetime.fromisoformat(data["start"])
        end = datetime.fromisoformat(data["end"])
        limit = data.get("max_results", 50)
        if type(limit) is not int or limit > 200:
            raise ValueError("max_results must be an integer from 1 to 200")
        polarization = data.get("polarization", "any")
        options = {
            "any": None,
            "VV+VH": ("VV", "VH"),
            "HH+HV": ("HH", "HV"),
            "VV": ("VV",),
            "HH": ("HH",),
        }
        if polarization not in options:
            raise ValueError("unsupported polarization")
        beam_mode = data.get("beam_mode", "any")
        if beam_mode not in ("any", "IW", "EW", "SM"):
            raise ValueError("unsupported beam mode")
        return SearchQuery(
            bounds,
            start,
            end,
            limit,
            options[polarization],
            None if beam_mode == "any" else beam_mode,
        )
    except (KeyError, TypeError, OverflowError, ValueError) as exc:
        raise ValueError(f"invalid search input: {exc}") from exc


class GUIHandler(BaseHTTPRequestHandler):
    """Serve the page and a local JSON search endpoint."""

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        body = files("sartool").joinpath("web/index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/search":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("request body must be between 1 and 8192 bytes")
            data = json.loads(self.rfile.read(length))
            query = parse_query(data)
        except (TypeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})
            return
        try:
            scenes = ASFAdapter().search(query)
        except (
            ASFQueryError,
            ASFResultError,
            asf_search.ASFError,
            asf_search.CMRError,
            requests.RequestException,
        ) as exc:
            self._json(502, {"error": f"ASF search failed: {exc}"})
            return
        self._json(
            200,
            {
                "type": "FeatureCollection",
                "bbox": list(query.bbox),
                "features": [scene.to_feature() for scene in scenes],
            },
        )


def serve(port: int = 8765, *, open_browser: bool = True) -> int:
    """Run a loopback-only server until interrupted."""
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), GUIHandler)
    except OSError as exc:
        print(f"Cannot start GUI: {exc}")
        return 1
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"SARtool GUI: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
