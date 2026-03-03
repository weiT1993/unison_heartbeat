"""Generate and install macOS LaunchAgent for Unison sync."""

import json
import os
import subprocess
import sys
from typing import Any

from unison_heartbeat.cache import (clean_unison_state, cleanup_artifacts,
                                    get_unison_paths)
from unison_heartbeat.health import check_sync_health

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.unison-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{unison_py}</string>
        <string>daemon</string>
        <string>{config_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{unison_log_dir}/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{unison_log_dir}/launchd-stderr.log</string>
</dict>
</plist>
"""

LABEL = "com.user.unison-sync"


def _get_config_path() -> str:
    """Get the path to store the config for the daemon."""
    home = os.environ.get("HOME")
    if not home:
        raise EnvironmentError("HOME environment variable is not set")
    return os.path.join(home, ".unison", "heartbeat-config.json")


def _get_plist_dest() -> str:
    """Get the destination path for the LaunchAgent plist file."""
    home = os.environ.get("HOME")
    if not home:
        raise EnvironmentError("HOME environment variable is not set")
    return os.path.join(home, "Library", "LaunchAgents", f"{LABEL}.plist")


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


def start(config: dict[str, Any]) -> None:
    """
    Stop any existing sync, then install and load the LaunchAgent.

    Args:
        config: Configuration dictionary with unison_log_dir, sync_points,
                heartbeat_interval, and max_log_lines.
    """
    unison_log_dir = config["unison_log_dir"]

    stop()

    config_path = _get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f)

    unison_py = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "unison.py"
    )
    plist_content = PLIST_TEMPLATE.format(
        python_path=sys.executable,
        unison_py=os.path.abspath(unison_py),
        config_path=config_path,
        working_dir=os.path.dirname(config_path),
        unison_log_dir=unison_log_dir,
    )
    dest = _get_plist_dest()

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as f:
        f.write(plist_content)
    print(f"Created: {dest}")

    os.makedirs(unison_log_dir, exist_ok=True)
    print(f"Created: {unison_log_dir}")

    result = subprocess.run(["launchctl", "load", dest], capture_output=True, text=True)
    if result.returncode == 0:
        print("LaunchAgent loaded successfully.")
        print("\nSync running.")
    else:
        print(f"Failed to load: {result.stderr}")
        sys.exit(1)


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
    """Unload and remove the LaunchAgent and clean up artifacts."""
    dest = _get_plist_dest()
    subprocess.run(["launchctl", "unload", dest], capture_output=True)
    if os.path.exists(dest):
        os.remove(dest)
        print(f"Removed: {dest}")

    config_path = _get_config_path()
    if os.path.exists(config_path):
        config = _load_saved_config()
        unison_log_dir = config["unison_log_dir"]

        if os.path.isdir(unison_log_dir):
            for log_file in ["launchd-stdout.log", "launchd-stderr.log"]:
                log_path = os.path.join(unison_log_dir, log_file)
                if os.path.exists(log_path):
                    os.remove(log_path)
                    print(f"Removed: {log_path}")

        os.remove(config_path)
        cleanup_artifacts(config)

    print("LaunchAgent stopped.")


def _print_launchctl_status() -> tuple[str | None, str | None]:
    """
    Query launchctl for the agent's PID and exit status.

    Returns:
        Tuple of (pid, exit_status), either may be None.
    """
    pid = None
    exit_status = None
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if LABEL not in line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            pid = parts[0] if parts[0] != "-" else None
            exit_status = parts[1] if len(parts) > 1 else None
        break
    return pid, exit_status


def status() -> None:
    """Show detailed status of the LaunchAgent."""
    config = _load_saved_config()
    unison_log_dir = config["unison_log_dir"]
    sync_points = config["sync_points"]
    status_check_timeout = 5

    plist_path = _get_plist_dest()
    plist_installed = os.path.exists(plist_path)
    print(f"LaunchAgent: {'installed' if plist_installed else 'not installed'}")
    print(f"Plist: {plist_path}")

    if not plist_installed:
        print("Status: not installed")
        return

    pid, exit_status = _print_launchctl_status()
    if pid:
        print(f"Status: running (PID: {pid})")
    else:
        status_msg = (
            f"not running (exit: {exit_status})" if exit_status else "not running"
        )
        print(f"Status: {status_msg}")

    paths = get_unison_paths(config)
    print(f"Log dir: {paths['unison_log_dir']}")

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
