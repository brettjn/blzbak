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
import yaml
import json
import gzip
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
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
        
        # Write backup started metadata and append to backup.log now that
        # the server has finished preparation and is ready to receive the
        # client's rsync into the C snapshot. Also create a set.log entry
        # (newest entries are at the top).
        try:
            started_iso = datetime.now(timezone.utc).isoformat()
            c_path.mkdir(parents=True, exist_ok=True)
            self._write_backup_started_metadata(set_name, started_iso)
            self._append_backup_log(set_name, f"Backup started: {started_iso}")
            # add the set.log entry (new backup started)
            self._create_set_log_entry_on_prepare(set_name, started_iso)
        except Exception as e:
            logger.warning(f"Failed to write backup started metadata for '{set_name}': {e}")

        return result

    def _create_diff(self, set_name: str, c_path: Path, o_path: Path) -> Path:
        """Create a diff archive between C and O snapshots.
        
        Archives all files from O that differ from C (or don't exist in C).
        This preserves the old state before O is overwritten by C.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        diff_dir = self.get_diff_dir(set_name)
        diff_archive = diff_dir / f"diff_{timestamp}.patch.gz"

        # Use unified recursive diff to create a patch from O -> C
        # `diff -ruN O/ C/` returns 0 if identical, 1 if differences, >1 on error
        diff_cmd = [
            "diff",
            "-ruN",
            f"{o_path}",
            f"{c_path}",
        ]
        try:
            result = subprocess.run(
                diff_cmd,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                logger.info("No differences found - O already matches C")
                # create small marker gzip file to record no changes
                diff_dir.mkdir(parents=True, exist_ok=True)
                with gzip.open(diff_archive, "wt", encoding="utf-8") as gz:
                    gz.write(f"# No changes at {timestamp}\n")
                return diff_archive

            if result.returncode > 1:
                logger.error(f"diff failed: {result.stderr}")
                raise RuntimeError(f"Failed to create diff: {result.stderr}")

            # result.returncode == 1 -> diffs present
            diff_dir.mkdir(parents=True, exist_ok=True)
            with gzip.open(diff_archive, "wt", encoding="utf-8") as gz:
                gz.write(result.stdout)

            logger.info(f"Patch archive created: {diff_archive}")
            # Update set.log to reflect the diff for the previous backup
            try:
                self._update_set_log_for_diff(set_name, diff_archive)
            except Exception:
                pass
            return diff_archive

        except OSError as e:
            logger.error(f"Failed to run diff: {e}")
            raise RuntimeError(f"Failed to create diff: {e}")

    def _load_set_log(self, set_name: str) -> List[Dict[str, any]]:
        """Load the set.log entries as a list of dicts (newest first)."""
        set_path = self.get_set_path(set_name)
        log_path = set_path / "set.log"
        entries: List[Dict[str, any]] = []
        if not log_path.exists():
            return entries
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    # try to ignore malformed lines
                    continue
        return entries

    def _write_set_log(self, set_name: str, entries: List[Dict[str, any]]) -> None:
        set_path = self.get_set_path(set_name)
        log_path = set_path / "set.log"
        set_path.mkdir(parents=True, exist_ok=True)
        # Write newest first
        with open(log_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _create_set_log_entry_on_prepare(self, set_name: str, started_iso: str) -> None:
        """Create a new set.log entry at prepare time (backup started).

        New entries are prepended (newest first). The new entry contains
        number, started_at, finished_at (None), location_type='C', location='C/'.
        """
        entries = self._load_set_log(set_name)
        maxnum = 0
        for e in entries:
            try:
                if isinstance(e.get("number"), int) and e["number"] > maxnum:
                    maxnum = e["number"]
            except Exception:
                continue
        newnum = maxnum + 1
        new_entry = {
            "number": newnum,
            "started_at": started_iso,
            "finished_at": None,
            "location_type": "C",
        }
        # Prepend
        entries.insert(0, new_entry)
        self._write_set_log(set_name, entries)

    def _update_set_log_for_diff(self, set_name: str, diff_path: Path) -> None:
        """Update the previous backup entry to record the diff archive and
        mark the previous C as now being O.
        """
        entries = self._load_set_log(set_name)
        if len(entries) < 2:
            # no previous entry to update
            return
        # previous entry is at index 1 (newest first)
        prev = entries[1]
        prev["diff_path"] = str(diff_path)
        prev["location_type"] = "diff"
        entries[1] = prev
        self._write_set_log(set_name, entries)

    def _finalize_set_log_entry(self, set_name: str, finished_iso: str) -> None:
        """Finalize the current (newest) set.log entry with finished time and
        ensure older entries are updated to O as needed.
        """
        entries = self._load_set_log(set_name)
        if not entries:
            return
        entries[0]["finished_at"] = finished_iso
        entries[0]["location_type"] = "C"
        # Ensure second entry reflects O
        if len(entries) >= 2:
            entries[1]["location_type"] = "O"
        self._write_set_log(set_name, entries)

    def _append_backup_log(self, set_name: str, message: str) -> None:
        """Append a timestamped message to the per-set backup.log file."""
        try:
            set_path = self.get_set_path(set_name)
            log_path = set_path / "backup.log"
            ts = datetime.now(timezone.utc).isoformat()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(f"{ts} - {message}\n")
        except Exception as e:
            logger.warning(f"Failed to append to backup.log for '{set_name}': {e}")

    def _write_backup_started_metadata(self, set_name: str, started_iso: str) -> None:
        """Write a .blzbak-metadata file into the C snapshot root with started timestamp."""
        try:
            c_path = self.get_snapshot_path(set_name, "C")
            c_path.mkdir(parents=True, exist_ok=True)
            meta_path = c_path / ".blzbak-metadata"
            metadata = {
                "set_name": set_name,
                "started_at": started_iso,
                "finished_at": None,
            }
            with open(meta_path, "w") as f:
                yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.warning(f"Failed to write .blzbak-metadata start for '{set_name}': {e}")

    def mark_backup_complete(self, set_name: str, finished_iso: str = None) -> Dict[str, any]:
        """Mark the backup as finished: update .blzbak-metadata and append to backup.log.

        Returns the updated metadata dict.
        """
        try:
            if finished_iso is None:
                finished_iso = datetime.now(timezone.utc).isoformat()
            c_path = self.get_snapshot_path(set_name, "C")
            meta_path = c_path / ".blzbak-metadata"
            metadata = {"set_name": set_name, "started_at": None, "finished_at": finished_iso}
            if meta_path.exists():
                try:
                    with open(meta_path, "r") as f:
                        existing = yaml.safe_load(f) or {}
                    metadata.update(existing)
                except Exception:
                    pass
            metadata["finished_at"] = finished_iso
            with open(meta_path, "w") as f:
                yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)

            # Append to backup.log
            self._append_backup_log(set_name, f"Backup finished: {finished_iso}")
            # Finalize set.log entry
            try:
                self._finalize_set_log_entry(set_name, finished_iso)
            except Exception:
                pass
            return metadata
        except Exception as e:
            logger.warning(f"Failed to mark backup complete for '{set_name}': {e}")
            raise
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
            # Append creation event to backup.log
            try:
                self._append_backup_log(set_name, f"Set created: {result['set_path']}")
            except Exception:
                pass

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

    def compare_files_across_backups(
        self, set_name: str, folder_path: str, local_metadata: Dict[str, Any], source_path: str = None
    ) -> List[Dict[str, Any]]:
        """Compare local file metadata against backup history.
        
        Args:
            set_name: Backup set name
            folder_path: Relative path within backup set
            local_metadata: Dict of {relative_path: metadata}
            
        Returns:
            List of difference entries with backup numbers
        """
        differences = []
        
        # Load set.log to get backup numbers
        entries = self._load_set_log(set_name)
        if not entries:
            logger.warning(f"No set.log entries found for '{set_name}'")
            return differences
        
        # Build backup number map: {snapshot_type: backup_number}
        # Most recent entry is at index 0
        current_backup_num = entries[0].get("number", 1) if entries else 1
        previous_backup_num = entries[1].get("number", 0) if len(entries) > 1 else 0
        
        c_path = self.get_snapshot_path(set_name, "C")
        o_path = self.get_snapshot_path(set_name, "O")
        
        # 1. Compare local metadata against C
        if c_path.exists():
            # Determine candidate folder mapping using provided source_path
            mapped_folder = folder_path
            # If client provided the absolute source path, try mapping into snapshot
            try:
                if source_path:
                    # Common case: snapshot contains the basename of the source path
                    sp_name = Path(source_path).name
                    # If folder_path is '.' or empty, map to snapshot/<basename>
                    if folder_path in ("", "."):
                        candidate = c_path / sp_name
                    else:
                        candidate = c_path / sp_name / folder_path.lstrip("/")
                    if candidate.exists():
                        # Use mapping where files actually reside in snapshot
                        mapped_folder = str(Path(sp_name) / Path(folder_path)) if folder_path not in ("", ".") else sp_name
                        logger.debug(f"Mapped client folder '{folder_path}' with source '{source_path}' to snapshot path '{mapped_folder}'")
                        c_diffs = self._compare_against_snapshot(
                            mapped_folder, local_metadata, c_path, current_backup_num, "current"
                        )
                        differences.extend(c_diffs)
                    else:
                        # Fall back to direct folder_path
                        c_diffs = self._compare_against_snapshot(
                            folder_path, local_metadata, c_path, current_backup_num, "current"
                        )
                        differences.extend(c_diffs)
                else:
                    c_diffs = self._compare_against_snapshot(
                        folder_path, local_metadata, c_path, current_backup_num, "current"
                    )
                    differences.extend(c_diffs)
            except Exception as e:
                logger.debug(f"Error mapping source_path for comparison: {e}")
                c_diffs = self._compare_against_snapshot(
                    folder_path, local_metadata, c_path, current_backup_num, "current"
                )
                differences.extend(c_diffs)
        
        # 2. Compare C against O
        if o_path.exists() and c_path.exists() and previous_backup_num:
            o_diffs = self._compare_snapshots(
                folder_path, c_path, o_path, previous_backup_num, "previous"
            )
            differences.extend(o_diffs)
        
        # 3. Parse patch files in reverse chronological order
        diff_dir = self.get_diff_dir(set_name)
        if diff_dir.exists():
            # Get all patch files sorted by timestamp (newest first)
            patch_files = sorted(
                diff_dir.glob("diff_*.patch.gz"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # Match patch files with backup numbers from set.log
            for idx, entry in enumerate(entries):
                diff_path = entry.get("diff_path")
                if diff_path and Path(diff_path).exists():
                    backup_num = entry.get("number", 0)
                    patch_diffs = self._parse_patch_for_folder(
                        folder_path, Path(diff_path), backup_num
                    )
                    differences.extend(patch_diffs)
        
        return differences
    
    def _compare_against_snapshot(
        self,
        folder_path: str,
        local_metadata: Dict[str, Any],
        snapshot_path: Path,
        backup_num: int,
        label: str,
    ) -> List[Dict[str, Any]]:
        """Compare local files against a snapshot."""
        differences = []
        snapshot_folder = snapshot_path / folder_path.lstrip("/")
        
        if not snapshot_folder.exists():
            # Attempt to locate the folder within the snapshot in case layout differs.
            # e.g., client sent a relative path that may be nested differently in C/.
            try:
                target_suffix = folder_path.lstrip("/")
                found = None
                for candidate in snapshot_path.rglob("*"):
                    if candidate.is_dir():
                        try:
                            rel = str(candidate.relative_to(snapshot_path))
                        except Exception:
                            rel = None
                        if rel and rel.endswith(target_suffix):
                            found = candidate
                            break
                if found:
                    logger.debug(f"Located snapshot folder for '{folder_path}' at '{found}'")
                    snapshot_folder = found
            except Exception as e:
                logger.debug(f"Error while searching snapshot for '{folder_path}': {e}")

        # After attempting to find it, if the folder still doesn't exist,
        # treat all local entries as new.
        if not snapshot_folder.exists():
            for rel_path, local_meta in local_metadata.items():
                differences.append({
                    "backup_number": backup_num,
                    "path": rel_path,
                    "status": f"new (not in {label} backup)",
                    "changes": {},
                    "after_meta": local_meta,
                })
            return differences
        
        # Check each local file against snapshot
        for rel_path, local_meta in local_metadata.items():
            snapshot_file = snapshot_folder / rel_path
            
            if not snapshot_file.exists():
                differences.append({
                    "backup_number": backup_num,
                    "path": rel_path,
                    "status": f"new (not in {label} backup)",
                    "changes": {},
                    "after_meta": local_meta,
                })
                continue
            
            # Compare metadata
            changes = {}
            try:
                snap_stat = snapshot_file.stat()
                
                # Compare size
                if local_meta.get("size") != snap_stat.st_size:
                    changes["size"] = {
                        "before": snap_stat.st_size,
                        "after": local_meta.get("size"),
                    }
                
                # Compare mtime
                if abs(local_meta.get("mtime", 0) - snap_stat.st_mtime) > 1:
                    from datetime import datetime, timezone
                    changes["modified_time"] = {
                        "before": datetime.fromtimestamp(snap_stat.st_mtime, tz=timezone.utc).isoformat(),
                        "after": datetime.fromtimestamp(local_meta.get("mtime", 0), tz=timezone.utc).isoformat(),
                    }
                
                # Compare type
                snap_is_dir = snapshot_file.is_dir()
                local_is_dir = local_meta.get("type") == "dir"
                if snap_is_dir != local_is_dir:
                    changes["type"] = {
                        "before": "dir" if snap_is_dir else "file",
                        "after": local_meta.get("type"),
                    }
                
                # Compare sha256 for files
                if not local_is_dir and "sha256" in local_meta:
                    snap_sha = self._calculate_sha256(snapshot_file)
                    if snap_sha and snap_sha != local_meta["sha256"]:
                        changes["data"] = {"message": "file content differs"}
                
                if changes:
                    # Include metadata snapshots for before/after where possible
                    before_meta = {
                        "type": "dir" if snapshot_file.is_dir() else "file",
                        "size": snap_stat.st_size,
                        "mtime": snap_stat.st_mtime,
                        "mode": snap_stat.st_mode,
                        "uid": snap_stat.st_uid,
                        "gid": snap_stat.st_gid,
                    }

                    differences.append({
                        "backup_number": backup_num,
                        "path": rel_path,
                        "status": "modified",
                        "changes": changes,
                        "before_meta": before_meta,
                        "after_meta": local_meta,
                    })
            except (PermissionError, OSError) as e:
                logger.debug(f"Error comparing {rel_path}: {e}")
        
        # Check for files in snapshot not in local
        if snapshot_folder.is_dir():
            try:
                for snap_item in snapshot_folder.rglob("*"):
                    rel_path = str(snap_item.relative_to(snapshot_folder))
                    if rel_path not in local_metadata:
                        # Capture snapshot metadata for deleted items
                        try:
                            s_stat = snap_item.stat()
                            before_meta = {
                                "type": "dir" if snap_item.is_dir() else "file",
                                "size": s_stat.st_size,
                                "mtime": s_stat.st_mtime,
                                "mode": s_stat.st_mode,
                                "uid": s_stat.st_uid,
                                "gid": s_stat.st_gid,
                            }
                        except Exception:
                            before_meta = None

                        differences.append({
                            "backup_number": backup_num,
                            "path": rel_path,
                            "status": f"deleted (exists in {label} backup)",
                            "changes": {},
                            "before_meta": before_meta,
                        })
            except (PermissionError, OSError) as e:
                logger.debug(f"Error scanning snapshot: {e}")
        
        return differences
    
    def _compare_snapshots(
        self,
        folder_path: str,
        c_path: Path,
        o_path: Path,
        backup_num: int,
        label: str,
    ) -> List[Dict[str, Any]]:
        """Compare two snapshots to find differences."""
        differences = []
        c_folder = c_path / folder_path.lstrip("/")
        o_folder = o_path / folder_path.lstrip("/")
        
        if not o_folder.exists():
            return differences
        
        if not c_folder.exists():
            # Folder was deleted
            differences.append({
                "backup_number": backup_num,
                "path": folder_path,
                "status": f"folder deleted (existed in {label} backup)",
                "changes": {},
            })
            return differences
        
        # Compare files in O against C
        try:
            for o_item in o_folder.rglob("*"):
                rel_path = str(o_item.relative_to(o_folder))
                c_item = c_folder / rel_path
                
                if not c_item.exists():
                    differences.append({
                        "backup_number": backup_num,
                        "path": rel_path,
                        "status": f"deleted between backups #{backup_num} and #{backup_num+1}",
                        "changes": {},
                    })
                    continue
                
                # Compare metadata
                changes = {}
                o_stat = o_item.stat()
                c_stat = c_item.stat()
                
                if o_stat.st_size != c_stat.st_size:
                    changes["size"] = {
                        "before": o_stat.st_size,
                        "after": c_stat.st_size,
                    }
                
                if o_item.is_file() and c_item.is_file():
                    o_sha = self._calculate_sha256(o_item)
                    c_sha = self._calculate_sha256(c_item)
                    if o_sha and c_sha and o_sha != c_sha:
                        changes["data"] = {"message": "file content differs"}
                
                if changes:
                    differences.append({
                        "backup_number": backup_num,
                        "path": rel_path,
                        "status": "modified",
                        "changes": changes,
                    })
        except (PermissionError, OSError) as e:
            logger.debug(f"Error comparing snapshots: {e}")
        
        return differences
    
    def _parse_patch_for_folder(
        self, folder_path: str, patch_file: Path, backup_num: int
    ) -> List[Dict[str, Any]]:
        """Parse a patch file to find changes in the specified folder."""
        differences = []
        
        try:
            import gzip
            import re
            
            with gzip.open(patch_file, "rt", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            # Parse unified diff format
            # Look for lines like: diff -ruN /path/O/file /path/C/file
            diff_pattern = re.compile(r"^diff -ruN (.+?) (.+?)$", re.MULTILINE)
            
            for match in diff_pattern.finditer(content):
                o_file = match.group(1)
                c_file = match.group(2)
                
                # Extract relative path (remove snapshot prefix)
                # Paths in diff look like: /blzbak/setname/O/folder/file
                for path_str in [o_file, c_file]:
                    if "/O/" in path_str:
                        rel_path = path_str.split("/O/", 1)[1]
                    elif "/C/" in path_str:
                        rel_path = path_str.split("/C/", 1)[1]
                    else:
                        continue
                    
                    # Check if this file is within our target folder
                    if rel_path.startswith(folder_path.lstrip("/")):
                        # Extract just the portion within the folder
                        folder_rel = rel_path[len(folder_path.lstrip("/")):].lstrip("/")
                        if folder_rel:
                            differences.append({
                                "backup_number": backup_num,
                                "path": folder_rel,
                                "status": "changed in diff",
                                "changes": {"data": {"message": "file modified"}},
                            })
                            break  # Only add once per file
        
        except Exception as e:
            logger.warning(f"Error parsing patch {patch_file}: {e}")
        
        return differences
    
    def _calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        try:
            sha = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    sha.update(chunk)
            return sha.hexdigest()
        except (PermissionError, OSError) as e:
            logger.debug(f"Cannot hash {file_path}: {e}")
            return ""

