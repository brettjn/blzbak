"""CLI commands: set list / create / show / delete / edit."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

from ..backup import list_backup_sets, load_backup_set, save_backup_set, delete_backup_set, get_set_path
from ..config import load_ignore_patterns
from ..cron import install_cron_job, remove_cron_job, install_system_cron_job
from ..models import BackupSet, ServerConfig, validate_set_name


def cmd_set_list(args, config: dict) -> int:
    sets = list_backup_sets(config)
    if not sets:
        print("No backup sets configured.")
        return 0
    fmt = "  {:<20}  {:<18}  {:<22}  {}"
    print(fmt.format("NAME", "SCHEDULE", "SERVER", "SOURCE PATHS"))
    print("  " + "-" * 100)
    for s in sets:
        sources = ", ".join(s.source_paths) if s.source_paths else "(none)"
        srv = "(none)"
        if getattr(s, "server", None) and s.server.host:
            srv = f"{s.server.host}:{s.server.port}"
        print(fmt.format(s.name, s.schedule, srv, sources))
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
    
    # Automatically install cron job
    try:
        # If the user explicitly provided --schedule, prefer system-wide
        # installation in /etc/cron.d.  Fall back to per-user crontab on
        # permission errors or when system install isn't possible.
        explicit_schedule = any(
            a == "--schedule" or a.startswith("--schedule=") for a in sys.argv
        )
        if explicit_schedule:
            try:
                install_system_cron_job(args.name, args.schedule)
                print(f"System cron job installed: {args.schedule}")
            except Exception as exc:
                print(f"Warning: Failed to install system cron job: {exc}", file=sys.stderr)
                install_cron_job(args.name, args.schedule)
                print(f"Per-user cron job installed: {args.schedule}")
        else:
            install_cron_job(args.name, args.schedule)
            print(f"Cron job installed: {args.schedule}")
    except Exception as exc:
        print(f"Warning: Failed to install cron job: {exc}", file=sys.stderr)
        print("You can manually install it later with: blzbak cron install", file=sys.stderr)
    
    return 0


def cmd_set_delete(args, config: dict) -> int:
    if not delete_backup_set(args.name, config):
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1
    
    # Also remove the cron job
    try:
        if remove_cron_job(args.name):
            print(f"Cron job removed for '{args.name}'.")
    except Exception as exc:
        # If removal failed due to permissions on system /etc/cron.d file,
        # offer to remove it via sudo so the delete can proceed.
        cron_path = Path(f"/etc/cron.d/blzbak-{args.name}")
        if cron_path.exists():
            try:
                resp = input(f"Removing the cron job requires elevated permissions. Use sudo to remove {cron_path}? [Y/n]: ")
            except KeyboardInterrupt:
                print("\nSkipped removing system cron job.", file=sys.stderr)
                resp = "n"
            if resp.strip() == "" or resp.strip().lower() in ("y", "yes"):
                try:
                    subprocess.run(["sudo", "rm", "-f", str(cron_path)], check=True)
                    print(f"Cron job removed for '{args.name}' (via sudo).")
                except subprocess.CalledProcessError as exc2:
                    print(f"Warning: Failed to remove cron job with sudo: {exc2}", file=sys.stderr)
            else:
                print("Skipped removing system cron job.", file=sys.stderr)
        else:
            print(f"Warning: Failed to remove cron job: {exc}", file=sys.stderr)
    
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
