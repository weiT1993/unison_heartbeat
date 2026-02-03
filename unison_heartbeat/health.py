"""Heartbeat-based health detection for Unison sync points."""

import os
import time

from unison_heartbeat.sync_point import write_heartbeat


def check_sync_health(local_dir: str, logfile: str, timeout: int) -> bool:
    """
    Check if sync is working by writing a heartbeat file and verifying log updates.

    Writes a heartbeat file to the local directory, waits for the timeout period,
    then checks if the log file was modified. If the log file modification time
    increased, the sync is considered healthy.

    Args:
        local_dir: Local directory being synced.
        logfile: Path to the unison log file for this sync point.
        timeout: Seconds to wait for sync to complete.

    Returns:
        True if sync is healthy, False if stuck.
    """
    mtime_before = os.path.getmtime(logfile) if os.path.exists(logfile) else 0
    write_heartbeat(local_dir)
    time.sleep(timeout)
    mtime_after = os.path.getmtime(logfile) if os.path.exists(logfile) else 0
    return mtime_after > mtime_before
