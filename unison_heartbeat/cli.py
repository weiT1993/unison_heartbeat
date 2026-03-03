"""CLI entry point for unison_heartbeat."""

import argparse
import json
import sys
import types
from typing import Any

from unison_heartbeat import launchagent, systemd
from unison_heartbeat.manager import run

_BACKENDS: dict[str, types.ModuleType] = {
    "darwin": launchagent,
    "linux": systemd,
}


def _get_backend() -> types.ModuleType:
    """
    Return the platform-appropriate backend module.

    Returns:
        Module with start, stop, and status functions.

    Raises:
        SystemExit: If the current platform is not supported.
    """
    backend = _BACKENDS.get("darwin" if sys.platform == "darwin" else "linux")
    if not backend:
        print(f"Unsupported platform: {sys.platform}", file=sys.stderr)
        sys.exit(1)
    return backend


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
    """Parse arguments and dispatch to the platform-appropriate backend."""
    parser = argparse.ArgumentParser(
        prog="unison_heartbeat",
        description="Bidirectional file sync with heartbeat monitoring",
    )
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="Start syncing")
    start_p.add_argument("--config", required=True, help="Path to JSON config file")

    sub.add_parser("stop", help="Stop syncing and clean up artifacts")
    sub.add_parser("status", help="Show sync health")

    clean_p = sub.add_parser(
        "force_start", help="Wipe all Unison state and start fresh"
    )
    clean_p.add_argument("--config", required=True, help="Path to JSON config file")

    daemon_p = sub.add_parser("daemon")
    daemon_p.add_argument("config_path", help="Path to JSON config file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "daemon":
        config = _load_config(args.config_path)
        run(config)
        return

    backend = _get_backend()
    config_commands = {"start": backend.start, "force_start": backend.force_start}
    no_config_commands = {"stop": backend.stop, "status": backend.status}

    if args.command in config_commands:
        config_commands[args.command](_load_config(args.config))
    elif args.command in no_config_commands:
        no_config_commands[args.command]()


if __name__ == "__main__":
    main()
