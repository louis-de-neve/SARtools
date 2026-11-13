"""Discovery of detected imagery in Capella's public Open Data STAC catalog."""

import re
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import urljoin, urlsplit

import requests
from shapely.geometry import box, shape

from sartool.models import Scene, SearchQuery


class CapellaResultError(ValueError):
    """Capella Open Data returned unusable catalogue metadata."""


class CapellaAdapter:
    """Follow the public catalogue's year/month/day hierarchy."""

    HOSTS: ClassVar[set[str]] = {
        "capella-open-data.s3.us-west-2.amazonaws.com",
        "capella-open-data.s3.amazonaws.com",
    }
    INDEX = (
        "https://capella-open-data.s3.us-west-2.amazonaws.com/stac/"
        "capella-open-data-by-datetime/catalog.json"
    )
    DATE_LINK: ClassVar[dict[str, re.Pattern[str]]] = {
        "year": re.compile(r"^Capella Open Data (\d{4})$"),
        "month": re.compile(r"^Capella Open Data (\d{4})-(\d{2})$"),
        "day": re.compile(r"^Capella Open Data (\d{4})-(\d{2})-(\d{2})$"),
    }

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    @classmethod
    def _url(cls, base: str, href: object) -> str:
        if not isinstance(href, str):
            raise CapellaResultError("Capella catalogue link has no URL")
        url = urljoin(base, href)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in cls.HOSTS:
            raise CapellaResultError("Capella URL is outside the public catalogue")
        return url

    @staticmethod
    def _time(value: object) -> datetime:
        if not isinstance(value, str):
            raise CapellaResultError("Capella item has no acquisition time")
        try:
            result = datetime.fromisoformat(value)
            if result.tzinfo is None:
                raise ValueError("missing timezone")
            return result.astimezone(UTC)
        except ValueError as exc:
            raise CapellaResultError(
                "Capella item has invalid acquisition time"
            ) from exc

    def _catalog(self, url: str) -> list[dict]:
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        try:
            links = response.json()["links"]
            if not isinstance(links, list):
                raise TypeError("links is not a list")
        except (KeyError, TypeError, ValueError) as exc:
            raise CapellaResultError("Capella returned an invalid catalogue") from exc
        return links

    def _children(self, url: str, level: str, first, last) -> list[str]:
        children = []
        for link in self._catalog(url):
            if not isinstance(link, dict) or link.get("rel") != "child":
                continue
            title = link.get("title")
            match = (
                self.DATE_LINK[level].fullmatch(title)
                if isinstance(title, str)
                else None
            )
            if match is None:
                continue
            parts = tuple(map(int, match.groups()))
            value = (
                parts[0]
                if level == "year"
                else parts[:2]
                if level == "month"
                else parts
            )
            if first <= value <= last:
                children.append(self._url(url, link.get("href")))
        return children

    def _item(self, item: dict) -> Scene:
        try:
            properties = item["properties"]
            assets = item["assets"]
            item_id = item["id"]
            geometry = item["geometry"]
            product = properties["sar:product_type"]
            if product not in ("GEO", "GEC"):
                raise ValueError("unsupported product type")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError("empty ID")
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
            platform = properties["platform"]
            if not isinstance(platform, str) or not platform.startswith("capella-"):
                raise ValueError("unexpected platform")
            polarizations = tuple(properties["sar:polarizations"])
            if not polarizations or not set(polarizations) <= {"VV", "VH", "HH", "HV"}:
                raise ValueError("invalid polarizations")
            mode = properties.get("sar:instrument_mode")
            if mode is not None and not isinstance(mode, str):
                raise ValueError("invalid acquisition mode")
            asset = next(
                asset
                for asset in assets.values()
                if isinstance(asset, dict) and "data" in asset.get("roles", [])
            )
            download_url = self._url(self.INDEX, asset["href"])
            size = asset.get("file:size")
            if size is not None and (type(size) is not int or size < 0):
                raise ValueError("invalid size")
        except (KeyError, StopIteration, TypeError, ValueError) as exc:
            raise CapellaResultError(f"invalid Capella STAC item: {exc}") from exc
        return Scene(
            id=f"capella:{item_id}",
            provider="capella",
            name=item_id,
            start=start,
            end=end,
            geometry=geometry,
            platform=f"Capella-{platform.removeprefix('capella-')}",
            product_type=f"{product}_COG",
            polarizations=polarizations,
            beam_mode=mode,
            flight_direction=properties.get("sat:orbit_state", "").upper() or None,
            size_bytes=size,
            download_url=download_url,
            source_metadata=item,
        )

    def search(self, query: SearchQuery) -> list[Scene]:
        # Include adjacent dates for acquisitions crossing midnight UTC.
        first = (query.start - timedelta(days=1)).date()
        last = (query.end + timedelta(days=1)).date()
        area = box(*query.bbox)
        scenes: list[Scene] = []
        seen: set[str] = set()
        years = self._children(self.INDEX, "year", first.year, last.year)
        for year_url in years:
            months = self._children(
                year_url, "month", (first.year, first.month), (last.year, last.month)
            )
            for month_url in months:
                days = self._children(
                    month_url,
                    "day",
                    (first.year, first.month, first.day),
                    (last.year, last.month, last.day),
                )
                for day_url in days:
                    for link in self._catalog(day_url):
                        if not isinstance(link, dict) or link.get("rel") != "item":
                            continue
                        href = link.get("href")
                        if not isinstance(href, str) or not re.search(
                            r"_(GEO|GEC)_", href
                        ):
                            continue
                        item_url = self._url(day_url, href)
                        response = self.session.get(item_url, timeout=30)
                        response.raise_for_status()
                        scene = self._item(response.json())
                        if scene.start > query.end or scene.end < query.start:
                            continue
                        if not shape(scene.geometry).intersects(area):
                            continue
                        if query.beam_mode and (
                            not scene.beam_mode
                            or scene.beam_mode.casefold() != query.beam_mode.casefold()
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
                            return scenes
        return scenes
