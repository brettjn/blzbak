"""Show backup history for a set using the server's set.log."""

from datetime import datetime
import sys

from ..client import DaemonClient, DaemonError


def _format_entry(entry: dict) -> str:
    # entry contains: number, started_at, finished_at (nullable), location_type, optional diff_path
    num = entry.get("number")
    started = entry.get("started_at")
    finished = entry.get("finished_at")

    try:
        s_dt = datetime.fromisoformat(started).astimezone()
        s_date = s_dt.date().isoformat()
        s_time = s_dt.time().isoformat(timespec="seconds")
    except Exception:
        s_date = started or "-"
        s_time = "-"

    if finished:
        try:
            f_dt = datetime.fromisoformat(finished).astimezone()
            # If finished on same local date, omit date
            if f_dt.date() == s_dt.date():
                f_str = f_dt.time().isoformat(timespec="seconds")
            else:
                f_str = f"{f_dt.date().isoformat()} {f_dt.time().isoformat(timespec='seconds')}"
        except Exception:
            f_str = finished
    else:
        f_str = "<in-progress>"

    diff = entry.get("diff_path")
    diff_str = f" diff={diff}" if diff else ""

    return f"{num}. {s_date} start={s_time} end={f_str}{diff_str}"


def cmd_show(args, config, client: DaemonClient) -> int:
    name = args.name
    try:
        entries = client.show_set(name)
        # client.show_set previously returned entries only; support newer responses
        sources = None
        if isinstance(entries, dict):
            sources = entries.get("source_paths")
            entries = entries.get("entries", [])
    except DaemonError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Failed to query daemon: {e}", file=sys.stderr)
        return 1

    if not entries:
        print(f"No history found for set '{name}'")
        return 0

    # Print sources being backed up
    if sources:
        if isinstance(sources, (list, tuple)):
            print("Source paths:")
            for s in sources:
                print(f"  - {s}")
        else:
            print(f"Source: {sources}")
        print()

    # entries are newest-first; list by number
    for entry in entries:
        print(_format_entry(entry))

    return 0
