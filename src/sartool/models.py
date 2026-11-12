"""Provider-independent search inputs shared by future API adapters."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class SearchQuery:
    """A WGS84 bounding box and timezone-aware acquisition interval."""

    bbox: tuple[float, float, float, float]
    start: datetime
    end: datetime
    max_results: int = 100

    def __post_init__(self) -> None:
        if len(self.bbox) != 4:
            raise ValueError("bbox must contain west, south, east, north")
        west, south, east, north = self.bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError(
                "bbox must be valid WGS84 bounds without antimeridian crossing"
            )
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end must include a timezone")
        if self.start >= self.end:
            raise ValueError("start must be earlier than end")
        if self.max_results < 1:
            raise ValueError("max_results must be at least 1")
        object.__setattr__(self, "start", self.start.astimezone(UTC))
        object.__setattr__(self, "end", self.end.astimezone(UTC))


@dataclass(frozen=True)
class Scene:
    """Normalized catalogue record with its original provider metadata."""

    id: str
    provider: str
    name: str
    start: datetime
    end: datetime
    geometry: dict[str, Any]
    platform: str
    product_type: str
    polarizations: tuple[str, ...]
    beam_mode: str | None
    flight_direction: str | None
    size_bytes: int | None
    download_url: str
    source_metadata: dict[str, Any]

    def to_feature(self) -> dict[str, Any]:
        """Return a GeoJSON feature suitable for a discovery manifest."""
        return {
            "type": "Feature",
            "id": self.id,
            "geometry": self.geometry,
            "properties": {
                "provider": self.provider,
                "name": self.name,
                "start": self.start.isoformat().replace("+00:00", "Z"),
                "end": self.end.isoformat().replace("+00:00", "Z"),
                "platform": self.platform,
                "product_type": self.product_type,
                "polarizations": list(self.polarizations),
                "beam_mode": self.beam_mode,
                "flight_direction": self.flight_direction,
                "size_bytes": self.size_bytes,
                "download_url": self.download_url,
                "source_metadata": self.source_metadata,
            },
        }
