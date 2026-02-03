"""Cache and artifact organization for Unison sync."""

import glob
import os
import shutil
from typing import Any


def _count_lines(filepath: str) -> int:
    """
    Count the number of lines in a file.

    Args:
        filepath: Path to the file.

    Returns:
        Number of lines in the file.
    """
    with open(filepath) as f:
        return sum(1 for _ in f)


def get_unison_paths(config: dict[str, Any]) -> dict[str, str]:
    """
    Get paths for unison directories.

    Args:
        config: Configuration dictionary with unison_log_dir.

    Returns:
        Dictionary with script_dir, unison_dir, and unison_log_dir paths.

    Raises:
        EnvironmentError: If HOME environment variable is not set.
    """
    home_dir = os.environ.get("HOME")
    if not home_dir:
        raise EnvironmentError("HOME environment variable is not set")
    return {
        "script_dir": os.path.dirname(os.path.abspath(__file__)),
        "unison_dir": os.path.join(home_dir, ".unison"),
        "unison_log_dir": config["unison_log_dir"],
    }


def init_unison(config: dict[str, Any]) -> dict[str, str]:
    """
    Initialize unison directories and clean up old profile files.

    Args:
        config: Configuration dictionary.

    Returns:
        Dictionary with unison_dir and unison_log_dir paths.
    """
    paths = get_unison_paths(config)
    script_dir = paths["script_dir"]
    unison_dir = paths["unison_dir"]
    unison_log_dir = paths["unison_log_dir"]

    for dir_to_check in [script_dir, unison_dir]:
        if os.path.isdir(dir_to_check):
            for file in glob.glob(f"{dir_to_check}/*"):
                _, ext = os.path.splitext(file)
                if ext.lower() in [".prf", ".sh"]:
                    os.remove(file)

    if not os.path.exists(unison_dir):
        os.makedirs(unison_dir)
    if not os.path.exists(unison_log_dir):
        os.makedirs(unison_log_dir)

    return {
        "unison_dir": unison_dir,
        "unison_log_dir": unison_log_dir,
    }


def cleanup_artifacts(config: dict[str, Any]) -> None:
    """
    Clean up unison logs and profile files.

    Args:
        config: Configuration dictionary.
    """
    paths = get_unison_paths(config)
    unison_dir = paths["unison_dir"]
    unison_log_dir = paths["unison_log_dir"]

    if os.path.isdir(unison_log_dir):
        shutil.rmtree(unison_log_dir)
        print(f"Removed: {unison_log_dir}")

    if os.path.isdir(unison_dir):
        for prf_file in glob.glob(os.path.join(unison_dir, "unison-*.prf")):
            os.remove(prf_file)
            print(f"Removed: {prf_file}")


def check_large_logfiles(logfiles: set[str], max_lines: int) -> list[str]:
    """
    Return log files that exceed the maximum line count.

    Args:
        logfiles: Set of log file paths to check.
        max_lines: Maximum number of lines allowed.

    Returns:
        List of log files exceeding max_lines.
    """
    large = []
    for logfile in logfiles:
        if os.path.exists(logfile) and _count_lines(logfile) > max_lines:
            large.append(logfile)
    return large


def delete_logfile(logfile: str) -> None:
    """
    Delete a log file.

    Args:
        logfile: Path to the log file to delete.
    """
    if os.path.exists(logfile):
        os.remove(logfile)


def write_common_prf(unison_dir: str, sync_interval: int) -> None:
    """
    Write common Unison profile settings to a .prf file.

    Args:
        unison_dir: Directory for Unison profiles.
        sync_interval: Seconds between sync polls.
    """
    prf_content = f"""ignore = Name {{.DS_Store,.Spotlight-V100,.Trashes,.fseventsd}}
ignore = Path */{{.metadata,.settings,.project,.classpath}}
ignore = Name {{.iml,.iws}}
ignore = Path */.idea
ignore = Name {{[._]*.s[a-v][a-z],[._]*.sw[a-p],[._]s[a-v][a-z],[._]sw[a-p],Session.vim,Sessionx.vim}}
ignore = BelowPath */{{env,logs,out}}
ignore    = Path */build/*/*/*/*/build/{{,.}}?*
ignorenot = Path */build/*/*/*/*/build/brazil-integration-tests
ignore    = Path */build/*/*/*/*/build/brazil-integration-tests/{{,.}}?*
ignorenot = Path */build/*/*/*/*/build/brazil-integration-tests/{{*.html,*.css,com}}
ignorenot = Path */build/*/*/*/*/build/brazil-integ-tests
ignore    = Path */build/*/*/*/*/build/brazil-integ-tests/{{,.}}?*
ignorenot = Path */build/*/*/*/*/build/brazil-integ-tests/{{*.html,*.css,com}}
ignorenot = Path */build/*/*/*/*/build/brazil-unit-tests
ignore    = Path */build/*/*/*/*/build/brazil-unit-tests/{{,.}}?*
ignorenot = Path */build/*/*/*/*/build/brazil-unit-tests/{{*.html,*.css,com}}
ignorenot = Path */build/*/*/*/*/build/generated-src
ignore    = Path */build/*/*/*/*/build/generated-src/{{,.}}?*
ignorenot = Path */build/*/*/*/*/build/generated-src/{{*.html,*.css,com}}
ignore = Name log{{,s}}/*.log{{,.*}}
ignore  = Path Neuron-Nemo-Megatron/src/Neuron-Nemo-Megatron/nemo/examples/nlp/language_modeling/neuronxcc-*
ignore  = Path context_parallel/neuronxcc-*
ignore = Path .unison
ignorecase = false
repeat = {sync_interval}
backup = Name *
maxbackups = 5
retry = 1
auto = true
batch = true
confirmbigdeletes = true
times = true
prefer = newer
terse = true
contactquietly = true"""
    prf_path = os.path.join(unison_dir, "unison-common_settings.prf")
    with open(prf_path, "w") as f:
        f.write(prf_content)
