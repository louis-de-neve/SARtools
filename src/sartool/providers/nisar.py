"""Discovery of NISAR GCOV products through ASF search."""

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import asf_search

from sartool.models import Scene, SearchQuery
from sartool.providers.asf import _bbox_wkt, _utc_string


class NISARResultError(ValueError):
    """ASF returned an unusable NISAR GCOV record."""


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise NISARResultError("NISAR record has no acquisition time")
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError("missing timezone")
        return result.astimezone(UTC)
    except ValueError as exc:
        raise NISARResultError("NISAR record has invalid acquisition time") from exc


def _normalize(product: Any) -> Scene:
    try:
        feature = product.geojson()
        properties = feature["properties"]
        item_id = properties["fileID"]
        geometry = feature["geometry"]
        start = _time(properties["startTime"])
        end = _time(properties["stopTime"])
        url = properties["url"]
        if not isinstance(item_id, str) or not item_id.startswith("NISAR_"):
            raise ValueError("unexpected ID")
        if (
            properties.get("platform") != "NISAR"
            or properties.get("processingLevel") != "GCOV"
        ):
            raise ValueError("unexpected platform or product")
        if not isinstance(geometry, dict) or geometry.get("type") not in (
            "Polygon",
            "MultiPolygon",
        ):
            raise ValueError("invalid footprint")
        if start > end:
            raise ValueError("reversed acquisition interval")
        if not isinstance(url, str) or urlsplit(url).scheme != "https":
            raise ValueError("missing HTTPS product URL")
        channels = properties.get("mainBandPolarization") or []
        side_channels = properties.get("sideBandPolarization") or []
        if not isinstance(channels, list) or not isinstance(side_channels, list):
            raise TypeError("invalid polarizations")
        polarizations = tuple(dict.fromkeys([*channels, *side_channels]))
        if not set(polarizations) <= {"VV", "VH", "HH", "HV"}:
            raise ValueError("invalid polarizations")
        file_name = properties.get("fileName") or urlsplit(url).path.rsplit("/", 1)[-1]
        size_record = properties.get("bytes") or {}
        size = (
            size_record.get(file_name, {}).get("bytes")
            if isinstance(size_record, dict)
            else None
        )
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError("invalid size")
    except (KeyError, TypeError, ValueError) as exc:
        raise NISARResultError(f"invalid NISAR GCOV result: {exc}") from exc
    return Scene(
        id=f"nisar:{item_id}",
        provider="nisar",
        name=properties.get("sceneName") or item_id,
        start=start,
        end=end,
        geometry=geometry,
        platform="NISAR",
        product_type="GCOV_HDF5",
        polarizations=polarizations,
        beam_mode=properties.get("beamModeType"),
        flight_direction=properties.get("flightDirection"),
        size_bytes=size,
        download_url=url,
        source_metadata=dict(properties),
    )


class NISARAdapter:
    """Search NISAR GCOV scenes using ASF's supported dataset filter."""

    def __init__(
        self, search_pages: Callable[..., Iterable[Iterable[Any]]] | None = None
    ):
        self._search_pages = search_pages or asf_search.search_generator

    def search(self, query: SearchQuery) -> list[Scene]:
        options = {
            "dataset": asf_search.DATASET.NISAR,
            "processingLevel": asf_search.PRODUCT_TYPE.GCOV,
            "intersectsWith": _bbox_wkt(query.bbox),
            "start": _utc_string(query.start),
            "end": _utc_string(query.end),
            "maxResults": query.max_results,
        }
        scenes: list[Scene] = []
        seen: set[str] = set()
        for page in self._search_pages(**options):
            for product in page:
                scene = _normalize(product)
                if query.beam_mode and scene.beam_mode != query.beam_mode:
                    continue
                if query.polarizations and set(scene.polarizations) != set(
                    query.polarizations
                ):
                    continue
                if scene.id not in seen:
                    scenes.append(scene)
                    seen.add(scene.id)
                if len(scenes) >= query.max_results:
                    return scenes
        return scenes
