"""CLI commands: backup run / list / list-files."""

import sys

from ..backup import load_backup_set
from ..client import DaemonClient, DaemonError
from ..rsync import build_backup_cmd, run_rsync


def cmd_backup_run(args, config: dict, client: DaemonClient) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1

    print(f"[blzbak] Preparing server for backup of '{args.name}'...")
    try:
        client.prepare_backup(args.name)
    except DaemonError as exc:
        print(f"Error: daemon rejected prepare_backup: {exc}", file=sys.stderr)
        return 1

    # Destination: user@host:/blzbak/<set>/C/
    dest = bs.server.rsync_dest("C") + "/"
    cmd  = build_backup_cmd(
        source_paths     = bs.source_paths,
        dest             = dest,
        exclude_patterns = bs.exclude_patterns,
        dry_run          = getattr(args, "dry_run", False),
        verbose          = getattr(args, "verbose", False),
    )
    print(f"[blzbak] Syncing to {dest}...")
    rc = run_rsync(cmd)
    if rc != 0:
        print(f"[blzbak] rsync failed with exit code {rc}.", file=sys.stderr)
        return rc

    try:
        client.backup_complete(args.name)
    except DaemonError as exc:
        print(f"[blzbak] Warning: backup_complete notification failed: {exc}", file=sys.stderr)

    print(f"[blzbak] Backup of '{args.name}' complete.")
    return 0


def cmd_backup_list(args, config: dict, client: DaemonClient) -> int:
    set_name = getattr(args, "name", None)
    if set_name:
        try:
            snapshots = client.list_snapshots(set_name)
        except DaemonError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if not snapshots:
            print(f"No snapshots found for '{set_name}'.")
            return 0
        fmt = "  {:<6}  {:<30}  {}"
        print(fmt.format("LABEL", "TIMESTAMP", "SIZE"))
        print("  " + "-" * 54)
        for snap in snapshots:
            size = _fmt_size(snap.get("size_bytes", 0))
            print(fmt.format(snap.get("label", "?"), snap.get("timestamp", "?"), size))
    else:
        try:
            sets = client.list_sets()
        except DaemonError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if not sets:
            print("No backup sets found on server.")
            return 0
        print("Backup sets on server:")
        for s in sets:
            print(f"  {s.get('name', '?')}")
    return 0


def cmd_backup_list_files(args, config: dict, client: DaemonClient) -> int:
    snapshot = getattr(args, "snapshot", "C")
    path     = getattr(args, "path", "/")
    try:
        files = client.list_files(args.name, snapshot, path)
    except DaemonError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not files:
        print(f"No files at '{path}' in snapshot '{snapshot}'.")
        return 0
    fmt = "  {:<1}  {:<12}  {:<22}  {}"
    print(fmt.format("T", "SIZE", "MODIFIED", "NAME"))
    print("  " + "-" * 56)
    for entry in files:
        ftype = "d" if entry.get("is_dir") else "-"
        size  = _fmt_size(entry.get("size", 0)) if not entry.get("is_dir") else ""
        name  = entry.get("name", "?") + ("/" if entry.get("is_dir") else "")
        mtime = entry.get("mtime", "")
        print(fmt.format(ftype, size, mtime, name))
    return 0


def _fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
