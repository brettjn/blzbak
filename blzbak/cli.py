"""blzbak CLI — main entry point.

Command hierarchy:

    blzbak [--server HOST] [--port N] [--config FILE] [-v] [--no-daemon]

        set  list
             create  <name> <source...> [--schedule CRON]
             show    <name>
             delete  <name>
             edit    <name>

        backup  run         <name> [--dry-run]
                list        [name]
                list-files  <name> [--snapshot C|O] [--path PATH]

        restore  file    <name> <file>   [--snapshot S] [--dest P] [-y] [--dry-run]
                 folder  <name> <folder> [--snapshot S] [--dest P] [-y] [--dry-run]
                 set     <name>          [--snapshot S] [--dest P] [-y] [--dry-run]

        cron  install  <name> [--schedule CRON]
              remove   <name>
              list
              edit     <name> <schedule>
"""

import argparse
import sys
from pathlib import Path

from .config import load_config, setup_logging
from .client import DaemonClient, DaemonError
from .commands import set_cmd, backup_cmd, restore_cmd, cron_cmd


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blzbak",
        description="blzbak — Automated backup system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--server",    metavar="HOST", help="Override server hostname from config")
    parser.add_argument("--port",      metavar="PORT", type=int, help="Override daemon port from config")
    parser.add_argument("--config",    metavar="FILE", help="Path to CLI .config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose/debug output")
    parser.add_argument(
        "--no-daemon", action="store_true",
        help="Skip daemon connection (valid only for local-only commands)"
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    _add_set_commands(sub)
    _add_backup_commands(sub)
    _add_restore_commands(sub)
    _add_cron_commands(sub)

    return parser


def _add_set_commands(sub: argparse._SubParsersAction) -> None:
    p  = sub.add_parser("set", help="Manage backup set configurations")
    ss = p.add_subparsers(dest="set_command", metavar="SUBCOMMAND")
    ss.required = True

    ss.add_parser("list", help="List all configured backup sets")

    c = ss.add_parser("create", help="Create a new backup set")
    c.add_argument("name", help="Backup set name (letters, digits, hyphens, underscores)")
    c.add_argument("sources", nargs="+", metavar="SOURCE", help="Source paths to back up")
    c.add_argument(
        "--schedule", default="0 2 * * *", metavar="CRON",
        help="Cron schedule expression (default: '0 2 * * *' — daily at 02:00)"
    )

    sh = ss.add_parser("show", help="Print backup set configuration as YAML")
    sh.add_argument("name")

    d = ss.add_parser("delete", help="Delete a backup set configuration")
    d.add_argument("name")

    e = ss.add_parser("edit", help="Open backup set config in $EDITOR")
    e.add_argument("name")


def _add_backup_commands(sub: argparse._SubParsersAction) -> None:
    p  = sub.add_parser("backup", help="Run backups and inspect backup history")
    bs = p.add_subparsers(dest="backup_command", metavar="SUBCOMMAND")
    bs.required = True

    r = bs.add_parser("run", help="Run a backup set immediately")
    r.add_argument("name", help="Backup set name")
    r.add_argument("--dry-run", action="store_true", help="Simulate rsync without transferring files")

    ls = bs.add_parser("list", help="List snapshots on the server")
    ls.add_argument("name", nargs="?", help="Backup set name (omit to list all sets on server)")

    lf = bs.add_parser("list-files", help="List files in a backup snapshot")
    lf.add_argument("name", help="Backup set name")
    lf.add_argument("--snapshot", default="C", metavar="SNAP",
                    help="Snapshot label: C (current) or O (once-removed) [default: C]")
    lf.add_argument("--path", default="/", metavar="PATH",
                    help="Remote directory to list [default: /]")


def _add_restore_commands(sub: argparse._SubParsersAction) -> None:
    p  = sub.add_parser("restore", help="Restore files from backup")
    rs = p.add_subparsers(dest="restore_command", metavar="SUBCOMMAND")
    rs.required = True

    # Shared restore flags added to each subcommand for clarity
    def _add_restore_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--snapshot", default="C", metavar="SNAP",
                        help="Snapshot to restore from: C (current) or O (once-removed) [default: C]")
        sp.add_argument("--dest", metavar="PATH",
                        help="Destination base path (default: restore to original location)")
        sp.add_argument("-y", "--yes", action="store_true",
                        help="Restore to original location without prompting")
        sp.add_argument("--dry-run", action="store_true",
                        help="Simulate rsync without writing files")

    f = rs.add_parser("file", help="Restore a single file")
    f.add_argument("name", help="Backup set name")
    f.add_argument("file", metavar="FILE", help="Absolute path of the file to restore")
    _add_restore_flags(f)

    fo = rs.add_parser("folder", help="Restore a folder and its contents")
    fo.add_argument("name", help="Backup set name")
    fo.add_argument("folder", metavar="FOLDER", help="Absolute path of the folder to restore")
    _add_restore_flags(fo)

    se = rs.add_parser("set", help="Restore an entire backup set")
    se.add_argument("name", help="Backup set name")
    _add_restore_flags(se)


