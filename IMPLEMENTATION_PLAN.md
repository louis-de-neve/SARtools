# SARtool implementation plan

Based on `codex_config.txt` (reviewed 11 November 2026).

## Goal and initial scope

Build a reproducible tool that discovers open-access synthetic aperture radar (SAR) scenes across multiple providers, lets a researcher select scenes, downloads the selected assets, and writes both original products and documented derived formats. The command line interface (CLI) and graphical interface (GUI) must use the same search, selection, download, and export code.

**First supported dataset:** Sentinel-1 Ground Range Detected (GRD). **First providers:** Alaska Satellite Facility (ASF) and Copernicus Data Space Ecosystem (CDSE). This gives two independent catalogues for the same product family and a useful test of cross-provider normalization. Add other missions and product levels through provider adapters after the first workflow is reliable. Open access does not necessarily mean anonymous downloads: both providers have authentication workflows.

**First release outputs:** original downloaded product, NetCDF, and NumPy arrays plus metadata. Treat GeoTIFF and other formats as later exporters if needed. A NetCDF or array export must declare its processing level, units, coordinate reference system (CRS), grid, nodata mask, and processing steps; merely changing a file extension is not a scientific conversion.

## User workflow

1. Define area of interest (AOI), time range, provider and product filters, and output settings in a versioned YAML config file. The CLI can override common settings. The GUI can draw or import an AOI and adjust the time range with a slider.
2. **Discover:** query each enabled provider, paginate results, normalize metadata, and show the available scenes before any download. Show acquisition time, footprint, product type, mode, polarization, orbit direction, provider, approximate size where available, and authentication requirement. Keep the source record and URL for traceability.
3. **Select:** allow explicit scene selection in the GUI or from an exported discovery manifest in the CLI. A non-interactive CLI can use a documented selection rule such as `all`, provider, IDs, or a maximum count. Show estimated bytes and destination before execution.
4. **Download:** save into a user-defined root and folder template. Use a persisted manifest to record selected scene IDs, source, download URL, local path, status, size, checksum where supplied, and errors. Retry transient failures, resume or safely restart partial downloads, and skip verified existing files.
5. **Export:** apply a documented processing profile and write chosen output formats. Preserve source metadata and a provenance record alongside each derivative. Report per-scene success and failure without losing the rest of the batch.

## Architecture

| Component | Responsibility |
| --- | --- |
| Config and validation | Parse versioned YAML; validate dates, AOI, CRS, filters, paths, and output profiles. Never store credentials in the project config. |
| Geometry and time | Store AOI in WGS84 longitude/latitude for catalogue queries; transform to and from GUI display CRS; use UTC internally. Handle antimeridian crossings and invalid polygons. |
| Provider adapters | Implement `search(query)`, `resolve_download(scene)`, and `download(scene, destination, credentials)` for each provider. Keep provider-specific fields in namespaced metadata. |
| Common scene model | Stable provider-scoped ID, mission, product level, acquisition interval, footprint, available polarizations, orbit metadata, asset links, size, and provenance. |
| Discovery service | Run searches, paginate, collect partial provider errors, sort and filter, and identify matching acquisitions across providers without discarding either source. |
| Download manager | Authentication, rate limits, retries, temporary files, integrity checks, resume policy, and manifest updates. |
| Processing and exporters | Convert the agreed product level into a georeferenced data cube; write NetCDF and ML arrays through separate exporters. |
| Interfaces | CLI for scripts and repeatable jobs; GUI for map, projection and time controls, result review, selection, and progress. Both call the same application services. |

The proposed Python package layout is `src/sartool/{config,models,geometry,providers,discovery,downloads,processing,export,cli,gui}` with `tests/`, `examples/`, and `docs/`. Keep provider adapters and exporters separately testable.

## Proposed config contract

The schema should be finalized with examples before implementing provider integrations. An initial shape is:

```yaml
schema_version: 1
search:
  aoi: ./aoi.geojson             # GeoJSON geometry in WGS84
  start: 2025-01-01T00:00:00Z
  end: 2025-02-01T00:00:00Z
  providers: [asf, cdse]
  product: sentinel-1-grd
  polarizations: [VV, VH]
selection:
  mode: manual                   # or all / explicit_ids for unattended runs
output:
  root: ./data
  folder_template: "{provider}/{mission}/{year}/{scene_id}"
  formats: [original, netcdf, numpy]
  processing_profile: calibrated_geocoded_v1
  target_crs: EPSG:32630
  pixel_size_m: 10
```

Paths should resolve relative to the config file, unless explicitly absolute. The CLI should expose commands such as `sartool config validate`, `sartool search --config ... --out results.json`, and `sartool download --config ... --selection selected.json`. Define the exact command names and manifest schema in milestone 1.

