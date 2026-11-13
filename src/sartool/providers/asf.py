"""Sentinel-1 GRD discovery through the official ASF search package."""

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import asf_search

from sartool.models import Scene, SearchQuery

GRD_LEVELS = (
    asf_search.PRODUCT_TYPE.GRD_HD,
    asf_search.PRODUCT_TYPE.GRD_HS,
    asf_search.PRODUCT_TYPE.GRD_MD,
    asf_search.PRODUCT_TYPE.GRD_MS,
    asf_search.PRODUCT_TYPE.GRD_FD,
)
STRIPMAP_BEAMS = tuple(f"S{i}" for i in range(1, 7))


class ASFResultError(ValueError):
    """ASF returned a record without fields needed for discovery."""


class ASFQueryError(ValueError):
    """A search filter cannot be represented by ASF's Sentinel-1 catalogue."""


def _polarization_filter(values: tuple[str, ...] | None) -> str | None:
    if values is None:
        return None
    supported = {
        frozenset(("VV",)): asf_search.POLARIZATION.VV,
        frozenset(("HH",)): asf_search.POLARIZATION.HH,
        frozenset(("VV", "VH")): asf_search.POLARIZATION.VV_VH,
        frozenset(("HH", "HV")): asf_search.POLARIZATION.HH_HV,
        frozenset(("HH", "VV")): asf_search.POLARIZATION.HH_VV,
        frozenset(("HH", "HV", "VH", "VV")): asf_search.POLARIZATION.HH_HV_VH_VV,
    }
    try:
        return supported[frozenset(values)]
    except KeyError as exc:
        raise ASFQueryError(
            "ASF does not support this exact polarization combination"
        ) from exc


def _utc_string(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _bbox_wkt(bbox: tuple[float, float, float, float]) -> str:
    west, south, east, north = bbox
    return (
        f"POLYGON(({west} {south},{east} {south},{east} {north},"
        f"{west} {north},{west} {south}))"
    )


def _parse_time(value: str | None, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ASFResultError(f"ASF result has invalid {field}") from exc
    if parsed.tzinfo is None:
        raise ASFResultError(f"ASF result has timezone-free {field}")
    return parsed.astimezone(UTC)


def _normalize(product: Any) -> Scene:
    try:
        feature = product.geojson()
    except (AttributeError, TypeError) as exc:
        raise ASFResultError("ASF result cannot be read as GeoJSON") from exc
    try:
        properties = feature["properties"]
        file_id = properties["fileID"]
        name = properties["sceneName"]
        level = properties["processingLevel"]
        url = properties["url"]
        geometry = feature["geometry"]
        platform = properties["platform"]
    except (KeyError, TypeError) as exc:
        raise ASFResultError(
            "ASF result is missing required discovery metadata"
        ) from exc
    if not all(
        isinstance(value, str) and value
        for value in (file_id, name, level, url, platform)
    ):
        raise ASFResultError("ASF result has empty required discovery metadata")
    if (
        not isinstance(geometry, dict)
        or geometry.get("type") not in {"Polygon", "MultiPolygon"}
        or not geometry.get("coordinates")
    ):
        raise ASFResultError("ASF result has invalid geometry")
    if level not in GRD_LEVELS:
        raise ASFResultError(f"ASF result is not Sentinel-1 GRD: {level}")
    if not platform.startswith("Sentinel-1"):
        raise ASFResultError(f"ASF result is not Sentinel-1: {platform}")
    parsed_url = urlsplit(url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise ASFResultError("ASF result has invalid download URL")
    size = properties.get("bytes")
    if size is not None and (type(size) is not int or size < 0):
        raise ASFResultError("ASF result has invalid byte size")
    polarization = properties.get("polarization") or ""
    if not isinstance(polarization, str):
        raise ASFResultError("ASF result has invalid polarization")
    start = _parse_time(properties.get("startTime"), "startTime")
    end = _parse_time(properties.get("stopTime"), "stopTime")
    if start >= end:
        raise ASFResultError("ASF result has an invalid acquisition interval")
    return Scene(
        id=f"asf:{file_id}",
        provider="asf",
        name=name,
        start=start,
        end=end,
        geometry=geometry,
        platform=platform,
        product_type=level,
        polarizations=tuple(
            part.strip() for part in polarization.split("+") if part.strip()
        ),
        beam_mode=properties.get("beamModeType"),
        flight_direction=properties.get("flightDirection"),
        size_bytes=size,
        download_url=url,
        source_metadata=dict(properties),
    )


class ASFAdapter:
    """Search ASF for original Sentinel-1 GRD scenes."""

    def __init__(
        self, search_pages: Callable[..., Iterable[Iterable[Any]]] | None = None
    ):
        self._search_pages = search_pages or asf_search.search_generator

    def search(self, query: SearchQuery) -> list[Scene]:
        options = {
            "dataset": asf_search.DATASET.SENTINEL1,
            "processingLevel": GRD_LEVELS,
            "intersectsWith": _bbox_wkt(query.bbox),
            "start": _utc_string(query.start),
            "end": _utc_string(query.end),
            "maxResults": query.max_results,
        }
        polarization = _polarization_filter(query.polarizations)
        if query.beam_mode == "SM":
            options["beamMode"] = STRIPMAP_BEAMS
        elif query.beam_mode is not None:
            options["beamMode"] = query.beam_mode
        if polarization is not None:
            options["polarization"] = polarization
        scenes: list[Scene] = []
        seen: set[str] = set()
        for page in self._search_pages(**options):
            for product in page:
                scene = _normalize(product)
                if scene.id not in seen:
                    scenes.append(scene)
                    seen.add(scene.id)
                if len(scenes) >= query.max_results:
                    return scenes
        return scenes
