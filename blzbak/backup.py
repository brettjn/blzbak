"""Backup set persistence — load/save YAML files in the sets_directory."""

import logging
import sys
from pathlib import Path
from typing import Optional

import yaml

from .models import BackupSet, validate_set_name

logger = logging.getLogger(__name__)


def _sets_dir(config: dict) -> Path:
    p = Path(config.get("sets_directory", "."))
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_set_path(name: str, config: dict) -> Path:
    """Return the filesystem path for a backup set's YAML file."""
    return _sets_dir(config) / f"{name}.yaml"


def list_backup_sets(config: dict) -> list[BackupSet]:
    """Return all backup sets found in the sets_directory."""
    sets: list[BackupSet] = []
    for f in sorted(_sets_dir(config).glob("*.yaml")):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
            sets.append(BackupSet.from_dict(data))
        except Exception as exc:
            logger.warning("Could not load backup set from %s: %s", f.name, exc)
    return sets


def load_backup_set(name: str, config: dict) -> Optional[BackupSet]:
    validate_set_name(name)
    path = get_set_path(name, config)
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml.safe_load(f)
    return BackupSet.from_dict(data)


def save_backup_set(bs: BackupSet, config: dict) -> None:
    validate_set_name(bs.name)
    path = get_set_path(bs.name, config)
    with open(path, "w") as f:
        yaml.dump(bs.to_dict(), f, default_flow_style=False, sort_keys=False)
    logger.debug("Saved backup set '%s'", bs.name)


def delete_backup_set(name: str, config: dict) -> bool:
    """Delete a backup set's YAML file.  Returns True if it existed."""
    validate_set_name(name)
    path = get_set_path(name, config)
    if not path.exists():
        return False
    path.unlink()
    logger.info("Deleted backup set config '%s'", name)
    return True
