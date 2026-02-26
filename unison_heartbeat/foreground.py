"""Foreground sync mode for Linux (run in tmux/screen, stop with Ctrl+C)."""

import os
from typing import Any

from unison_heartbeat.cache import cleanup_artifacts, get_unison_paths
from unison_heartbeat.health import check_sync_health
from unison_heartbeat.manager import run


def start(config: dict[str, Any]) -> None:
    """
    Run Unison sync in the foreground (blocks until Ctrl+C).

    Args:
        config: Configuration dictionary with unison_log_dir, sync_points,
                heartbeat_interval, and max_log_lines.
    """
    sync_points = config["sync_points"]
    print(f"Starting foreground sync with {len(sync_points)} sync point(s)")
    print(f"Log directory: {config['unison_log_dir']}")
    print("Press Ctrl+C to stop.\n")

    run(config)


def stop(config: dict[str, Any]) -> None:
    """
    Clean up logs and profile files.

    Args:
        config: Configuration dictionary with unison_log_dir and sync_points.
    """
    cleanup_artifacts(config)
    print("Cleaned up sync artifacts.")


def status(config: dict[str, Any]) -> None:
    """
    Check and display sync health for each sync point.

    Args:
        config: Configuration dictionary with unison_log_dir and sync_points.
    """
    status_check_timeout = 5
    unison_log_dir = config["unison_log_dir"]
    sync_points = config["sync_points"]

    paths = get_unison_paths(config)
    print(f"Log dir: {paths['unison_log_dir']}")

    print(f"\nSync points: {len(sync_points)} configured")
    print("Checking sync health (this may take a few seconds per sync point)...")
    for sp in sync_points:
        ssh_name = sp["ssh"]
        logfile = os.path.join(unison_log_dir, f"unison-{ssh_name}.log")
        healthy = check_sync_health(sp["local_dir"], logfile, status_check_timeout)
        status_str = "healthy" if healthy else "STUCK"
        print(f"  {ssh_name}: {sp['local_dir']} <-> {sp['remote_dir']} [{status_str}]")
