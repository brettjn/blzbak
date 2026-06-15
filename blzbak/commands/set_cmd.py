"""CLI commands: set list / create / show / delete / edit."""

import os
import subprocess
import sys

import yaml

from ..backup import list_backup_sets, load_backup_set, save_backup_set, delete_backup_set, get_set_path
from ..config import load_ignore_patterns
from ..models import BackupSet, ServerConfig, validate_set_name


def cmd_set_list(args, config: dict) -> int:
    sets = list_backup_sets(config)
    if not sets:
        print("No backup sets configured.")
        return 0
    fmt = "  {:<20}  {:<18}  {}"
    print(fmt.format("NAME", "SCHEDULE", "SOURCE PATHS"))
    print("  " + "-" * 72)
    for s in sets:
        sources = ", ".join(s.source_paths) if s.source_paths else "(none)"
        print(fmt.format(s.name, s.schedule, sources))
    return 0


def cmd_set_show(args, config: dict) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1
    print(yaml.dump(bs.to_dict(), default_flow_style=False, sort_keys=False), end="")
    return 0


def cmd_set_create(args, config: dict) -> int:
    try:
        validate_set_name(args.name)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if load_backup_set(args.name, config):
        print(f"Error: backup set '{args.name}' already exists.", file=sys.stderr)
        return 1

    srv      = config.get("server", {})
    bak_base = srv.get("backup_base", "/blzbak")
    server   = ServerConfig(
        host      = srv.get("host", ""),
        port      = int(srv.get("port", 7890)),
        ssh_user  = srv.get("ssh_user", ""),
        dest_path = f"{bak_base}/{args.name}",
    )

    # Snapshot the current ignore patterns into the set so future global
    # changes don't affect this set's behaviour.
    exclude_patterns = load_ignore_patterns()

    bs = BackupSet(
        name             = args.name,
        source_paths     = args.sources,
        server           = server,
        schedule         = args.schedule,
        exclude_patterns = exclude_patterns,
    )
    save_backup_set(bs, config)
    print(f"Backup set '{args.name}' created.")
    return 0


def cmd_set_delete(args, config: dict) -> int:
    if not delete_backup_set(args.name, config):
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1
    print(f"Backup set '{args.name}' deleted.")
    return 0


def cmd_set_edit(args, config: dict) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1
    set_file = get_set_path(args.name, config)
    editor   = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    result   = subprocess.run([editor, str(set_file)])
    return result.returncode
