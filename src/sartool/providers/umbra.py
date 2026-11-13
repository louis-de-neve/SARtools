"""Discovery of public Umbra GEC scenes in a static STAC catalogue."""

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import quote, urljoin, urlsplit

import requests
from shapely.geometry import box, shape

from sartool.models import Scene, SearchQuery


class UmbraResultError(ValueError):
    """Umbra Open Data returned unusable metadata."""


class UmbraAdapter:
    """Search date-organized STAC items and resolve public S3 GEC assets."""

    HOSTS: ClassVar[set[str]] = {
        "s3.us-west-2.amazonaws.com",
        "umbra-open-data-catalog.s3.us-west-2.amazonaws.com",
    }
    ROOT = (
        "https://s3.us-west-2.amazonaws.com/umbra-open-data-catalog/stac/catalog.json"
    )
    BUCKET = "https://umbra-open-data-catalog.s3.us-west-2.amazonaws.com/"
    XML_NS: ClassVar[dict[str, str]] = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    @classmethod
    def _url(cls, base: str, href: object) -> str:
        if not isinstance(href, str) or not href:
            raise UmbraResultError("Umbra catalogue link has no URL")
        url = urljoin(base, href)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in cls.HOSTS:
            raise UmbraResultError("Umbra URL is outside the public catalogue")
        if (
            parsed.hostname == "s3.us-west-2.amazonaws.com"
            and not parsed.path.startswith("/umbra-open-data-catalog/")
        ):
            raise UmbraResultError("Umbra URL is outside the public bucket")
        return url

    @staticmethod
    def _time(value: object) -> datetime:
        if not isinstance(value, str):
            raise UmbraResultError("Umbra item has no acquisition time")
        try:
            result = datetime.fromisoformat(value)
            if result.tzinfo is None:
                raise ValueError("missing timezone")
            return result.astimezone(UTC)
        except ValueError as exc:
            raise UmbraResultError("Umbra item has invalid acquisition time") from exc

    def _links(self, url: str) -> list[dict]:
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        try:
            links = response.json()["links"]
            if not isinstance(links, list):
                raise TypeError("links is not a list")
        except (KeyError, TypeError, ValueError) as exc:
            raise UmbraResultError("Umbra returned an invalid catalogue") from exc
        return links

    def _children(self, url: str, pattern: str, first: str, last: str) -> list[str]:
        children = []
        for link in self._links(url):
            if not isinstance(link, dict) or link.get("rel") != "child":
                continue
            title = link.get("title")
            if (
                isinstance(title, str)
                and re.fullmatch(pattern, title)
                and first <= title <= last
            ):
                children.append(self._url(url, link.get("href")))
        return children

    def _gec_asset(self, task_id: object) -> tuple[str, int] | None:
        if not isinstance(task_id, str) or not self.UUID.fullmatch(task_id):
            raise UmbraResultError("Umbra item has no valid task ID")
        for base in ("sar-data/tasks/", "sar-data/task-data/"):
            prefix = f"{base}{task_id}/"
            response = self.session.get(
                self.BUCKET,
                params={"list-type": "2", "prefix": prefix, "max-keys": 1000},
                timeout=30,
            )
            response.raise_for_status()
            try:
                root = ET.fromstring(response.content)
                for entry in root.findall("s3:Contents", self.XML_NS):
                    key = entry.findtext("s3:Key", namespaces=self.XML_NS)
                    size = entry.findtext("s3:Size", namespaces=self.XML_NS)
                    if key and key.startswith(prefix) and key.endswith("_GEC.tif"):
                        return self.BUCKET + quote(key), int(size)
            except (ET.ParseError, TypeError, ValueError) as exc:
                raise UmbraResultError(
                    "Umbra public bucket listing is invalid"
                ) from exc
        return None

    def _item(self, item: dict, query: SearchQuery, area) -> Scene | None:
        try:
            properties = item["properties"]
            if properties.get("sar:product_type") != "GEC":
                return None
            start = self._time(
                properties.get("start_datetime") or properties.get("datetime")
            )
            end = self._time(
                properties.get("end_datetime") or properties.get("datetime")
            )
            if start > query.end or end < query.start:
                return None
            geometry = item["geometry"]
            if not shape(geometry).intersects(area):
                return None
            platform = properties["platform"]
            polarizations = tuple(properties["sar:polarizations"])
            mode = properties.get("sar:instrument_mode")
            if not isinstance(platform, str) or not platform.startswith("Umbra-"):
                raise ValueError("unexpected platform")
            if not polarizations or not set(polarizations) <= {"VV", "VH", "HH", "HV"}:
                raise ValueError("invalid polarizations")
            if not isinstance(mode, str) or not mode:
                raise ValueError("missing mode")
            if query.polarizations and set(polarizations) != set(query.polarizations):
                return None
            if query.beam_mode and mode.casefold() != query.beam_mode.casefold():
                return None
            item_id = item["id"]
            if not isinstance(item_id, str) or not item_id:
                raise ValueError("empty ID")
            asset = self._gec_asset(properties.get("umbra:task_id"))
            if asset is None:
                return None
            url, size = asset
        except (KeyError, TypeError, ValueError) as exc:
            raise UmbraResultError(f"invalid Umbra STAC item: {exc}") from exc
        return Scene(
            id=f"umbra:{item_id}",
            provider="umbra",
            name=item_id,
            start=start,
            end=end,
            geometry=geometry,
            platform=platform,
            product_type="GEC",
            polarizations=polarizations,
            beam_mode=mode,
            flight_direction=properties.get("sat:orbit_state", "").upper() or None,
            size_bytes=size,
            download_url=url,
            source_metadata=item,
        )

    def search(self, query: SearchQuery) -> list[Scene]:
        first = (query.start - timedelta(days=1)).date()
        last = (query.end + timedelta(days=1)).date()
        area = box(*query.bbox)
        scenes: list[Scene] = []
        seen: set[str] = set()
        for year_url in self._children(
            self.ROOT, r"\d{4}", str(first.year), str(last.year)
        ):
            for month_url in self._children(
                year_url,
                r"\d{4}-\d{2}",
                first.strftime("%Y-%m"),
                last.strftime("%Y-%m"),
            ):
                for day_url in self._children(
                    month_url,
                    r"\d{4}-\d{2}-\d{2}",
                    first.isoformat(),
                    last.isoformat(),
                ):
                    for link in self._links(day_url):
                        if not isinstance(link, dict) or link.get("rel") != "item":
                            continue
                        item_url = self._url(day_url, link.get("href"))
                        response = self.session.get(item_url, timeout=30)
                        response.raise_for_status()
                        scene = self._item(response.json(), query, area)
                        if scene and scene.id not in seen:
                            scenes.append(scene)
                            seen.add(scene.id)
                        if len(scenes) >= query.max_results:
                            return scenes
        return scenes