## Delivery milestones and acceptance criteria

| Milestone | Work | Acceptance check |
| --- | --- | --- |
| 0. Development foundation | Initialize a local Git repository; establish package metadata and layout, a small real unit-test suite, contribution commands, `.gitignore`, and GitHub Actions CI. Decide remote repository owner/name/visibility before publishing. | Tests run locally and on a clean CI checkout; CI installs the package and runs the same test command on supported Python versions; no data or credentials enter Git. |
| 1. Specification and skeleton | Agree the first SAR product, output semantics, config and manifest schemas, dependency choices, example AOI, package layout, CLI entry point, test framework, lint and CI. | Example config validates; invalid geometry, dates, CRS, and paths give useful errors; CI runs checks on a clean checkout. |
| 2. Discovery via one provider | Implement ASF adapter, common scene model, pagination, metadata normalization, and CLI search output. | A known AOI and date range returns scene metadata and footprints; empty results and authentication/network errors are distinguishable. |
| 3. Multi-provider discovery and selection | Add CDSE adapter, duplicate-acquisition grouping, deterministic sorting, filters, result/selection manifests. | The same query can show results from both providers; selection can be saved and replayed without changing chosen IDs. |
| 4. Downloads and original products | Implement credentials, destination layout, progress, retry/resume behavior, integrity checks, and persistent manifest. | Selected scenes download to requested paths; rerun skips verified files and recovers an interrupted transfer. |
| 5. Scientific conversion and exports | Implement one explicit Sentinel-1 GRD processing profile, then NetCDF and NumPy exporters with masks, coordinates, units, and provenance. | Compare a small fixture against an independently processed reference; verify geolocation, pixel values/units, shape, and metadata. A fresh user can reproduce the output from the manifest. |
| 6. GUI | Build AOI draw/import, selectable map projections, temporal slider, result table/map, selection, destination settings, and transfer progress over the shared services. | A user can perform the same search → select → download → export journey as the CLI; a drawn AOI maps to the same geographic search in each display projection. |
| 7. Release and distribution | Documentation, example workflows, versioned release, and Docker image after the workflow is stable. | Clean-machine and container smoke tests run the example workflow; mounted inputs, outputs, credentials, and cache paths are documented. |

## Testing and CI

Milestone 0 is detailed in [`DEVELOPMENT_FOUNDATION.md`](DEVELOPMENT_FOUNDATION.md). The initial suite uses Python's standard `unittest` so it runs without third-party tooling; adopt extra linters and type checkers when dependencies and processing libraries are chosen. Keep this baseline passing before starting the first API adapter.

- Unit tests for config validation, geometry/CRS transformations, temporal boundaries, provider response normalization, deduplication, path safety, manifest transitions, and exporters.
- Contract tests using saved provider responses; a small number of live API smoke tests run separately because service availability and catalogue contents change.
- Integration tests with a tiny redistributable fixture for download interruption and processing/export correctness. Keep large SAR products out of Git.
- GitHub Actions on pull requests and the main branch: install, lint/format, type checks if adopted, unit/contract tests, and build. Run live API and full processing tests on a scheduled or manual workflow, with credentials in GitHub secrets.

## Decisions to settle before milestone 5

1. **Radiometry:** whether NetCDF/arrays contain original GRD digital numbers, calibrated sigma nought in linear units, sigma nought in dB, or more than one variable. Recommended starting profile: calibrated, geocoded sigma nought in linear units, with any dB representation clearly separate.
2. **Geometry:** target CRS, pixel size, AOI clipping, resampling, and whether all scenes must share one grid for ML. A single common grid is needed for directly stackable arrays.
3. **ML format:** full-scene `.npy` arrays versus fixed-size patches, channel order, missing-data mask, and train/validation split metadata. Start with full-scene arrays and a JSON sidecar; add patch generation once the target ML task is known.
4. **Processing engine:** evaluate a reproducible Sentinel-1 GRD calibration/geocoding route and its platform/container dependencies with a small benchmark before committing. Record engine name, version, parameters, and DEM source in provenance.
5. **Additional sources:** rank the next provider or mission by the research use case, authentication/access terms, metadata quality, and whether its product can share the chosen processing profile.

## Reference documentation checked

- [ASF search API and supported datasets](https://docs.asf.alaska.edu/api/keywords/)
- [ASF search/download package and authentication](https://docs.asf.alaska.edu/asf_search/downloading/)
- [CDSE STAC catalogue and Sentinel-1 collections](https://documentation.dataspace.copernicus.eu/APIs/STAC.html)
- [CDSE OData product download and authentication](https://documentation.dataspace.copernicus.eu/APIs/OData.html)
- [STAC Item Search specification](https://api.stacspec.org/v1.0.0/item-search/)
