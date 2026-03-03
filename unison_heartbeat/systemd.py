"""Linux background service for Unison sync (nohup + PID file)."""

import json
import os
import signal
import subprocess
import sys
from typing import Any

from unison_heartbeat.cache import (clean_unison_state, cleanup_artifacts,
                                    get_unison_paths)
from unison_heartbeat.health import check_sync_health

SERVICE_NAME = "unison-sync"


def _get_config_path() -> str:
    """Get the path to store the config for the daemon."""
    home = os.environ.get("HOME")
    if not home:
        raise EnvironmentError("HOME environment variable is not set")
    return os.path.join(home, ".unison", "heartbeat-config.json")


def _get_pid_path() -> str:
    """Get the path to the PID file."""
    home = os.environ.get("HOME")
    if not home:
        raise EnvironmentError("HOME environment variable is not set")
    return os.path.join(home, ".unison", f"{SERVICE_NAME}.pid")


def _get_log_path() -> str:
    """Get the path to the daemon log file."""
    home = os.environ.get("HOME")
    if not home:
        raise EnvironmentError("HOME environment variable is not set")
    return os.path.join(home, ".unison", f"{SERVICE_NAME}.log")


def _load_saved_config() -> dict[str, Any]:
    """
    Load config from the saved location.

    Returns:
        Parsed configuration dictionary.

    Raises:
        SystemExit: If saved config does not exist or is unreadable.
    """
    config_path = _get_config_path()
    try:
        with open(config_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"No saved config at {config_path}: {exc}", file=sys.stderr)
        sys.exit(1)


def _read_pid() -> int:
    """
    Read PID from the PID file and verify the process is alive.

    Returns:
        The PID if the process is running, 0 otherwise.
    """
    pid = 0
    pid_path = _get_pid_path()
    if os.path.exists(pid_path):
        try:
            with open(pid_path) as f:
                candidate = int(f.read().strip())
            os.kill(candidate, 0)
            pid = candidate
        except (ValueError, OSError):
            pass
    return pid


def start(config: dict[str, Any]) -> None:
    """
    Stop any existing sync, then launch the daemon in the background.

    Args:
        config: Configuration dictionary with unison_log_dir, sync_points,
                heartbeat_interval, and max_log_lines.
    """
    stop()

    config_path = _get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f)

    unison_py = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "unison.py"
    )
    unison_py = os.path.abspath(unison_py)
    log_path = _get_log_path()
    pid_path = _get_pid_path()

    with open(log_path, "a") as log_file:
        proc = subprocess.Popen(
            [sys.executable, "-u", unison_py, "daemon", config_path],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

    with open(pid_path, "w") as f:
        f.write(str(proc.pid))

    print(f"Daemon started (PID: {proc.pid})")
    print(f"Log: {log_path}")
    print("\nSync running.")


def force_start(config: dict[str, Any]) -> None:
    """
    Wipe all Unison state locally and on remotes, then start fresh.

    Args:
        config: Configuration dictionary.
    """
    stop()
    clean_unison_state(config)
    start(config)


def stop() -> None:
    """Stop the daemon and clean up artifacts."""
    stopped_anything = False

    pid = _read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped daemon (PID: {pid})")
            stopped_anything = True
        except OSError as exc:
            print(f"Warning: could not stop PID {pid}: {exc}")

    pid_path = _get_pid_path()
    if os.path.exists(pid_path):
        os.remove(pid_path)

    config_path = _get_config_path()
    if os.path.exists(config_path):
        config = _load_saved_config()
        os.remove(config_path)
        cleanup_artifacts(config)
        stopped_anything = True

    log_path = _get_log_path()
    if os.path.exists(log_path):
        os.remove(log_path)
        print(f"Removed: {log_path}")

    if stopped_anything:
        print("Service stopped.")


def status() -> None:
    """Show daemon status and sync health."""
    config = _load_saved_config()
    unison_log_dir = config["unison_log_dir"]
    sync_points = config["sync_points"]
    status_check_timeout = 5

    pid = _read_pid()
    if pid:
        print(f"Status: running (PID: {pid})")
    else:
        print("Status: not running")

    log_path = _get_log_path()
    print(f"Daemon log: {log_path}")

    paths = get_unison_paths(config)
    print(f"Sync log dir: {paths['unison_log_dir']}")

    print(f"\nSync points: {len(sync_points)} configured")
    print("Checking sync health (this may take a few seconds per sync point)...")
    for sp in sync_points:
        ssh_name = sp["ssh"]
        logfile = os.path.join(unison_log_dir, f"unison-{ssh_name}.log")
        healthy = check_sync_health(sp["local_dir"], logfile, status_check_timeout)
        status_str = "healthy" if healthy else "STUCK"
        print(
            f"  {ssh_name}: {sp['local_dir']} <-> {sp['remote_dir']}" f" [{status_str}]"
        )
