"""Config validation command used before provider integrations are enabled."""

import argparse
import sys

from sartool.config import ConfigError, load_config


def validate(config_path: str) -> int:
    """Validate a config file and report a concise result to the user."""
    try:
        load_config(config_path)
    except ConfigError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 2
    print(f"Configuration valid: {config_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sartool")
    commands = parser.add_subparsers(dest="command", required=True)
    config_parser = commands.add_parser("config", help="manage tool configuration")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    validate_parser = config_commands.add_parser(
        "validate", help="validate a YAML config file"
    )
    validate_parser.add_argument(
        "--config", required=True, help="path to the YAML config file"
    )
    args = parser.parse_args(argv)
    return validate(args.config)
