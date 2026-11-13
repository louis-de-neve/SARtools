"""Command line entry point for SARtool discovery."""

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime

import asf_search
import requests

from sartool.config import ConfigError, load_config
from sartool.config_cli import validate
from sartool.models import SearchQuery
from sartool.providers import PRODUCTS, PROVIDERS, make_adapter
from sartool.providers.asf import ASFAdapter, ASFQueryError, ASFResultError
from sartool.providers.capella import CapellaResultError
from sartool.providers.iceye import ICEYEResultError
from sartool.providers.nisar import NISARResultError
from sartool.providers.umbra import UmbraResultError


def _date_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO 8601 time: {value}") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("time must include a timezone")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sartool")
    commands = parser.add_subparsers(dest="command", required=True)
    gui_parser = commands.add_parser("gui", help="open the local discovery GUI")
    gui_parser.add_argument("--port", type=int, default=8765)
    gui_parser.add_argument("--no-browser", action="store_true")
    config_parser = commands.add_parser("config", help="manage tool configuration")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    validate_parser = config_commands.add_parser(
        "validate", help="validate a YAML config file"
    )
    validate_parser.add_argument("--config", required=True)
    search_parser = commands.add_parser("search", help="discover SAR scenes")
    search_parser.add_argument("provider", choices=PROVIDERS)
    search_parser.add_argument("--config", help="validated YAML search configuration")
    search_parser.add_argument(
        "--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH")
    )
    search_parser.add_argument("--start", type=_date_time)
    search_parser.add_argument("--end", type=_date_time)
    search_parser.add_argument("--limit", type=int)
    search_parser.add_argument("--beam-mode", help="mission-specific acquisition mode")
    search_parser.add_argument(
        "--output", help="write the GeoJSON discovery manifest to this path"
    )
    args = parser.parse_args(argv)

    if args.command == "gui":
        from sartool.web import serve

        if not 0 <= args.port <= 65535:
            parser.error("--port must be between 0 and 65535")
        return serve(args.port, open_browser=not args.no_browser)

    if args.command == "config":
        return validate(args.config)

    try:
        if args.config:
            if any(
                value is not None
                for value in (args.bbox, args.start, args.end, args.limit)
            ):
                parser.error(
                    "--config cannot be combined with --bbox, --start, --end, or --limit"
                )
            config = load_config(args.config)
            if args.provider not in config.search.providers:
                parser.error(f"search.providers must include {args.provider}")
            if config.search.product != PRODUCTS[args.provider]:
                parser.error(
                    f"{args.provider} requires search.product: {PRODUCTS[args.provider]}"
                )
            query = config.search_query()
            if args.beam_mode is not None:
                query = replace(query, beam_mode=args.beam_mode)
        else:
            if args.bbox is None or args.start is None or args.end is None:
                parser.error("provide --config or all of --bbox, --start, and --end")
            limit = args.limit if args.limit is not None else 100
            query = SearchQuery(
                tuple(args.bbox),
                args.start,
                args.end,
                limit,
                beam_mode=args.beam_mode,
            )
        if (
            args.beam_mode
            and args.provider == "asf"
            and args.beam_mode not in ("IW", "EW", "SM")
        ):
            parser.error("Sentinel-1 beam mode must be IW, EW, or SM")
    except ConfigError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        parser.error(str(exc))
    try:
        adapter = (
            ASFAdapter() if args.provider == "asf" else make_adapter(args.provider)
        )
        scenes = adapter.search(query)
    except (
        ASFQueryError,
        ASFResultError,
        ICEYEResultError,
        CapellaResultError,
        UmbraResultError,
        NISARResultError,
        asf_search.ASFError,
        asf_search.CMRError,
        requests.RequestException,
    ) as exc:
        print(f"{args.provider.upper()} search failed: {exc}", file=sys.stderr)
        return 1
    manifest = {
        "type": "FeatureCollection",
        "query": {
            "provider": args.provider,
            "product": PRODUCTS[args.provider],
            "bbox": list(query.bbox),
            "start": query.start.isoformat().replace("+00:00", "Z"),
            "end": query.end.isoformat().replace("+00:00", "Z"),
            "max_results": query.max_results,
            "beam_mode": query.beam_mode,
            "polarizations": list(query.polarizations)
            if query.polarizations is not None
            else None,
        },
        "features": [scene.to_feature() for scene in scenes],
    }
    serialized = json.dumps(manifest, indent=2) + "\n"
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as output:
                output.write(serialized)
        except OSError as exc:
            print(f"Cannot write discovery manifest: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(serialized)
    return 0
