"""Cron job installation and management for blzbak.

Every cron entry managed by blzbak contains a trailing tag of the form:
    # blzbak-managed:<set_name>

This tag is used to identify, update, and remove entries without touching
any other cron lines the user may have.
"""

import logging
import re
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)

_CRON_TAG    = "# blzbak-managed"
_SET_TAG_RE  = re.compile(r"#\s*blzbak-managed:(\S+)")


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
    """Install (or replace) the cron job for *set_name*."""
    if blzbak_cmd is None:
        blzbak_cmd = sys.argv[0]
    crontab = _get_crontab()
    # Remove existing entry for this set, keep all others
    lines = [l for l in crontab.splitlines() if _set_tag_name(l) != set_name]
    lines.append(_make_entry(schedule, set_name, blzbak_cmd))
    _set_crontab("\n".join(lines) + "\n")
    logger.info("Cron job installed for '%s': %s", set_name, schedule)


def remove_cron_job(set_name: str) -> bool:
    """Remove the cron job for *set_name*.  Returns True if one was removed."""
    crontab = _get_crontab()
    lines    = crontab.splitlines()
    filtered = [l for l in lines if _set_tag_name(l) != set_name]
    if len(filtered) == len(lines):
        return False
    _set_crontab("\n".join(filtered) + "\n")
    logger.info("Cron job removed for '%s'", set_name)
    return True


def list_cron_jobs() -> list[dict]:
    """Return a list of dicts describing all blzbak-managed cron jobs."""
    crontab = _get_crontab()
    jobs: list[dict] = []
    for line in crontab.splitlines():
        name = _set_tag_name(line)
        if name:
            parts    = line.split()
            schedule = " ".join(parts[:5]) if len(parts) >= 5 else ""
            jobs.append({"set_name": name, "schedule": schedule, "entry": line})
    return jobs
