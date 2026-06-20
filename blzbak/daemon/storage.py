"""Storage management for blzbakd — handles backup directories and operations.

Directory structure on the server:
    /blzbak/                    (base_path)
        <set_name>/
            C/                  (current backup)
            O/                  (once-removed backup)
            metadata.yaml       (backup set metadata)
        diffs/
            <set_name>/
                <timestamp>.tar.gz
"""

import os
import subprocess
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


@dataclass
class SnapshotInfo:
    """Information about a backup snapshot."""
    label: str  # "C" or "O"
    path: str
    exists: bool
    size_bytes: int = 0
    mtime: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "timestamp": datetime.fromtimestamp(
                self.mtime, tz=timezone.utc
            ).isoformat() if self.mtime else None,
        }


class StorageManager:
    """Manages backup storage on the server."""

    def __init__(self, base_path: str, diff_dir: str):
        self.base_path = Path(base_path)
        self.diff_dir = Path(diff_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.diff_dir.mkdir(parents=True, exist_ok=True)

    def get_set_path(self, set_name: str) -> Path:
        """Get the base directory for a backup set."""
        return self.base_path / set_name

    def get_snapshot_path(self, set_name: str, label: str) -> Path:
        """Get the path for a specific snapshot (C or O)."""
        return self.get_set_path(set_name) / label

    def get_diff_dir(self, set_name: str) -> Path:
        """Get the diff directory for a backup set."""
        diff_path = self.diff_dir / set_name
        diff_path.mkdir(parents=True, exist_ok=True)
        return diff_path

    def list_sets(self) -> List[str]:
        """List all backup set names."""
        if not self.base_path.exists():
            return []
        
        sets = []
        for item in self.base_path.iterdir():
            if item.is_dir() and item.name != "diffs":
                # Verify it has at least one snapshot directory
                if (item / "C").exists() or (item / "O").exists():
                    sets.append(item.name)
        return sorted(sets)

    def get_snapshot_info(self, set_name: str, label: str) -> SnapshotInfo:
        """Get information about a specific snapshot."""
        snapshot_path = self.get_snapshot_path(set_name, label)
        
        if not snapshot_path.exists():
            return SnapshotInfo(label=label, path=str(snapshot_path), exists=False)
        
        # Calculate directory size and get modification time
        size = self._get_dir_size(snapshot_path)
        mtime = snapshot_path.stat().st_mtime
        
        return SnapshotInfo(
            label=label,
            path=str(snapshot_path),
            exists=True,
            size_bytes=size,
            mtime=mtime
        )

    def list_snapshots(self, set_name: str) -> List[SnapshotInfo]:
        """List all snapshots for a backup set."""
        snapshots = []
        for label in ["C", "O"]:
            info = self.get_snapshot_info(set_name, label)
            if info.exists:
                snapshots.append(info)
        return snapshots

    def prepare_backup(self, set_name: str) -> Dict[str, any]:
        """Prepare for a new backup by creating diffs and syncing O to C.
        
        Steps:
        1. Check if C and O exist
        2. If both exist, create a diff between C and O
        3. Sync O to match C (rsync --delete)
        4. Return status
        
        Returns:
            dict with status and any relevant info
        """
        set_path = self.get_set_path(set_name)
        c_path = self.get_snapshot_path(set_name, "C")
        o_path = self.get_snapshot_path(set_name, "O")
        
        # Ensure the set directory exists
        set_path.mkdir(parents=True, exist_ok=True)
        
        result = {
            "c_exists": c_path.exists(),
            "o_exists": o_path.exists(),
            "diff_created": False,
            "synced": False,
        }
        
        # If both C and O exist, create a diff
        if c_path.exists() and o_path.exists():
            logger.info(f"Creating diff between C and O for set '{set_name}'")
            try:
                diff_path = self._create_diff(set_name, c_path, o_path)
                result["diff_created"] = True
                result["diff_path"] = str(diff_path)
                logger.info(f"Diff created: {diff_path}")
            except Exception as e:
                logger.error(f"Failed to create diff: {e}")
                raise
            
            # Now sync O to match C
            logger.info(f"Syncing O to match C for set '{set_name}'")
            try:
                self._sync_snapshots(c_path, o_path)
                result["synced"] = True
                logger.info("Sync completed successfully")
            except Exception as e:
                logger.error(f"Failed to sync O to C: {e}")
                raise
        
        elif c_path.exists() and not o_path.exists():
            # First backup exists, prepare O directory
            logger.info(f"Creating O directory for set '{set_name}'")
            o_path.mkdir(parents=True, exist_ok=True)
        
        elif not c_path.exists():
            # First time backup - create both directories
            logger.info(f"First backup for set '{set_name}', creating C and O directories")
            c_path.mkdir(parents=True, exist_ok=True)
            o_path.mkdir(parents=True, exist_ok=True)
        
        return result

    def _create_diff(self, set_name: str, c_path: Path, o_path: Path) -> Path:
        """Create a diff archive between C and O snapshots.
        
        Uses rsync --dry-run to find differences, then creates a tar archive.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        diff_dir = self.get_diff_dir(set_name)
        diff_archive = diff_dir / f"diff_{timestamp}.tar.gz"
        
        # Use rsync to generate a list of changed files
        # rsync -an --out-format='%n' C/ O/ gives us the file list
        try:
            result = subprocess.run(
                [
                    "rsync",
                    "-an",  # archive mode, dry-run
                    "--delete",
                    "--out-format=%n",
                    f"{c_path}/",
                    f"{o_path}/",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            
            changed_files = [
                line.strip() for line in result.stdout.splitlines()
                if line.strip() and not line.startswith("deleting ")
            ]
            
            if not changed_files:
                logger.info("No changes detected between C and O")
                # Create an empty marker file
                diff_archive.write_text(f"No changes at {timestamp}")
                return diff_archive
            
            logger.info(f"Found {len(changed_files)} changed files")
            
            # Create tar archive of changed files from O
            # We save the old versions from O before syncing
            with subprocess.Popen(
                ["tar", "-czf", str(diff_archive), "-C", str(o_path)]
                + changed_files,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as proc:
                stdout, stderr = proc.communicate()
                if proc.returncode != 0:
                    # Some files might not exist in O (new files), that's okay
                    logger.debug(f"tar stderr: {stderr.decode()}")
            
            logger.info(f"Diff archive created: {diff_archive}")
            return diff_archive
            
        except subprocess.CalledProcessError as e:
            logger.error(f"rsync diff failed: {e.stderr}")
            raise RuntimeError(f"Failed to create diff: {e.stderr}")

    def _sync_snapshots(self, source: Path, dest: Path) -> None:
        """Sync source to dest using rsync --delete."""
        try:
            subprocess.run(
                [
                    "rsync",
                    "-a",  # archive mode
                    "--delete",  # delete files in dest not in source
                    f"{source}/",
                    f"{dest}/",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"rsync sync failed: {e.stderr}")
            raise RuntimeError(f"Failed to sync snapshots: {e.stderr}")

    def _get_dir_size(self, path: Path) -> int:
        """Calculate total size of a directory in bytes."""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except (PermissionError, OSError) as e:
            logger.warning(f"Error calculating size for {path}: {e}")
        return total

    def list_files(
        self, set_name: str, snapshot: str = "C", path: str = "/"
    ) -> List[Dict[str, any]]:
        """List files in a snapshot directory.
        
        Args:
            set_name: Backup set name
            snapshot: "C" or "O"
            path: Relative path within the snapshot
            
        Returns:
            List of file/directory info dicts
        """
        snapshot_path = self.get_snapshot_path(set_name, snapshot)
        if not snapshot_path.exists():
            return []
        
        # Construct the full path
        target_path = snapshot_path / path.lstrip("/")
        if not target_path.exists():
            return []
        
        if not target_path.is_dir():
            # Return info about the single file
            stat = target_path.stat()
            return [{
                "name": target_path.name,
                "path": str(target_path.relative_to(snapshot_path)),
                "type": "file",
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }]
        
        # List directory contents
        files = []
        try:
            for entry in sorted(target_path.iterdir(), key=lambda x: x.name):
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "path": str(entry.relative_to(snapshot_path)),
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else 0,
                    "mtime": stat.st_mtime,
                })
        except PermissionError:
            logger.warning(f"Permission denied listing {target_path}")
        
        return files
