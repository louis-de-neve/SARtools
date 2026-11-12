# SARtool v1 development specification

## First product and workflow

The first supported product is **Sentinel-1 Ground Range Detected (GRD)**. ASF is the first discovery provider; Copernicus Data Space is the next provider. A user validates a config, searches for available scenes, reviews a GeoJSON discovery manifest, selects scenes, and later downloads and exports them. Search and selection precede transfers. The CLI and future GUI use the same provider-neutral model.

## Version 1 config

See [`examples/sentinel1-grd.yaml`](../examples/sentinel1-grd.yaml) and its AOI file. `load_config(path)` validates and returns typed data. Paths in the YAML are relative to the YAML file unless absolute; timestamps are normalized to UTC.

| Field | Meaning |
| --- | --- |
| `schema_version` | Required integer `1`. |
| `search.aoi` | GeoJSON Polygon or MultiPolygon (or a Feature containing one), in WGS84 longitude/latitude. The first bbox search rejects antimeridian crossings and AOIs over 180° wide. |
| `search.start`, `search.end` | ISO 8601 instants with timezones; start must precede end. |
| `search.providers` | Nonempty list from `asf`, `cdse`. Only ASF is implemented so far. |
| `search.product` | `sentinel-1-grd` in this release. |
| `search.polarizations` | Optional list of `VV`, `VH`, `HH`, `HV`; defaults to `VV`, `VH`. ASF treats this as an exact channel combination: `[VV, VH]` is sent as `VV+VH`. Unsupported combinations are rejected. See [ASF polarization values](https://docs.asf.alaska.edu/api/keywords/). |
| `search.max_results` | Positive integer; defaults to `100`. |
| `selection.mode` | `manual`, `all`, or `explicit_ids`; the last mode requires `selection.ids`. Download selection is a later milestone. |
| `output.root` | Destination directory. An existing file is rejected. |
| `output.folder_template` | Relative template with `{provider}`, `{mission}`, `{year}`, `{scene_id}` only. Use `/` separators; parent traversal and backslashes are rejected on every platform. |
| `output.formats` | Nonempty list of `original`, `netcdf`, `numpy`. Only discovery is currently implemented. |
| `output.processing_profile`, `target_crs`, `pixel_size_m` | Required for NetCDF/NumPy output declarations. CRS must be a recognized projected metre-based EPSG code. The processing profile itself is defined in milestone 5. |

Credentials are never stored in YAML or discovery manifests. Unknown keys are rejected so spelling mistakes cannot silently change a search. Invalid input raises `ConfigError` naming the affected field.

## Discovery manifest

The CLI writes a GeoJSON `FeatureCollection` with the normalized `query` and one `Feature` per provider scene. Each feature has a provider-scoped `id`, the source footprint in `geometry`, and properties: `provider`, `name`, `start`, `end`, `platform`, `product_type`, `polarizations`, `beam_mode`, `flight_direction`, `size_bytes`, `download_url`, and `source_metadata`. Times use UTC ISO 8601. Size and some SAR metadata may be absent; no values are invented. Results should be sorted deterministically before they become a selection manifest in milestone 3.

## Output semantics and open science decisions

- `original` means the unmodified provider product, with a manifest recording source URL and integrity information if available.
- `netcdf` will contain calibrated, geocoded data variables with explicit units, CRS, grid coordinates, masks, and provenance. The precise radiometric variable and processing engine remain to be chosen and validated in milestone 5.
- `numpy` will initially be full-scene arrays with a JSON metadata sidecar containing dimensions, channel order, grid, mask, units, and provenance. Patch generation awaits the ML task definition.

The target grid, resampling, radiometric convention, calibration engine and DEM are **not yet fixed**. A configuration that declares derived formats can be validated now, but export commands will not run until milestone 5.

## Package layout and tests

`src/sartool/` contains provider-neutral `models.py`, `config.py`, `geometry.py`, `providers/`, and the CLI. Future `discovery.py`, `downloads.py`, `processing.py`, `export/`, and `gui/` modules follow the implementation plan. `tests/` contains standard-library `unittest` tests and small saved provider responses; `examples/` contains the reference config and AOI. GitHub Actions installs the package, compiles source/tests, and runs the unit suite on Python 3.11 and 3.13. Live API smoke tests run separately so routine CI stays deterministic.
