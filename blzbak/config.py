"""Configuration management for the blzbak CLI.

The CLI looks for its .config and .blzbak-ignore files in the same directory
as the blzbak executable (sys.argv[0]).  Defaults are used when no file is found.

Config file format (YAML):

    server:
      host: 192.168.1.100
      port: 7890
      ssh_user: backup
      backup_base: /blzbak      # base path for all backup sets on the server
    sets_directory: /opt/blzbak/sets
    log_level: INFO
"""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

CONFIG_FILENAME  = ".config"
IGNORE_FILENAME  = ".blzbak-ignore"
DEFAULT_PORT     = 7890
DEFAULT_BACKUP_BASE = "/blzbak"

logger = logging.getLogger(__name__)


def get_executable_dir() -> Path:
    """Return the directory that contains the blzbak executable."""
    return Path(sys.argv[0]).resolve().parent


def _find_sibling(filename: str) -> Optional[Path]:
    p = get_executable_dir() / filename
    return p if p.exists() else None


def load_config(config_path: Optional[Path] = None) -> dict:
    """Load CLI configuration, merging file values over defaults.

    Args:
        config_path: Explicit path to a .config file.  When omitted the file
                     is searched for next to the executable.
    """
    defaults: dict[str, Any] = {
        "server": {
            "host": "localhost",
            "port": DEFAULT_PORT,
            "ssh_user": "",
            "backup_base": DEFAULT_BACKUP_BASE,
        },
        "sets_directory": str(get_executable_dir() / "sets"),
        "log_level": "INFO",
    }

    path = config_path or _find_sibling(CONFIG_FILENAME)
    if path and path.exists():
        with open(path) as f:
            file_cfg = yaml.safe_load(f) or {}
        _deep_merge(defaults, file_cfg)
        logger.debug("Loaded config from %s", path)
    else:
        logger.debug("No config file found; using defaults")

    return defaults


def save_config(config: dict, config_path: Optional[Path] = None) -> None:
    """Persist config dict to the .config YAML file."""
    path = config_path or (get_executable_dir() / CONFIG_FILENAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def load_ignore_patterns(ignore_path: Optional[Path] = None) -> list[str]:
    """Return non-comment lines from the .blzbak-ignore file."""
    path = ignore_path or _find_sibling(IGNORE_FILENAME)
    if not path or not path.exists():
        return []
    patterns: list[str] = []
    with open(path) as f:
        for line in f:
            stripped = line.rstrip("\n").strip()
            if stripped and not stripped.startswith("#"):
                patterns.append(stripped)
    return patterns


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=numeric,
    )


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
