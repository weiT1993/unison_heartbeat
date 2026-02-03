"""Wrapper to initiate and control multiple Unison sync points."""

import os
import subprocess
import time
from datetime import datetime
from typing import Any

from unison_heartbeat.cache import (
    check_large_logfiles,
    delete_logfile,
    init_unison,
    write_common_prf,
)
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
    try:
        result = subprocess.run(
            ["which", "unison"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        common_paths = [
            "/opt/homebrew/bin/unison",
            "/usr/local/bin/unison",
            "/usr/bin/unison",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        raise FileNotFoundError(
            "Unison binary not found. Please install unison or add it to PATH."
        )


def run(config: dict[str, Any]) -> None:
    """
    Start Unison sync agents and monitor their health.

    Args:
        config: Configuration dictionary with sync_points, unison_log_dir,
                heartbeat_interval, and max_log_lines.
    """
    heartbeat_interval = config["heartbeat_interval"]
    max_log_lines = config["max_log_lines"]
    sync_interval = 5

    dirs = init_unison(config)
    unison_path = find_unison_binary()

    write_common_prf(dirs["unison_dir"], sync_interval)

    syncs = config["sync_points"]
    profile_logfiles: dict[str, str] = {}
    profile_to_sync: dict[str, dict[str, str]] = {}
    processes: dict[str, subprocess.Popen] = {}

    for sync in syncs:
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

    logfiles = set(profile_logfiles.values())

    try:
        while True:
            time.sleep(heartbeat_interval)

            large_logfiles = check_large_logfiles(logfiles, max_log_lines)
            for logfile in large_logfiles:
                print(f"[DELETE] {logfile} exceeded {max_log_lines} lines")
                delete_logfile(logfile)

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
