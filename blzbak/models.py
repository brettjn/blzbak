"""Data models for blzbak."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

_VALID_SET_NAME = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_set_name(name: str) -> str:
    """Raise ValueError if name contains path-unsafe characters."""
    if not name or not _VALID_SET_NAME.match(name):
        raise ValueError(
            f"Invalid backup set name '{name}'. "
            "Only letters, digits, hyphens, and underscores are allowed."
        )
    return name


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ServerConfig:
    host: str
    port: int = 7890
    ssh_user: str = ""
    dest_path: str = ""         # Absolute path for this backup set on the server

    def rsync_dest(self, subdir: str = "C") -> str:
        """Build an rsync-compatible host:path destination string."""
        prefix = f"{self.ssh_user}@" if self.ssh_user else ""
        return f"{prefix}{self.host}:{self.dest_path}/{subdir}"

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "ssh_user": self.ssh_user,
            "dest_path": self.dest_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServerConfig":
        return cls(
            host=data.get("host", ""),
            port=int(data.get("port", 7890)),
            ssh_user=data.get("ssh_user", ""),
            dest_path=data.get("dest_path", ""),
        )


@dataclass
class BackupSet:
    name: str
    source_paths: list[str]
    server: ServerConfig
    schedule: str = "0 2 * * *"
    exclude_patterns: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": 1,
            "created_at": self.created_at,
            "updated_at": _now_iso(),
            "source_paths": self.source_paths,
            "schedule": self.schedule,
            "server": self.server.to_dict(),
            "exclude_patterns": self.exclude_patterns,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupSet":
        now = _now_iso()
        return cls(
            name=data["name"],
            source_paths=data.get("source_paths", []),
            server=ServerConfig.from_dict(data.get("server", {})),
            schedule=data.get("schedule", "0 2 * * *"),
            exclude_patterns=data.get("exclude_patterns", []),
            created_at=data.get("created_at", now),
            updated_at=data.get("updated_at", now),
        )


@dataclass
class Snapshot:
    """Represents a backup snapshot (C = current, O = once-removed)."""
    set_name: str
    label: str          # "C" or "O"
    timestamp: str
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "set_name": self.set_name,
            "label": self.label,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
        }
