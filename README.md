# SARtool

Research software for discovering, downloading, and exporting synthetic aperture radar data. Discovery currently covers Sentinel-1 GRD through ASF, ICEYE GRD, Capella GEO/GEC, Umbra GEC, and NISAR GCOV. The GUI searches all five satellite sources together. Downloads and export processing are planned.

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

The tests cover config validation, provider-independent search input, catalogue normalization, and CLI manifests. The GitHub Actions workflow installs the package and runs the same checks on Python 3.11 and 3.13. Downloaded data and credentials must stay outside Git.

## ASF discovery

Search a WGS84 bounding box and UTC interval:

```bash
python -m pip install -e .
sartool search asf --bbox -0.5 51.3 0.3 51.7 \
  --start 2025-01-01T00:00:00Z --end 2025-01-08T00:00:00Z \
  --limit 10 --output results.geojson
```

The command writes a GeoJSON discovery manifest containing normalized fields and the original ASF metadata. It searches Sentinel-1 GRD only. Downloading is a later milestone.

For Stripmap scenes, select **SM** under **Sentinel-1 mode** in the GUI or pass `--beam-mode SM` to the CLI. ASF records Sentinel-1 Stripmap under the individual S1–S6 beam names. The GUI's **Load known Sentinel-1 SM area** button fills a verified area and date near 94°E, 13°N; the combined GUI search still queries the other satellite sources. The equivalent CLI search is:

```bash
sartool search asf --bbox 93.3 12.1 94.8 13.9 \
  --start 2025-12-30T00:00:00Z --end 2025-12-31T23:59:00Z \
  --beam-mode SM --limit 20 --output sm-results.geojson
```

ASF Sentinel-1 catalogue links point to ZIP products. Those products contain TIFF measurement images; SARtool currently writes only a GeoJSON search manifest and does not create TIFF files.

## ICEYE Open Data

Use **Load known ICEYE example** in the GUI to search all satellite sources near Tunis on 20 December 2023. The ICEYE-only CLI equivalent is:

```bash
sartool search iceye --bbox 10.0 36.7 10.3 37.0 \
  --start 2023-12-20T00:00:00Z --end 2023-12-21T00:00:00Z \
  --beam-mode spotlight --limit 10 --output iceye-results.geojson
```

You can also use `sartool search iceye --config examples/iceye-grd.yaml`. ICEYE Open Data is a curated public subset, with anonymous HTTPS links to GRD COGs and preview PNGs. ICEYE's wider [ICAS catalogue API](https://docs.iceye.com/constellation/api/catalog/search-catalog-items/) requires a bearer token; this adapter does not access that commercial archive. The public subset is documented by [ICEYE](https://sar.iceye.com/6.0.5/opendata/opendata/).

## Capella Open Data

Use **Load known Capella example** in the GUI to search all sources near Los Angeles on 1 January 2025. The Capella-only CLI equivalent is:

```bash
sartool search capella --bbox -118.2 34.7 -118.0 34.9 \
  --start 2025-01-01T00:00:00Z --end 2025-01-02T00:00:00Z \
  --limit 10 --output capella-results.geojson
```

You can also use `sartool search capella --config examples/capella-detected.yaml`. The adapter follows Capella's public date-organized STAC catalogue and returns detected GEO/GEC GeoTIFF assets plus PNG thumbnails. It excludes complex SLC products for now. This is Capella's [open dataset](https://support.capellaspace.com/how-do-i-access-capellas-open-data/), not the full commercial archive.

## Umbra Open Data

Use **Load known Umbra example** in the GUI to search near Lord Howe Island on 22 June 2025. The CLI example is:

```bash
sartool search umbra --config examples/umbra-gec.yaml --output umbra-results.geojson
```

The adapter follows Umbra's public date-organized STAC catalogue and resolves GEC GeoTIFF assets through the public S3 bucket. The catalogue's asset links can be empty, so the adapter confirms each GEC file in the bucket before returning it. Umbra's [Open Data Program](https://umbra.space/open-data/) requires no sign-up.

## NISAR GCOV

Use **Load known NISAR example** in the GUI to search a June 2026 Caribbean acquisition. The CLI example is:

```bash
sartool search nisar --config examples/nisar-gcov.yaml --output nisar-results.geojson
```

NISAR GCOV discovery uses [ASF's `asf_search` dataset filter](https://nisar-docs.asf.alaska.edu/asf-search/). Results link to HDF5 products and include PNG browse images. NISAR data is free, but downloading requires a NASA Earthdata Login; [GCOV](https://nisar-docs.asf.alaska.edu/gcov/) is calibrated, terrain-corrected backscatter rather than a GeoTIFF scene.

## Local discovery GUI

Launch the browser interface after installing the package:

```bash
.venv/bin/sartool gui
```

It opens `http://127.0.0.1:8765/`. Enter WGS84 west/south/east/north bounds or click **Draw search area** and drag a rectangle on the map. The coordinate fields and orange map rectangle stay in sync. Enter a UTC time range, polarization, and per-source result limit, then select **Search all satellites**. The map and result list combine all five sources, with counts and any source failures shown separately. Selecting a result shows its browse preview when available; Umbra's public STAC items do not currently supply browser-ready preview images. The background uses OpenStreetMap tiles and requires an internet connection, as do the catalogue searches and previews. Press Ctrl+C in the terminal to stop the server. Use `--no-browser` if you want to open the address yourself, or `--port 8766` to choose another port.

The same search can use the validated YAML example:

```bash
sartool config validate --config examples/sentinel1-grd.yaml
sartool search asf --config examples/sentinel1-grd.yaml --output results.geojson
```
