"""CLI command: files - show file/folder differences across backups."""

import os
import sys
import hashlib
from pathlib import Path
from typing import Dict, Any, List

from ..client import DaemonClient, DaemonError
from ..backup import load_backup_set


def _get_file_metadata(path: Path) -> Dict[str, Any]:
    """Gather metadata for a file or directory entry."""
    try:
        stat = path.stat()
        metadata = {
            "name": path.name,
            "type": "dir" if path.is_dir() else "file",
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "mode": stat.st_mode,
            "uid": stat.st_uid,
            "gid": stat.st_gid,
        }
        
        # Calculate sha256 for files
        if path.is_file() and stat.st_size > 0:
            try:
                sha = hashlib.sha256()
                with open(path, "rb") as f:
                    while chunk := f.read(8192):
                        sha.update(chunk)
                metadata["sha256"] = sha.hexdigest()
            except (PermissionError, OSError) as e:
                metadata["sha256_error"] = str(e)
        
        return metadata
    except (PermissionError, OSError) as e:
        return {
            "name": path.name,
            "error": str(e),
        }


def _gather_folder_metadata(folder_path: Path) -> Dict[str, Any]:
    """Recursively gather metadata for all files in a folder."""
    entries = {}
    
    if not folder_path.exists():
        return entries
    
    if not folder_path.is_dir():
        # Single file
        rel_path = folder_path.name
        entries[rel_path] = _get_file_metadata(folder_path)
        return entries
    
    # Recursively walk the directory
    try:
        for root, dirs, files in os.walk(folder_path):
            root_path = Path(root)
            rel_root = root_path.relative_to(folder_path)
            
            # Add directory entries
            for d in sorted(dirs):
                dir_path = root_path / d
                rel_path = str(rel_root / d) if str(rel_root) != "." else d
                entries[rel_path] = _get_file_metadata(dir_path)
            
            # Add file entries
            for f in sorted(files):
                file_path = root_path / f
                rel_path = str(rel_root / f) if str(rel_root) != "." else f
                entries[rel_path] = _get_file_metadata(file_path)
    except (PermissionError, OSError) as e:
        print(f"Warning: Error scanning {folder_path}: {e}", file=sys.stderr)
    
    return entries


def _format_diff_entry(entry: Dict[str, Any]) -> str:
    """Format a single diff entry for display."""
    lines = []
    backup_num = entry.get("backup_number")
    path = entry.get("path", "")
    status = entry.get("status", "")
    
    header = f"[Backup #{backup_num}] {path}"
    if status:
        header += f" ({status})"
    lines.append(header)
    
    changes = entry.get("changes", {})
    if changes:
        for key, change in changes.items():
            before = change.get("before")
            after = change.get("after")
            if before is not None and after is not None:
                lines.append(f"  {key}: {before} -> {after}")
            elif "message" in change:
                lines.append(f"  {key}: {change['message']}")
            else:
                lines.append(f"  {key}: {change}")
    
    return "\n".join(lines)


def cmd_files(args, config: dict, client: DaemonClient) -> int:
    """Show file/folder differences across backups."""
    set_name = args.name
    folder = args.folder
    
    # Load backup set to get source paths
    bs = load_backup_set(set_name, config)
    if not bs:
        print(f"Error: backup set '{set_name}' not found.", file=sys.stderr)
        return 1
    
    # Expand folder path - try to find it within source paths
    folder_path = Path(folder).expanduser().resolve()
    
    # Check if folder is within any source path
    found_source = None
    for source in bs.source_paths:
        source_path = Path(source).expanduser().resolve()
        try:
            rel = folder_path.relative_to(source_path)
            found_source = source_path
            break
        except ValueError:
            continue
    
    if not found_source:
        # Try as absolute path
        if not folder_path.exists():
            print(f"Error: folder '{folder}' not found and not within any source paths", file=sys.stderr)
            print(f"Source paths: {', '.join(bs.source_paths)}", file=sys.stderr)
            return 1
        found_source = folder_path.parent
    
    # Gather local file metadata
    print(f"Scanning local folder: {folder_path}")
    local_metadata = _gather_folder_metadata(folder_path)
    
    if not local_metadata:
        print(f"No files found in {folder_path}")
        return 0
    
    print(f"Found {len(local_metadata)} entries, comparing with backups...")
    
    # Send request to server
    try:
        # Calculate relative path within the backup set
        try:
            rel_folder = str(folder_path.relative_to(found_source))
        except ValueError:
            rel_folder = str(folder_path)
        
        response = client.files_diff(set_name, rel_folder, local_metadata)
        
        differences = response.get("differences", [])
        
        if not differences:
            print(f"\nNo differences found across backups for '{folder}'")
            return 0
        
        print(f"\nFound {len(differences)} differences:\n")
        
        # Group by backup number for cleaner display
        by_backup = {}
        for diff in differences:
            backup_num = diff.get("backup_number", 0)
            if backup_num not in by_backup:
                by_backup[backup_num] = []
            by_backup[backup_num].append(diff)
        
        # Display in order (most recent first)
        for backup_num in sorted(by_backup.keys(), reverse=True):
            print(f"=== Backup #{backup_num} ===")
            for diff in by_backup[backup_num]:
                print(_format_diff_entry(diff))
                print()
        
        return 0
        
    except DaemonError as e:
        print(f"Error from daemon: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
