"""Storage management for blzbakd — handles backup directories and operations.

Directory structure on the server:
    /blzbak/                    (base_path)
        <set_name>/
            C/                  (current backup)
            O/                  (once-removed backup)
            diffs/              (diff archives)
                <timestamp>.tar.gz
            metadata.yaml       (backup set metadata)
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

    def __init__(self, base_path: str, config=None):
        self.base_path = Path(base_path)
        self.config = config  # Store config for test command
        self.base_path.mkdir(parents=True, exist_ok=True)

    def get_set_path(self, set_name: str) -> Path:
        """Get the base directory for a backup set."""
        return self.base_path / set_name

    def get_snapshot_path(self, set_name: str, label: str) -> Path:
        """Get the path for a specific snapshot (C or O)."""
        return self.get_set_path(set_name) / label

    def get_diff_dir(self, set_name: str) -> Path:
        """Get the diff directory for a backup set.
        
        Diffs are stored within the backup set's directory:
        /blzbak/<set_name>/diffs/
        """
        diff_path = self.get_set_path(set_name) / "diffs"
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
        2. If both exist and O has content, create a diff between C and O
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
        
        # If both C and O exist, check if O has content before creating diff
        if c_path.exists() and o_path.exists():
            # Only create diff if O actually has files (not empty)
            o_has_content = self._dir_has_content(o_path)
            
            if o_has_content:
                logger.info(f"Creating diff between C and O for set '{set_name}'")
                try:
                    diff_path = self._create_diff(set_name, c_path, o_path)
                    result["diff_created"] = True
                    result["diff_path"] = str(diff_path)
                    logger.info(f"Diff created: {diff_path}")
                except Exception as e:
                    logger.error(f"Failed to create diff: {e}")
                    raise
            else:
                logger.info(f"Skipping diff creation - O is empty (first backup already completed)")
            
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
        
        Archives all files from O that differ from C (or don't exist in C).
        This preserves the old state before O is overwritten by C.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        diff_dir = self.get_diff_dir(set_name)
        diff_archive = diff_dir / f"diff_{timestamp}.tar.gz"
        
        # Use rsync to find files in O that differ from C
        # rsync -an --delete O/ C/ shows what would be transferred from O to C
        # These are files we need to preserve from O before overwriting it
        try:
            result = subprocess.run(
                [
                    "rsync",
                    "-an",  # archive mode, dry-run
                    "--delete",
                    "--out-format=%n",
                    f"{o_path}/",
                    f"{c_path}/",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            
            # All files listed (including ones marked for deletion) need to be saved from O
            changed_files = [
                line.strip() for line in result.stdout.splitlines()
                if line.strip() and not line.startswith("deleting ")
            ]
            
            if not changed_files:
                logger.info("No differences found - O already matches C")
                # Create an empty marker file
                diff_archive.write_text(f"No changes at {timestamp}")
                return diff_archive
            
            logger.info(f"Found {len(changed_files)} files to preserve from O")
            
            # Create tar archive of changed files from O
            # We save the old versions from O before syncing C→O
            with subprocess.Popen(
                ["tar", "-czf", str(diff_archive), "-C", str(o_path)]
                + changed_files,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as proc:
                stdout, stderr = proc.communicate()
                if proc.returncode != 0:
                    # Log any errors but don't fail - some files might have been deleted
                    logger.debug(f"tar stderr: {stderr.decode()}")
            
            logger.info(f"Diff archive created: {diff_archive}")
            return diff_archive
            
        except subprocess.CalledProcessError as e:
            logger.error(f"rsync diff failed: {e.stderr}")
            raise RuntimeError(f"Failed to create diff: {e.stderr}")
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

    def _dir_has_content(self, path: Path) -> bool:
        """Check if a directory contains any files or subdirectories.
        
        Returns:
            True if directory contains at least one item, False if empty
        """
        try:
            # Use iterator - stops at first item found (efficient for large dirs)
            return any(path.iterdir())
        except (PermissionError, OSError) as e:
            logger.warning(f"Error checking if directory has content: {e}")
            return False

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

    def create_set(self, set_name: str, metadata: dict) -> Dict[str, any]:
        """Create a new backup set with directory structure and metadata.
        
        Creates:
        - Set base directory
        - C (current) snapshot directory
        - O (once-removed) snapshot directory
        - metadata.yaml file with backup set configuration
        
        Args:
            set_name: Name of the backup set
            metadata: Dictionary containing backup set configuration
            
        Returns:
            Dict with details about created items
            
        Raises:
            FileExistsError: If the backup set already exists
            RuntimeError: If creation fails
        """
        import yaml
        from datetime import datetime, timezone
        
        set_path = self.get_set_path(set_name)
        
        if set_path.exists():
            raise FileExistsError(f"Backup set '{set_name}' already exists")
        
        result = {
            "set_name": set_name,
            "set_path": str(set_path),
            "created_items": [],
        }
        
        try:
            # Create set directory
            set_path.mkdir(parents=True, exist_ok=False)
            result["created_items"].append(f"Set directory: {set_path}")
            logger.info(f"Created set directory: {set_path}")
            
            # Create C snapshot directory
            c_path = self.get_snapshot_path(set_name, "C")
            c_path.mkdir(parents=True, exist_ok=False)
            result["created_items"].append(f"C snapshot directory: {c_path}")
            logger.info(f"Created C snapshot directory: {c_path}")
            
            # Create O snapshot directory
            o_path = self.get_snapshot_path(set_name, "O")
            o_path.mkdir(parents=True, exist_ok=False)
            result["created_items"].append(f"O snapshot directory: {o_path}")
            logger.info(f"Created O snapshot directory: {o_path}")
            
            # Create metadata.yaml
            metadata_path = set_path / "metadata.yaml"
            metadata_content = {
                "name": set_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **metadata,  # Include all metadata from client
            }
            
            with open(metadata_path, "w") as f:
                yaml.dump(metadata_content, f, default_flow_style=False, sort_keys=False)
            
            result["created_items"].append(f"Metadata file: {metadata_path}")
            result["metadata_path"] = str(metadata_path)
            logger.info(f"Created metadata file: {metadata_path}")
            
            return result
            
        except Exception as e:
            # Clean up on failure
            logger.error(f"Failed to create backup set '{set_name}': {e}")
            if set_path.exists():
                import shutil
                try:
                    shutil.rmtree(set_path)
                    logger.info(f"Cleaned up partial creation: {set_path}")
                except Exception as cleanup_err:
                    logger.error(f"Failed to clean up after error: {cleanup_err}")
            raise RuntimeError(f"Failed to create backup set: {e}") from e

    def delete_set(self, set_name: str) -> Dict[str, any]:
        """Delete a backup set and all associated data.
        
        Removes:
        - C and O snapshot directories and all their contents
        - All diff archives for this set
        - The set's base directory
        
        Args:
            set_name: Name of the backup set to delete
            
        Returns:
            Dict with details about what was deleted
            
        Raises:
            FileNotFoundError: If the backup set doesn't exist
            RuntimeError: If deletion fails
        """
        import shutil
        
        set_path = self.get_set_path(set_name)
        diff_path = self.get_diff_dir(set_name)
        
        if not set_path.exists():
            raise FileNotFoundError(f"Backup set '{set_name}' does not exist")
        
        result = {
            "set_name": set_name,
            "deleted_items": [],
            "errors": [],
        }
        
        # Delete C snapshot
        c_path = self.get_snapshot_path(set_name, "C")
        if c_path.exists():
            try:
                shutil.rmtree(c_path)
                result["deleted_items"].append(f"C snapshot: {c_path}")
                logger.info(f"Deleted C snapshot: {c_path}")
            except Exception as e:
                error_msg = f"Failed to delete C snapshot: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)
        
        # Delete O snapshot
        o_path = self.get_snapshot_path(set_name, "O")
        if o_path.exists():
            try:
                shutil.rmtree(o_path)
                result["deleted_items"].append(f"O snapshot: {o_path}")
                logger.info(f"Deleted O snapshot: {o_path}")
            except Exception as e:
                error_msg = f"Failed to delete O snapshot: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)
        
        # Delete diff archives
        if diff_path.exists():
            try:
                diff_count = len(list(diff_path.glob("*.tar.gz")))
                shutil.rmtree(diff_path)
                result["deleted_items"].append(f"Diff archives: {diff_path} ({diff_count} files)")
                logger.info(f"Deleted diff directory: {diff_path}")
            except Exception as e:
                error_msg = f"Failed to delete diff archives: {e}"
                result["errors"].append(error_msg)
                logger.error(error_msg)
        
        # Delete set directory (should be empty now, or may contain metadata.yaml)
        try:
            shutil.rmtree(set_path)
            result["deleted_items"].append(f"Set directory: {set_path}")
            logger.info(f"Deleted set directory: {set_path}")
        except Exception as e:
            error_msg = f"Failed to delete set directory: {e}"
            result["errors"].append(error_msg)
            logger.error(error_msg)
        
        if result["errors"]:
            raise RuntimeError(f"Partial deletion completed with {len(result['errors'])} error(s)")
        
        return result
