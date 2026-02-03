"""Generate and install macOS LaunchAgent for Unison sync."""

import json
import os
import subprocess
import sys

from unison_heartbeat.cache import cleanup_artifacts, get_unison_paths
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
        <string>-m</string>
        <string>unison_heartbeat.cli</string>
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


def _build_config(
    unison_log_dir: str,
    sync_points: list[dict[str, str]],
    heartbeat_interval: int,
    max_log_lines: int,
) -> dict:
    """
    Build config dictionary from parameters.

    Args:
        unison_log_dir: Directory for Unison logs.
        sync_points: List of sync point configurations.
        heartbeat_interval: Seconds between health checks.
        max_log_lines: Maximum log lines before deletion.

    Returns:
        Configuration dictionary for the daemon.
    """
    return {
        "unison_log_dir": unison_log_dir,
        "sync_points": sync_points,
        "heartbeat_interval": heartbeat_interval,
        "max_log_lines": max_log_lines,
    }


def start(
    unison_log_dir: str,
    sync_points: list[dict[str, str]],
    heartbeat_interval: int,
    max_log_lines: int,
) -> None:
    """
    Stop any existing sync, then install and load the LaunchAgent.

    Args:
        unison_log_dir: Directory for Unison logs.
        sync_points: List of sync point configurations.
        heartbeat_interval: Seconds between health checks.
        max_log_lines: Maximum log lines before deletion.
    """
    config = _build_config(
        unison_log_dir, sync_points, heartbeat_interval, max_log_lines
    )
    stop(unison_log_dir, sync_points)

    config_path = _get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f)

    plist_content = PLIST_TEMPLATE.format(
        python_path=sys.executable,
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


def stop(unison_log_dir: str, sync_points: list[dict[str, str]]) -> None:
    """
    Unload and remove the LaunchAgent and clean up artifacts.

    Args:
        unison_log_dir: Directory for Unison logs.
        sync_points: List of sync point configurations.
    """
    config = {"unison_log_dir": unison_log_dir, "sync_points": sync_points}

    dest = _get_plist_dest()
    subprocess.run(["launchctl", "unload", dest], capture_output=True)
    if os.path.exists(dest):
        os.remove(dest)
        print(f"Removed: {dest}")

    config_path = _get_config_path()
    if os.path.exists(config_path):
        os.remove(config_path)

    if os.path.isdir(unison_log_dir):
        for log_file in ["launchd-stdout.log", "launchd-stderr.log"]:
            log_path = os.path.join(unison_log_dir, log_file)
            if os.path.exists(log_path):
                os.remove(log_path)
                print(f"Removed: {log_path}")

    cleanup_artifacts(config)
    print("LaunchAgent stopped.")


def status(unison_log_dir: str, sync_points: list[dict[str, str]]) -> None:
    """
    Show detailed status of the LaunchAgent.

    Args:
        unison_log_dir: Directory for Unison logs.
        sync_points: List of sync point configurations.
    """
    config = {"unison_log_dir": unison_log_dir, "sync_points": sync_points}
    status_check_timeout = 5

    plist_path = _get_plist_dest()
    plist_installed = os.path.exists(plist_path)
    print(f"LaunchAgent: {'installed' if plist_installed else 'not installed'}")
    print(f"Plist: {plist_path}")

    if not plist_installed:
        print("Status: not installed")
        return

    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    pid = None
    exit_status = None
    for line in result.stdout.splitlines():
        if LABEL in line:
            parts = line.split()
            if len(parts) >= 2:
                pid = parts[0] if parts[0] != "-" else None
                exit_status = parts[1] if len(parts) > 1 else None
            break

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
        print(f"  {ssh_name}: {sp['local_dir']} <-> {sp['remote_dir']} [{status_str}]")
