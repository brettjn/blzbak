"""Cron job installation and management for blzbak.

Every cron entry managed by blzbak contains a trailing tag of the form:
    # blzbak-managed:<set_name>

This tag is used to identify, update, and remove entries without touching
any other cron lines the user may have.
"""

import logging
import re
import shutil
import subprocess
import sys
from typing import Optional
from pathlib import Path
import os

logger = logging.getLogger(__name__)

_CRON_TAG    = "# blzbak-managed"
_SET_TAG_RE  = re.compile(r"#\s*blzbak-managed:(\S+)")


def _resolve_executable_path(cmd: str) -> str:
    """Return an absolute path for the given executable string.

    If `cmd` is already absolute, return it. Otherwise resolve it to an
    absolute path. Use `shutil.which` if the command is a simple name,
    or resolve relative paths using Path.resolve().
    """
    p = Path(cmd)
    if p.is_absolute():
        return str(p)
    
    # For simple command names (no slashes), try which first
    if '/' not in cmd:
        found = shutil.which(cmd)
        if found:
            return found
    
    # For relative paths or when which fails, resolve to absolute
    return str(p.resolve().absolute())


# ---------------------------------------------------------------------------
# Low-level crontab I/O
# ---------------------------------------------------------------------------

def _get_crontab() -> str:
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout
    if "no crontab" in result.stderr.lower():
        return ""
    raise RuntimeError(f"Failed to read crontab: {result.stderr.strip()}")


def _set_crontab(content: str) -> None:
    result = subprocess.run(
        ["crontab", "-"],
        input=content,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to install crontab: {result.stderr.strip()}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_tag_name(line: str) -> Optional[str]:
    """Return the backup set name embedded in a blzbak cron tag, or None."""
    m = _SET_TAG_RE.search(line)
    return m.group(1) if m else None


def _make_entry(schedule: str, set_name: str, blzbak_cmd: str) -> str:
    return f"{schedule} {blzbak_cmd} backup run {set_name} {_CRON_TAG}:{set_name}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install_cron_job(
    set_name: str,
    schedule: str,
    blzbak_cmd: Optional[str] = None,
) -> None:
    """Install (or replace) the cron job for *set_name* system-wide in /etc/cron.d.

    This always writes a file under /etc/cron.d and will attempt to elevate
    via `sudo` if direct writes are not permitted.
    """
    if blzbak_cmd is None:
        blzbak_cmd = sys.argv[0]
    blzbak_cmd = _resolve_executable_path(blzbak_cmd)
    install_system_cron_job(set_name, schedule, blzbak_cmd)
    logger.info("Cron job installed for '%s': %s", set_name, schedule)


def remove_cron_job(set_name: str) -> bool:
    """Remove the cron job for *set_name*.  Returns True if one was removed."""
    # Remove the system-wide cron.d file for this set
    return remove_system_cron_job(set_name)


def list_cron_jobs() -> list[dict]:
    """Return a list of dicts describing all blzbak-managed cron jobs."""
    jobs: list[dict] = []
    # Scan /etc/cron.d for blzbak-managed files only (system-wide)
    cron_d = Path("/etc/cron.d")
    if not cron_d.exists() or not cron_d.is_dir():
        return jobs
    for f in sorted(cron_d.glob("blzbak-*")):
        try:
            with open(f) as fh:
                line = fh.read().strip()
            name = _set_tag_name(line)
            if name:
                parts = line.split()
                # system entries include a user field after schedule
                schedule = " ".join(parts[:5]) if len(parts) >= 6 else ""
                jobs.append({"set_name": name, "schedule": schedule, "entry": line})
        except Exception:
            continue
    return jobs


# ---------------------------------------------------------------------------
# System cron.d helpers
# ---------------------------------------------------------------------------

def _system_cron_path(set_name: str) -> Path:
    return Path("/etc/cron.d") / f"blzbak-{set_name}"


def install_system_cron_job(
    set_name: str,
    schedule: str,
    blzbak_cmd: Optional[str] = None,
    user: str = "root",
) -> None:
    """Install a cron job for *set_name* into /etc/cron.d.

    The entry written uses the system cron.d format: <schedule> <user> <command>.
    Raises RuntimeError on permission failures or other IO errors.
    """
    if blzbak_cmd is None:
        blzbak_cmd = sys.argv[0]
    blzbak_cmd = _resolve_executable_path(blzbak_cmd)
    path = _system_cron_path(set_name)
    
    # Ensure required directories exist; prefer direct creation, fall back to sudo
    log_dir = Path("/var/log/blzbak")
    lib_dir = Path("/var/lib/blzbak")
    
    for dir_path in [log_dir, lib_dir]:
        try:
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                os.chmod(dir_path, 0o755)
        except Exception:
            # try creating with sudo
            try:
                subprocess.run(["sudo", "mkdir", "-p", str(dir_path)], check=True)
                subprocess.run(["sudo", "chmod", "755", str(dir_path)], check=True)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"Failed to create directory {dir_path!s}: {exc}") from exc

    # Redirect stdout/stderr to system log files
    stdout_log = "/var/log/blzbak/info.log"
    stderr_log = "/var/log/blzbak/err.log"
    redirect = f" >> {stdout_log} 2>> {stderr_log}"

    # Place redirection before the managed-comment tag so shell redirection
    # is not treated as a comment by cron parsers.
    entry = f"{schedule} {user} {blzbak_cmd} backup run {set_name}{redirect} {_CRON_TAG}:{set_name}\n"
    try:
        # Ensure directory exists (should normally) and write file atomically
        temp = Path(f"{path}.tmp")
        with open(temp, "w") as fh:
            fh.write(entry)
        # Set permissions to 0644
        os.chmod(temp, 0o644)
        temp.replace(path)
    except Exception as exc:
        # If direct write fails (likely permission), attempt to write via sudo
        try:
            subprocess.run(["sudo", "tee", str(path)], input=entry, text=True, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["sudo", "chmod", "644", str(path)], check=True)
        except subprocess.CalledProcessError as exc2:
            raise RuntimeError(
                f"Failed to write system cron file {path!s}: {exc2}; original error: {exc}"
            ) from exc2
    logger.info("Installed system cron job %s -> %s", set_name, path)


def remove_system_cron_job(set_name: str) -> bool:
    path = _system_cron_path(set_name)
    try:
        if path.exists():
            path.unlink()
            logger.info("Removed system cron job %s -> %s", set_name, path)
            return True
        return False
    except PermissionError as exc:
        raise RuntimeError(f"Permission denied removing {path!s}; try running as root") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to remove system cron file {path!s}: {exc}") from exc
