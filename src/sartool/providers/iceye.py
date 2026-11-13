"""Discovery of publicly downloadable ICEYE Open Data GRD scenes."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import requests
from shapely.geometry import box, shape

from sartool.models import Scene, SearchQuery


class ICEYEResultError(ValueError):
    """The public ICEYE catalogue returned unusable metadata."""


class ICEYEAdapter:
    """Search the public footprint index, then read matching STAC items."""

    HOST = "iceye-open-data-catalog.s3.amazonaws.com"
    INDEX = f"https://{HOST}/stac-items/summary/footprint-summary-points.geojson"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    @classmethod
    def _url(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ICEYEResultError("ICEYE item has no public HTTPS URL")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname != cls.HOST:
            raise ICEYEResultError("ICEYE item URL is outside the public catalogue")
        return value

    @staticmethod
    def _time(value: object) -> datetime:
        if not isinstance(value, str):
            raise ICEYEResultError("ICEYE item has no acquisition time")
        try:
            result = datetime.fromisoformat(value)
            if result.tzinfo is None:
                raise ValueError("missing timezone")
            return result.astimezone(UTC)
        except ValueError as exc:
            raise ICEYEResultError("ICEYE item has invalid acquisition time") from exc

    def _item(self, item: dict) -> Scene:
        try:
            properties = item["properties"]
            assets = item["assets"]
            item_id = item["id"]
            geometry = item["geometry"]
            if not isinstance(item_id, str) or not item_id:
                raise ValueError("empty ID")
            if not isinstance(properties["platform"], str) or not properties[
                "platform"
            ].upper().startswith("ICEYE"):
                raise ValueError("unexpected platform")
            if shape(geometry).is_empty:
                raise ValueError("empty footprint")
            start = self._time(
                properties.get("start_datetime") or properties.get("datetime")
            )
            end = self._time(
                properties.get("end_datetime") or properties.get("datetime")
            )
            if start > end:
                raise ValueError("reversed acquisition interval")
            asset = assets["grd-cog"]
            url = self._url(asset["href"])
            size = asset.get("file:size")
            if size is not None and (type(size) is not int or size < 0):
                raise ValueError("invalid size")
            polarizations = tuple(properties.get("sar:polarizations", []))
            if not polarizations or not set(polarizations) <= {"VV", "VH", "HH", "HV"}:
                raise ValueError("invalid polarizations")
            mode = properties.get("sar:instrument_mode")
            if not isinstance(mode, str) or not mode:
                raise ValueError("missing acquisition mode")
        except (KeyError, TypeError, ValueError) as exc:
            raise ICEYEResultError(f"invalid ICEYE STAC item: {exc}") from exc
        return Scene(
            id=f"iceye:{item_id}",
            provider="iceye",
            name=item_id,
            start=start,
            end=end,
            geometry=geometry,
            platform=properties["platform"],
            product_type="GRD_COG",
            polarizations=polarizations,
            beam_mode=mode,
            flight_direction=properties.get("sat:orbit_state", "").upper() or None,
            size_bytes=size,
            download_url=url,
            source_metadata=item,
        )

    def search(self, query: SearchQuery) -> list[Scene]:
        response = self.session.get(self.INDEX, timeout=30)
        response.raise_for_status()
        try:
            features = response.json()["features"]
            if not isinstance(features, list):
                raise TypeError("features is not a list")
        except (KeyError, TypeError, ValueError) as exc:
            raise ICEYEResultError("ICEYE footprint index is invalid") from exc
        area = box(*query.bbox)
        scenes: list[Scene] = []
        seen: set[str] = set()
        for feature in features:
            try:
                props = feature["properties"]
                # The public index also contains undated pair summaries.
                # They are not individual satellite scenes.
                if not props.get("datetime") or not props.get("platform"):
                    continue
                acquired = self._time(props["datetime"])
                # The index holds one representative time; confirm the full
                # acquisition interval from the item for boundary matches.
                if (
                    not query.start - timedelta(days=1)
                    <= acquired
                    <= query.end + timedelta(days=1)
                ):
                    continue
                if not shape(feature["geometry"]).intersects(area):
                    continue
                href = self._url(props["href"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ICEYEResultError(f"invalid ICEYE footprint: {exc}") from exc
            item_response = self.session.get(href, timeout=30)
            item_response.raise_for_status()
            try:
                item = item_response.json()
                if "grd-cog" not in item["assets"]:
                    continue
                scene = self._item(item)
            except (TypeError, ValueError) as exc:
                raise ICEYEResultError(f"invalid ICEYE item response: {exc}") from exc
            if scene.start > query.end or scene.end < query.start:
                continue
            if not shape(scene.geometry).intersects(area):
                continue
            if (
                query.beam_mode
                and scene.beam_mode.casefold() != query.beam_mode.casefold()
            ):
                continue
            if query.polarizations and set(scene.polarizations) != set(
                query.polarizations
            ):
                continue
            if scene.id not in seen:
                scenes.append(scene)
                seen.add(scene.id)
            if len(scenes) >= query.max_results:
                break
        return scenes
