"""Wrapper to initiate and control multiple Unison sync points."""

import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

from unison_heartbeat.cache import (check_large_logfiles, delete_logfile,
                                    init_unison, write_common_prf)
from unison_heartbeat.health import check_sync_health
from unison_heartbeat.sync_point import start_sync, stop_sync, write_prf


def _log_restart(logfile: str, ssh_name: str) -> None:
    """
    Write a timestamped restart event to the log file.

    Args:
        logfile: Path to the log file.
        ssh_name: SSH host name that was restarted.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(logfile, "a") as f:
        f.write(f"\n[{timestamp}] RESTART: {ssh_name} - no log activity detected\n")


def find_unison_binary() -> str:
    """
    Find the unison binary path.

    Returns:
        Path to unison binary.

    Raises:
        FileNotFoundError: If unison binary is not found.
    """
    result = subprocess.run(["which", "unison"], capture_output=True, text=True)
    if result.returncode == 0:
        found = result.stdout.strip()
    else:
        if sys.platform == "linux":
            candidates = ["/usr/bin/unison", "/usr/local/bin/unison"]
        else:
            candidates = [
                "/opt/homebrew/bin/unison",
                "/usr/local/bin/unison",
                "/usr/bin/unison",
            ]
        found = next((p for p in candidates if os.path.exists(p)), "")
    if not found:
        raise FileNotFoundError(
            "Unison binary not found. Please install unison or add it to PATH."
        )
    return found


def _start_all_syncs(
    config: dict[str, Any],
    dirs: dict[str, str],
    unison_path: str,
) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, subprocess.Popen]]:
    """
    Write profiles and start sync processes for all configured sync points.

    Args:
        config: Configuration dictionary.
        dirs: Dictionary with unison_dir and unison_log_dir paths.
        unison_path: Path to unison binary.

    Returns:
        Tuple of (profile_logfiles, profile_to_sync, processes) mappings.
    """
    profile_logfiles: dict[str, str] = {}
    profile_to_sync: dict[str, dict[str, str]] = {}
    processes: dict[str, subprocess.Popen] = {}

    for sync in config["sync_points"]:
        prf_name, logfile = write_prf(
            unison_dir=dirs["unison_dir"],
            unison_log_dir=dirs["unison_log_dir"],
            ssh_name=sync["ssh"],
            remote_dir=sync["remote_dir"],
            local_dir=sync["local_dir"],
        )
        profile_logfiles[prf_name] = logfile
        profile_to_sync[prf_name] = sync
        processes[prf_name] = start_sync(unison_path, prf_name)

    return profile_logfiles, profile_to_sync, processes


def run(config: dict[str, Any]) -> None:
    """
    Start Unison sync agents and monitor their health.

    Args:
        config: Configuration dictionary with sync_points, unison_log_dir,
                heartbeat_interval, and max_log_lines.
    """
    heartbeat_interval = config["heartbeat_interval"]
    max_log_lines = config["max_log_lines"]

    dirs = init_unison(config)
    unison_path = find_unison_binary()
    write_common_prf(dirs["unison_dir"], 5)

    profile_logfiles, profile_to_sync, processes = _start_all_syncs(
        config, dirs, unison_path
    )
    logfiles = set(profile_logfiles.values())

    try:
        while True:
            time.sleep(heartbeat_interval)

            for lf in check_large_logfiles(logfiles, max_log_lines):
                print(f"[DELETE] {lf} exceeded {max_log_lines} lines")
                delete_logfile(lf)

            for profile, logfile in profile_logfiles.items():
                sync = profile_to_sync[profile]
                if not check_sync_health(
                    sync["local_dir"], logfile, heartbeat_interval
                ):
                    print(f"[STUCK] {sync['ssh']} - no log activity, restarting")
                    _log_restart(logfile, sync["ssh"])
                    stop_sync(processes[profile], profile)
                    processes[profile] = start_sync(unison_path, profile)
    except KeyboardInterrupt:
        print("\nShutting down...")
        for profile, proc in processes.items():
            stop_sync(proc, profile)
