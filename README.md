# SARtool

Research software for discovering, downloading, and exporting synthetic aperture radar data. The first planned product is Sentinel-1 GRD through ASF and Copernicus Data Space. API connections and export processing are planned, not implemented yet.

See [the implementation plan](IMPLEMENTATION_PLAN.md), [development foundation](DEVELOPMENT_FOUNDATION.md), and [Sentinel-1 API research](SENTINEL_API_RESEARCH.md).

## Development

Python 3.11 or newer is required. Run the current tests without installing dependencies:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
```

The tests currently cover provider-independent search input validation. The GitHub Actions workflow installs the package and runs the same suite on Python 3.11 and 3.13. Downloaded data and credentials must stay outside Git.
