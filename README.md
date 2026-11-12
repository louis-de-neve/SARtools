# SARtool

Research software for discovering, downloading, and exporting synthetic aperture radar data. The first planned product is Sentinel-1 GRD through ASF and Copernicus Data Space. API connections and export processing are planned, not implemented yet.

See [the implementation plan](IMPLEMENTATION_PLAN.md), [development foundation](DEVELOPMENT_FOUNDATION.md), and [Sentinel-1 API research](SENTINEL_API_RESEARCH.md).

## Development

Python 3.11 or newer is required. Install the package and development tools in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

The tests cover config validation, provider-independent search input, ASF response normalization, and CLI manifests. The GitHub Actions workflow installs the package and runs the same checks on Python 3.11 and 3.13. Downloaded data and credentials must stay outside Git.

## ASF discovery

Search a WGS84 bounding box and UTC interval:

```bash
python -m pip install -e .
sartool search asf --bbox -0.5 51.3 0.3 51.7 \
  --start 2025-01-01T00:00:00Z --end 2025-01-08T00:00:00Z \
  --limit 10 --output results.geojson
```

The command writes a GeoJSON discovery manifest containing normalized fields and the original ASF metadata. It searches Sentinel-1 GRD only. Downloading is a later milestone.

The same search can use the validated YAML example:

```bash
sartool config validate --config examples/sentinel1-grd.yaml
sartool search asf --config examples/sentinel1-grd.yaml --output results.geojson
```
