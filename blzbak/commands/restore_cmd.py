"""CLI commands: restore file / folder / set.

Restore uses rsync --relative with the /./ path trick so that the original
directory structure is always preserved, regardless of whether the user
restores to the original location (dest_root='/') or an alternate base path.

    Source:  backup@server:/blzbak/docs/C/./home/alice/report.pdf
    dest='/': restores to  /home/alice/report.pdf          (original)
    dest='/mnt/recover/': restores to  /mnt/recover/home/alice/report.pdf
"""

import sys

from ..backup import load_backup_set
from ..client import DaemonClient, DaemonError
from ..rsync import build_restore_cmd, run_rsync


def _resolve_dest(args) -> str:
    """Return the restore destination root (empty string = original location)."""
    dest = getattr(args, "dest", None)
    if dest:
        return dest
    if getattr(args, "yes", False):
        return ""   # original location, no prompt

    try:
        answer = input(
            "Restore destination "
            "(press Enter for original location, or enter an alternate base path): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)
    return answer


def _do_restore(remote_source: str, dest: str, args) -> int:
    cmd = build_restore_cmd(
        remote_source = remote_source,
        dest_root     = dest if dest else "/",
        dry_run       = getattr(args, "dry_run", False),
        verbose       = getattr(args, "verbose", False),
    )
    return run_rsync(cmd)


def cmd_restore_file(args, config: dict, client: DaemonClient) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1

    snapshot      = getattr(args, "snapshot", "C")
    dest          = _resolve_dest(args)
    remote_base   = bs.server.rsync_dest(snapshot)
    file_path     = args.file.lstrip("/")
    remote_source = f"{remote_base}/./{file_path}"

    rc = _do_restore(remote_source, dest, args)
    if rc == 0:
        print("[blzbak] File restored successfully.")
    else:
        print(f"[blzbak] Restore failed (rsync exit code {rc}).", file=sys.stderr)
    return rc


def cmd_restore_folder(args, config: dict, client: DaemonClient) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1

    snapshot      = getattr(args, "snapshot", "C")
    dest          = _resolve_dest(args)
    remote_base   = bs.server.rsync_dest(snapshot)
    folder_path   = args.folder.strip("/") + "/"
    remote_source = f"{remote_base}/./{folder_path}"

    rc = _do_restore(remote_source, dest, args)
    if rc == 0:
        print("[blzbak] Folder restored successfully.")
    else:
        print(f"[blzbak] Restore failed (rsync exit code {rc}).", file=sys.stderr)
    return rc


def cmd_restore_set(args, config: dict, client: DaemonClient) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1

    snapshot      = getattr(args, "snapshot", "C")
    dest          = _resolve_dest(args)
    remote_base   = bs.server.rsync_dest(snapshot)
    # Trailing slash restores contents; /./ root preserves path structure
    remote_source = f"{remote_base}/./"

    rc = _do_restore(remote_source, dest, args)
    if rc == 0:
        print("[blzbak] Backup set restored successfully.")
    else:
        print(f"[blzbak] Restore failed (rsync exit code {rc}).", file=sys.stderr)
    return rc
