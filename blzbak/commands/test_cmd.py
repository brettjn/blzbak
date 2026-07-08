"""CLI command: test - Test configuration and server connection."""

import sys
from pathlib import Path

import yaml

from ..backup import list_backup_sets
from ..client import DaemonClient, DaemonError
from ..cron import list_cron_jobs


def cmd_test(args, config: dict, client: DaemonClient | None) -> int:
    """Test local configuration, backup sets, cron jobs, and server connection."""
    
    print("=" * 70)
    print("blzbak Configuration Test")
    print("=" * 70)
    print()
    
    # -----------------------------------------------------------------------
    # 1. Local Configuration
    # -----------------------------------------------------------------------
    print("1. Local Configuration")
    print("-" * 70)
    
    srv = config.get("server", {})
    sets_dir = config.get("sets_directory", "/etc/blzbak")
    log_level = config.get("log_level", "INFO")
    
    print(f"  Server Host:       {srv.get('host', 'localhost')}")
    print(f"  Server Port:       {srv.get('port', 7890)}")
    print(f"  SSH User:          {srv.get('ssh_user', '(none)')}")
    print(f"  Backup Base Path:  {srv.get('backup_base', '/blzbak')}")
    print(f"  Sets Directory:    {sets_dir}")
    print(f"  Log Level:         {log_level}")
    
    # Check if sets directory exists
    sets_path = Path(sets_dir)
    if sets_path.exists():
        print(f"  Sets Dir Status:   ✓ Exists")
    else:
        print(f"  Sets Dir Status:   ✗ Does not exist (will be created when needed)")
    
    print()
    
    # -----------------------------------------------------------------------
    # 2. Configured Backup Sets
    # -----------------------------------------------------------------------
    print("2. Configured Backup Sets")
    print("-" * 70)
    
    try:
        backup_sets = list_backup_sets(config)
        if not backup_sets:
            print("  No backup sets configured.")
        else:
            print(f"  Total sets: {len(backup_sets)}")
            print()
            for bs in backup_sets:
                print(f"  [{bs.name}]")
                print(f"    Schedule:     {bs.schedule}")
                print(f"    Sources:      {', '.join(bs.source_paths) if bs.source_paths else '(none)'}")
                print(f"    Destination:  {bs.server.host}:{bs.server.dest_path}")
                print(f"    Excludes:     {len(bs.exclude_patterns)} patterns")
                print(f"    Created:      {bs.created_at}")
                print()
    except Exception as e:
        print(f"  ✗ Error loading backup sets: {e}")
        print()
    
    # -----------------------------------------------------------------------
    # 3. Cron Jobs
    # -----------------------------------------------------------------------
    print("3. Scheduled Cron Jobs")
    print("-" * 70)
    
    try:
        cron_jobs = list_cron_jobs()
        if not cron_jobs:
            print("  No blzbak cron jobs installed.")
        else:
            print(f"  Total jobs: {len(cron_jobs)}")
            print()
            for job in cron_jobs:
                print(f"  [{job['set_name']}]")
                print(f"    Schedule: {job['schedule']}")
                print()
    except Exception as e:
        print(f"  ✗ Error reading crontab: {e}")
        print()
    
    # -----------------------------------------------------------------------
    # 4. Server Connection Test
    # -----------------------------------------------------------------------
    print("4. Server Connection Test")
    print("-" * 70)
    
    if not client:
        print("  ✗ No daemon connection available")
        print("    (Use --no-daemon flag if you want to skip server test)")
        print()
        return 1
    
    try:
        # Test basic connectivity
        print(f"  Testing connection to {srv.get('host', 'localhost')}:{srv.get('port', 7890)}...")
        
        # Request test information from daemon
        response = client.test()
        
        if response.get("status") == "ok":
            print("  ✓ Connection successful!")
            print()
            
            # Display daemon configuration
            daemon_info = response.get("daemon", {})
            print("  Daemon Configuration:")
            print(f"    Base Path:          {daemon_info.get('base_path', 'N/A')}")
            print(f"    Diff Directory:     {daemon_info.get('diff_dir', 'N/A')}")
            
            if "host" in daemon_info:
                print(f"    Listen Host:        {daemon_info.get('host', 'N/A')}")
            if "port" in daemon_info:
                print(f"    Listen Port:        {daemon_info.get('port', 'N/A')}")
            if "max_workers" in daemon_info:
                print(f"    Max Workers:        {daemon_info.get('max_workers', 'N/A')}")
            if "log_level" in daemon_info:
                print(f"    Log Level:          {daemon_info.get('log_level', 'N/A')}")
            
            # Check storage status
            base_exists = daemon_info.get('base_path_exists', False)
            base_writable = daemon_info.get('base_path_writable', False)
            
            print(f"    Base Path Exists:   {'✓' if base_exists else '✗'}")
            print(f"    Base Path Writable: {'✓' if base_writable else '✗'}")
            
            if not base_exists:
                print("    ⚠ Warning: Base path does not exist on server!")
            elif not base_writable:
                print("    ⚠ Warning: Base path is not writable on server!")
            
            print()
            
            # Display backup sets on server
            server_sets = response.get("sets", [])
            if server_sets:
                print(f"  Backup Sets on Server: {len(server_sets)}")
                print()
                for set_info in server_sets:
                    set_name = set_info.get("name", "unknown")
                    print(f"    [{set_name}]")
                    
                    if "error" in set_info:
                        print(f"      ✗ Error: {set_info['error']}")
                    else:
                        snapshots = set_info.get("snapshots", {})
                        c_snap = snapshots.get("C")
                        o_snap = snapshots.get("O")
                        
                        if c_snap:
                            print(f"      Current (C):      ✓ {c_snap.get('timestamp', 'N/A')}")
                        else:
                            print(f"      Current (C):      (none)")
                        
                        if o_snap:
                            print(f"      Once-removed (O): ✓ {o_snap.get('timestamp', 'N/A')}")
                        else:
                            print(f"      Once-removed (O): (none)")
                    print()
            else:
                print("  No backup sets found on server.")
                print()
                
            if "sets_error" in response:
                print(f"  ✗ Error listing server sets: {response['sets_error']}")
                print()
        else:
            print(f"  ✗ Server returned error: {response.get('message', 'Unknown error')}")
            print()
            return 1
            
    except DaemonError as e:
        print(f"  ✗ Daemon error: {e}")
        print()
        return 1
    except ConnectionError as e:
        print(f"  ✗ Connection failed: {e}")
        print()
        return 1
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        print()
        return 1
    
    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("=" * 70)
    print("Test Complete!")
    print("=" * 70)
    
    return 0
