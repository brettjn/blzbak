"""CLI command: files - show file/folder differences across backups."""

import os
import sys
import hashlib
import stat
import pwd
import grp
from datetime import datetime
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
    
    # Header format: [<backup number>] path
    header = f"[{backup_num}] {path}"
    if status:
        header += f" ({status})"
    lines.append(header)
    # Try to show ls -l style metadata for the file as it existed in the
    # backup (before_meta) or as it exists locally (after_meta).
    def format_ls_long(meta: Dict[str, Any], name: str) -> str:
        try:
            mode = meta.get("mode", 0)
            perm = stat.filemode(mode)
        except Exception:
            perm = "?---------"

        nlink = meta.get("nlink", 1)
        uid = meta.get("uid")
        gid = meta.get("gid")
        try:
            owner = pwd.getpwuid(uid).pw_name if uid is not None else "?"
        except Exception:
            owner = str(uid) if uid is not None else "?"
        try:
            group = grp.getgrgid(gid).gr_name if gid is not None else "?"
        except Exception:
            group = str(gid) if gid is not None else "?"

        size = meta.get("size", 0)
        mtime = meta.get("mtime", 0)
        try:
            ts = datetime.fromtimestamp(mtime)
            mtime_str = ts.strftime("%b %d %H:%M")
        except Exception:
            mtime_str = "?"

        return f"  {perm} {nlink:3} {owner} {group} {size:8} {mtime_str} {name}"

    before_meta = entry.get("before_meta")
    after_meta = entry.get("after_meta")

    if before_meta:
        lines.append(format_ls_long(before_meta, path))
        # If there is also an after_meta, show it as the new version
        if after_meta:
            lines.append("   ->")
            lines.append(format_ls_long(after_meta, path))
    elif after_meta:
        # No snapshot metadata available; show local file metadata
        lines.append(format_ls_long(after_meta, path))
    else:
        # Fallback: show any change messages
        changes = entry.get("changes", {})
        if changes:
            for key, change in changes.items():
                if isinstance(change, dict) and "message" in change:
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
    
    # Expand to absolute path
    folder_path = Path(folder).expanduser().resolve()
    
    if not folder_path.exists():
        print(f"Error: folder '{folder}' does not exist.", file=sys.stderr)
        return 1
    
    # Find which source path contains this folder
    source_path = None
    rel_folder = None
    
    for source in bs.source_paths:
        source_abs = Path(source).expanduser().resolve()
        try:
            rel_folder = str(folder_path.relative_to(source_abs))
            source_path = source_abs
            break
        except ValueError:
            # folder_path is not relative to this source
            continue
    
    if source_path is None:
        print(f"Error: folder '{folder}' is not within any backup source paths:", file=sys.stderr)
        print(f"  Source paths: {', '.join(bs.source_paths)}", file=sys.stderr)
        return 1
    
    # Gather local file metadata
    print(f"Scanning local folder: {folder_path}")
    print(f"Relative path in backup: {rel_folder}")
    local_metadata = _gather_folder_metadata(folder_path)
    
    if not local_metadata:
        print(f"No files found in {folder_path}")
        return 0
    
    print(f"Found {len(local_metadata)} entries, comparing with backups...")
    
    # Send request to server with relative path
    try:
        response = client.files_diff(set_name, rel_folder, local_metadata)
        
        differences = response.get("differences", [])
        
        if not differences:
            print(f"\nNo differences found across backups for '{rel_folder}'")
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
