"""Allow `python -m sartool` to run the CLI."""

from sartool.cli import main

raise SystemExit(main())
