"""Single sync point management for Unison."""

import os
import subprocess
import time

HEARTBEAT_FILENAME = ".unison-heartbeat"


def write_prf(
    *,
    unison_dir: str,
    unison_log_dir: str,
    ssh_name: str,
    remote_dir: str,
    local_dir: str,
) -> tuple[str, str]:
    """
    Write a Unison profile file for a specific sync point.

    Args:
        unison_dir: Directory for Unison profiles.
        unison_log_dir: Directory for Unison logs.
        ssh_name: SSH host name.
        remote_dir: Remote directory path.
        local_dir: Local directory path.

    Returns:
        Tuple of (profile_name, logfile_path).
    """
    logfile = os.path.join(unison_log_dir, f"unison-{ssh_name}.log")
    sync_dir_name = remote_dir.split("/")[-1]
    prf_name = f"unison-{ssh_name}-{sync_dir_name}"
    prf_content = f"""root = {local_dir}
root = ssh://{ssh_name}//{remote_dir}

include unison-common_settings.prf

log = true
logfile = {logfile}
"""
    prf_path = os.path.join(unison_dir, f"{prf_name}.prf")
    with open(prf_path, "w") as f:
        f.write(prf_content)
    return prf_name, logfile


def start_sync(unison_path: str, profile: str) -> subprocess.Popen:
    """
    Start a Unison sync process for a profile.

    Args:
        unison_path: Path to unison binary.
        profile: Name of the unison profile.

    Returns:
        The subprocess.Popen object for the running process.
    """
    cmd = [unison_path, "-ui", "text", profile]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Started Unison for {profile} (PID {proc.pid})")
    return proc


def stop_sync(proc: subprocess.Popen, profile: str) -> None:
    """
    Stop a Unison sync process.

    Args:
        proc: The subprocess.Popen object to terminate.
        profile: Name of the profile (for logging).
    """
    proc.terminate()
    proc.wait()
    print(f"Stopped Unison for {profile}")


def write_heartbeat(local_dir: str) -> None:
    """
    Write a heartbeat file to the local directory.

    Args:
        local_dir: Local directory being synced.
    """
    heartbeat_path = os.path.join(local_dir, HEARTBEAT_FILENAME)
    with open(heartbeat_path, "w") as f:
        f.write(str(time.time()))
