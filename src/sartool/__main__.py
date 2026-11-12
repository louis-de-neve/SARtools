"""Allow `python -m sartool` to run the CLI."""

from sartool.config_cli import main

raise SystemExit(main())
