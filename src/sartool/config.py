"""Versioned YAML configuration for SARtool searches and future exports."""

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path, PureWindowsPath
from string import Formatter
from typing import Any

import yaml
from pyproj import CRS
from pyproj.exceptions import CRSError

from sartool.geometry import GeometryError, load_aoi
from sartool.models import SearchQuery


class ConfigError(ValueError):
    """The configuration cannot be used by SARtool."""


@dataclass(frozen=True)
class SearchConfig:
    aoi_path: Path
    aoi_geometry: dict[str, Any]
    bbox: tuple[float, float, float, float]
    start: datetime
    end: datetime
    providers: tuple[str, ...]
    product: str
    polarizations: tuple[str, ...]
    max_results: int


@dataclass(frozen=True)
class SelectionConfig:
    mode: str
    ids: tuple[str, ...]


@dataclass(frozen=True)
class OutputConfig:
    root: Path
    folder_template: str
    formats: tuple[str, ...]
    processing_profile: str | None
    target_crs: str | None
    pixel_size_m: float | None


@dataclass(frozen=True)
class ToolConfig:
    path: Path
    schema_version: int
    search: SearchConfig
    selection: SelectionConfig
    output: OutputConfig

    def search_query(self) -> SearchQuery:
        """Build the provider-neutral query used by the current ASF adapter."""
        return SearchQuery(
            self.search.bbox,
            self.search.start,
            self.search.end,
            self.search.max_results,
        )


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{field} must be a mapping")
    return value


