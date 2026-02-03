"""CLI entry point for the LaunchAgent daemon."""

import json
import sys

from unison_heartbeat.manager import run


def main() -> None:
    """Load config from file and run the sync daemon."""
    if len(sys.argv) < 2:
        print("Usage: python -m unison_heartbeat.cli <config_path>")
        sys.exit(1)

    config_path = sys.argv[1]
    with open(config_path) as f:
        config = json.load(f)

    run(config)


if __name__ == "__main__":
    main()