def _add_cron_commands(sub: argparse._SubParsersAction) -> None:
    p  = sub.add_parser("cron", help="Manage scheduled backup cron jobs")
    cs = p.add_subparsers(dest="cron_command", metavar="SUBCOMMAND")
    cs.required = True

    i = cs.add_parser("install", help="Install (or update) a cron job for a backup set")
    i.add_argument("name")
    i.add_argument("--schedule", metavar="CRON",
                   help="Override the schedule stored in the backup set")

    rm = cs.add_parser("remove", help="Remove the cron job for a backup set")
    rm.add_argument("name")

    cs.add_parser("list", help="List all blzbak-managed cron jobs")

    ed = cs.add_parser("edit", help="Change the cron schedule for a backup set")
    ed.add_argument("name")
    ed.add_argument("schedule", metavar="CRON", help="New cron expression (e.g. '0 3 * * *')")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _dispatch(args, config: dict, client) -> int:
    cmd = args.command

    if cmd == "set":
        sc = args.set_command
        if sc == "list":   return set_cmd.cmd_set_list(args, config)
        if sc == "create": return set_cmd.cmd_set_create(args, config)
        if sc == "show":   return set_cmd.cmd_set_show(args, config)
        if sc == "delete": return set_cmd.cmd_set_delete(args, config)
        if sc == "edit":   return set_cmd.cmd_set_edit(args, config)

    elif cmd == "backup":
        bc = args.backup_command
        if bc == "run":        return backup_cmd.cmd_backup_run(args, config, client)
        if bc == "list":       return backup_cmd.cmd_backup_list(args, config, client)
        if bc == "list-files": return backup_cmd.cmd_backup_list_files(args, config, client)

    elif cmd == "restore":
        rc = args.restore_command
        if rc == "file":   return restore_cmd.cmd_restore_file(args, config, client)
        if rc == "folder": return restore_cmd.cmd_restore_folder(args, config, client)
        if rc == "set":    return restore_cmd.cmd_restore_set(args, config, client)

    elif cmd == "cron":
        cc = args.cron_command
        if cc == "install": return cron_cmd.cmd_cron_install(args, config)
        if cc == "remove":  return cron_cmd.cmd_cron_remove(args, config)
        if cc == "list":    return cron_cmd.cmd_cron_list(args, config)
        if cc == "edit":    return cron_cmd.cmd_cron_edit(args, config)

    print(f"Internal error: unhandled command '{args.command}'", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    config_path = Path(args.config) if getattr(args, "config", None) else None
    config      = load_config(config_path)

    log_level = "DEBUG" if args.verbose else config.get("log_level", "INFO")
    setup_logging(log_level)

    # CLI flags take precedence over config file
    if getattr(args, "server", None):
        config.setdefault("server", {})["host"] = args.server
    if getattr(args, "port", None):
        config.setdefault("server", {})["port"] = args.port

    # Daemon connection is required for backup and restore commands
    needs_daemon = args.command in ("backup", "restore")
    client: DaemonClient | None = None

    if needs_daemon and not getattr(args, "no_daemon", False):
        srv    = config.get("server", {})
        client = DaemonClient(
            host = srv.get("host", "localhost"),
            port = int(srv.get("port", 7890)),
        )
        try:
            client.connect()
        except ConnectionError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        rc = _dispatch(args, config, client)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        rc = 130
    finally:
        if client:
            client.disconnect()

    sys.exit(rc or 0)