def _known_keys(data: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        names = ", ".join(sorted(str(key) for key in unknown))
        raise ConfigError(f"{field} has unknown key(s): {names}")


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a nonempty string")
    return value.strip()


def _sequence(
    value: Any, field: str, allowed: set[str] | None = None
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{field} must be a nonempty list")
    items = tuple(_nonempty_string(item, field) for item in value)
    if len(set(items)) != len(items):
        raise ConfigError(f"{field} must not contain duplicates")
    if allowed is not None and not set(items) <= allowed:
        raise ConfigError(
            f"{field} contains unsupported values: {', '.join(sorted(set(items) - allowed))}"
        )
    return items


def _time(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ConfigError(
                f"{field} must be an ISO 8601 date-time with timezone"
            ) from exc
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ConfigError(f"{field} must be an ISO 8601 date-time with timezone")
    return value.astimezone(UTC)


def _path(value: Any, field: str, base: Path) -> Path:
    raw = Path(_nonempty_string(value, field)).expanduser()
    return (raw if raw.is_absolute() else base / raw).resolve()


def _folder_template(value: Any) -> str:
    template = _nonempty_string(value, "output.folder_template")
    if (
        "\\" in template
        or Path(template).is_absolute()
        or PureWindowsPath(template).drive
        or ".." in Path(template).parts
    ):
        raise ConfigError(
            "output.folder_template must be a relative path using '/' without '..' or backslashes"
        )
    allowed_fields = {"provider", "mission", "year", "scene_id"}
    try:
        for _literal, field, spec, conversion in Formatter().parse(template):
            if field is not None and (
                field not in allowed_fields or spec or conversion
            ):
                raise ConfigError(
                    f"output.folder_template has unsupported field: {field}"
                )
    except ValueError as exc:
        raise ConfigError("output.folder_template has invalid braces") from exc
    return template


def _crs(value: Any) -> str:
    identifier = _nonempty_string(value, "output.target_crs")
    if not identifier.upper().startswith("EPSG:") or not identifier[5:].isdigit():
        raise ConfigError("output.target_crs must be an EPSG code such as EPSG:32630")
    try:
        crs = CRS.from_user_input(identifier)
    except CRSError as exc:
        raise ConfigError(
            f"output.target_crs is not a recognized CRS: {identifier}"
        ) from exc
    if not crs.is_projected or not all(
        axis.unit_conversion_factor == 1 for axis in crs.axis_info
    ):
        raise ConfigError("output.target_crs must be a projected CRS with metre units")
    return identifier.upper()


def load_config(path: str | Path) -> ToolConfig:
    """Parse, validate, and normalize a SARtool YAML config file."""
    config_path = Path(path).expanduser().resolve()
    try:
        source = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file does not exist: {config_path}") from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"config file cannot be read: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"config file contains invalid YAML: {exc}") from exc
    data = _mapping(source, "config")
    _known_keys(data, {"schema_version", "search", "selection", "output"}, "config")
    if data.get("schema_version") != 1 or isinstance(data.get("schema_version"), bool):
        raise ConfigError("schema_version must be 1")
    search = _mapping(data.get("search"), "search")
    selection = _mapping(data.get("selection"), "selection")
    output = _mapping(data.get("output"), "output")
    _known_keys(
        search,
        {"aoi", "start", "end", "providers", "product", "polarizations", "max_results"},
        "search",
    )
    _known_keys(selection, {"mode", "ids"}, "selection")
    _known_keys(
        output,
        {
            "root",
            "folder_template",
            "formats",
            "processing_profile",
            "target_crs",
            "pixel_size_m",
        },
        "output",
    )
    base = config_path.parent

    aoi_path = _path(search.get("aoi"), "search.aoi", base)
    try:
        aoi_geometry, bbox = load_aoi(aoi_path)
    except GeometryError as exc:
        raise ConfigError(str(exc)) from exc
    start = _time(search.get("start"), "search.start")
    end = _time(search.get("end"), "search.end")
    if start >= end:
        raise ConfigError("search.start must be earlier than search.end")
    providers = _sequence(search.get("providers"), "search.providers", {"asf", "cdse"})
    product = _nonempty_string(search.get("product"), "search.product")
    if product != "sentinel-1-grd":
        raise ConfigError("search.product currently supports only sentinel-1-grd")
    polarizations = _sequence(
        search.get("polarizations", ["VV", "VH"]),
        "search.polarizations",
        {"VV", "VH", "HH", "HV"},
    )
    max_results = search.get("max_results", 100)
    if (
        isinstance(max_results, bool)
        or not isinstance(max_results, int)
        or max_results < 1
    ):
        raise ConfigError("search.max_results must be a positive integer")

    mode = _nonempty_string(selection.get("mode"), "selection.mode")
    if mode not in {"manual", "all", "explicit_ids"}:
        raise ConfigError("selection.mode must be manual, all, or explicit_ids")
    ids = ()
    if mode == "explicit_ids":
        ids = _sequence(selection.get("ids"), "selection.ids")
    elif "ids" in selection:
        raise ConfigError("selection.ids is allowed only when mode is explicit_ids")

    root = _path(output.get("root"), "output.root", base)
    if root.exists() and not root.is_dir():
        raise ConfigError(f"output.root is an existing file: {root}")
    folder_template = _folder_template(output.get("folder_template"))
    formats = _sequence(
        output.get("formats"), "output.formats", {"original", "netcdf", "numpy"}
    )
    derived = bool(set(formats) & {"netcdf", "numpy"})
    profile = output.get("processing_profile")
    if profile is not None:
        profile = _nonempty_string(profile, "output.processing_profile")
    target_crs = (
        _crs(output.get("target_crs")) if output.get("target_crs") is not None else None
    )
    pixel_size = output.get("pixel_size_m")
    if pixel_size is not None:
        if (
            isinstance(pixel_size, bool)
            or not isinstance(pixel_size, (int, float))
            or not isfinite(pixel_size)
            or pixel_size <= 0
        ):
            raise ConfigError("output.pixel_size_m must be a positive number")
        pixel_size = float(pixel_size)
    if derived and (profile is None or target_crs is None or pixel_size is None):
        raise ConfigError(
            "netcdf/numpy output requires processing_profile, target_crs, and pixel_size_m"
        )

    return ToolConfig(
        path=config_path,
        schema_version=1,
        search=SearchConfig(
            aoi_path,
            aoi_geometry,
            bbox,
            start,
            end,
            providers,
            product,
            polarizations,
            max_results,
        ),
        selection=SelectionConfig(mode, ids),
        output=OutputConfig(
            root, folder_template, formats, profile, target_crs, pixel_size
        ),
    )
