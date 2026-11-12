"""Provider-independent search inputs shared by future API adapters."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SearchQuery:
    """A WGS84 bounding box and timezone-aware acquisition interval."""

    bbox: tuple[float, float, float, float]
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if len(self.bbox) != 4:
            raise ValueError("bbox must contain west, south, east, north")
        west, south, east, north = self.bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox must be valid WGS84 bounds without antimeridian crossing")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end must include a timezone")
        if self.start >= self.end:
            raise ValueError("start must be earlier than end")
        object.__setattr__(self, "start", self.start.astimezone(timezone.utc))
        object.__setattr__(self, "end", self.end.astimezone(timezone.utc))
