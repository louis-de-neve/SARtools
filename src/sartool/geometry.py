"""Validation for geographic search areas supplied as GeoJSON."""

import json
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.validation import explain_validity


class GeometryError(ValueError):
    """The area of interest is unsuitable for catalogue search."""


def load_aoi(path: Path) -> tuple[dict[str, Any], tuple[float, float, float, float]]:
    """Read a WGS84 Polygon/MultiPolygon and return its geometry and bbox.

    The first search implementation cannot represent areas crossing the
    antimeridian as a single bbox. Such areas need splitting before search.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GeometryError(f"search.aoi does not exist: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise GeometryError(f"search.aoi cannot be read: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GeometryError(f"search.aoi is not valid GeoJSON: {exc.msg}") from exc

    if not isinstance(document, dict):
        raise GeometryError("search.aoi must contain a GeoJSON object")
    if "crs" in document:
        raise GeometryError(
            "search.aoi must use WGS84 longitude/latitude without a GeoJSON crs member"
        )
    geometry = (
        document.get("geometry") if document.get("type") == "Feature" else document
    )
    if not isinstance(geometry, dict) or geometry.get("type") not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise GeometryError(
            "search.aoi must be a GeoJSON Polygon, MultiPolygon, or Feature containing one"
        )
    try:
        polygon = shape(geometry)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise GeometryError("search.aoi has malformed polygon coordinates") from exc
    if polygon.is_empty or not polygon.is_valid:
        raise GeometryError(
            f"search.aoi has invalid geometry: {explain_validity(polygon)}"
        )
    west, south, east, north = polygon.bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise GeometryError(
            "search.aoi coordinates must be finite WGS84 longitude/latitude"
        )
    if east - west > 180:
        raise GeometryError(
            "search.aoi crosses the antimeridian or spans more than 180 degrees; split it into smaller areas"
        )
    return geometry, (west, south, east, north)
