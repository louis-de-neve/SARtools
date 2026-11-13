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

For Stripmap scenes, select **SM · Stripmap (S1–S6)** in the GUI or pass `--beam-mode SM` to the CLI. ASF records Sentinel-1 Stripmap under the individual S1–S6 beam names. The GUI's **Load known SM example** button fills a verified area and date near 94°E, 13°N. The equivalent CLI search is:

```bash
sartool search asf --bbox 93.3 12.1 94.8 13.9 \
  --start 2025-12-30T00:00:00Z --end 2025-12-31T23:59:00Z \
  --beam-mode SM --limit 20 --output sm-results.geojson
```

Sentinel-1 GRD catalogue links point to ZIP products. Those products contain TIFF measurement images; SARtool currently writes only a GeoJSON search manifest and does not create TIFF files.

## Local discovery GUI

Launch the browser interface after installing the package:

```bash
.venv/bin/sartool gui
```

It opens `http://127.0.0.1:8765/`. Enter WGS84 west/south/east/north bounds or click **Draw search area** and drag a rectangle on the map. The coordinate fields and orange map rectangle stay in sync. Enter a UTC time range, polarization, and result limit, then search to see ASF scene footprints and metadata. Selecting a result shows its ASF JPG browse preview in the bottom-right details panel when available. The background uses OpenStreetMap tiles and requires an internet connection, as does ASF search and the preview. Press Ctrl+C in the terminal to stop the server. Use `--no-browser` if you want to open the address yourself, or `--port 8766` to choose another port.

The same search can use the validated YAML example:

```bash
sartool config validate --config examples/sentinel1-grd.yaml
sartool search asf --config examples/sentinel1-grd.yaml --output results.geojson
```
