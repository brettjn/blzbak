"""CLI commands: cron install / remove / list / edit."""

import sys

from ..backup import load_backup_set, save_backup_set
from ..cron import install_cron_job, remove_cron_job, list_cron_jobs


def cmd_cron_install(args, config: dict) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1
    schedule = getattr(args, "schedule", None) or bs.schedule
    try:
        install_cron_job(args.name, schedule)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Cron job installed for '{args.name}' ({schedule}).")
    return 0


def cmd_cron_remove(args, config: dict) -> int:
    try:
        removed = remove_cron_job(args.name)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if removed:
        print(f"Cron job removed for '{args.name}'.")
    else:
        print(f"No cron job found for '{args.name}'.")
    return 0


def cmd_cron_list(args, config: dict) -> int:
    try:
        jobs = list_cron_jobs()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not jobs:
        print("No blzbak cron jobs installed.")
        return 0
    fmt = "  {:<20}  {}"
    print(fmt.format("SET NAME", "SCHEDULE"))
    print("  " + "-" * 42)
    for job in jobs:
        print(fmt.format(job["set_name"], job["schedule"]))
    return 0


def cmd_cron_edit(args, config: dict) -> int:
    bs = load_backup_set(args.name, config)
    if not bs:
        print(f"Error: backup set '{args.name}' not found.", file=sys.stderr)
        return 1
    try:
        install_cron_job(args.name, args.schedule)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    # Keep the stored schedule in sync with the cron table
    bs.schedule = args.schedule
    save_backup_set(bs, config)
    print(f"Cron job updated for '{args.name}' ({args.schedule}).")
    return 0
