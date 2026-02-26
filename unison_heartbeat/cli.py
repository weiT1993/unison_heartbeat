"""CLI entry point for unison_heartbeat."""

import argparse
import json
import sys
from typing import Any

from unison_heartbeat import foreground, launchagent
from unison_heartbeat.manager import run

_MODE_MODULES = {
    "foreground": foreground,
    "launchagent": launchagent,
}


def _load_config(path: str) -> dict[str, Any]:
    """
    Load and validate a JSON config file.

    Args:
        path: Path to the JSON config file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        SystemExit: If the file cannot be read or is missing required keys.
    """
    try:
        with open(path) as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error reading config: {exc}", file=sys.stderr)
        sys.exit(1)

    required = ["unison_log_dir", "sync_points", "heartbeat_interval", "max_log_lines"]
    missing = [k for k in required if k not in config]
    if missing:
        print(f"Missing config keys: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return config


def main() -> None:
    """Parse arguments and dispatch to the chosen mode handler."""
    parser = argparse.ArgumentParser(
        prog="unison_heartbeat",
        description="Bidirectional file sync with heartbeat monitoring",
    )
    parser.add_argument(
        "--mode",
        choices=["foreground", "launchagent"],
        required=True,
        help="Running mode: foreground (blocks, Ctrl+C) or launchagent (macOS daemon)",
    )
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="Start syncing")
    start_p.add_argument("--config", required=True, help="Path to JSON config file")

    stop_p = sub.add_parser("stop", help="Stop syncing and clean up artifacts")
    stop_p.add_argument("--config", required=True, help="Path to JSON config file")

    status_p = sub.add_parser("status", help="Show sync health")
    status_p.add_argument("--config", required=True, help="Path to JSON config file")

    daemon_p = sub.add_parser(
        "daemon", help="Run sync loop directly (used by LaunchAgent)"
    )
    daemon_p.add_argument("config_path", help="Path to JSON config file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "daemon":
        config = _load_config(args.config_path)
        run(config)
        return

    module = _MODE_MODULES[args.mode]
    config = _load_config(args.config)

    commands = {
        "start": module.start,
        "stop": module.stop,
        "status": module.status,
    }
    commands[args.command](config)


if __name__ == "__main__":
    main()
