"""rsync wrapper utilities for blzbak backup and restore operations.

Backup  (local → remote):
    Uses -az --delete so the remote C/ mirror exactly matches the source.

Restore (remote → local):
    Uses -az --relative with the /./ path trick so the original directory
    structure is preserved under the chosen destination root.

    Example:
        remote_source = "backup@server:/blzbak/docs/C/./home/alice/report.pdf"
        dest_root     = "/"            → restores to  /home/alice/report.pdf
        dest_root     = "/restore/"   → restores to  /restore/home/alice/report.pdf
"""

import logging
import subprocess
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def build_backup_cmd(
    source_paths: list[str],
    dest: str,
    exclude_patterns: list[str],
    *,
    ssh_key_path: str = "",
    dry_run: bool = False,
    verbose: bool = False,
) -> list[str]:
    """Return an rsync command list for a backup operation."""
    cmd = ["rsync", "-az", "--delete"]
    
    # Build SSH command with options for host key handling and optional identity file
    ssh_opts = []
    if ssh_key_path:
        ssh_opts.extend(["-i", ssh_key_path])
    ssh_opts.extend([
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/var/lib/blzbak/known_hosts",
    ])
    
    if ssh_opts:
        # Quote the entire SSH command properly for rsync's -e option
        ssh_cmd = "ssh " + " ".join(ssh_opts)
        cmd.extend(["-e", ssh_cmd])
    
    if dry_run:
        cmd.append("--dry-run")
    if verbose:
        cmd.append("-v")
    for pattern in exclude_patterns:
        pattern = pattern.strip()
        if pattern and not pattern.startswith("#"):
            cmd.append(f"--exclude={pattern}")
    cmd.extend(source_paths)
    cmd.append(dest)
    return cmd


def build_restore_cmd(
    remote_source: str,
    dest_root: str,
    *,
    ssh_key_path: str = "",
    dry_run: bool = False,
    verbose: bool = False,
) -> list[str]:
    """Return an rsync command list for a restore operation."""
    cmd = ["rsync", "-az", "--relative"]
    
    # Build SSH command with options for host key handling and optional identity file
    ssh_opts = []
    if ssh_key_path:
        ssh_opts.extend(["-i", ssh_key_path])
    ssh_opts.extend([
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/var/lib/blzbak/known_hosts",
    ])
    
    if ssh_opts:
        # Quote the entire SSH command properly for rsync's -e option
        ssh_cmd = "ssh " + " ".join(ssh_opts)
        cmd.extend(["-e", ssh_cmd])
    
    if dry_run:
        cmd.append("--dry-run")
    if verbose:
        cmd.append("-v")
    cmd.append(remote_source)
    cmd.append(dest_root)
    return cmd


def run_rsync(
    cmd: list[str],
    callback: Optional[Callable[[str], None]] = None,
) -> int:
    """Execute an rsync command, streaming output line by line.

    Args:
        cmd:      Full rsync command as a list (shell=False).
        callback: Called with each output line; defaults to print().

    Returns:
        rsync exit code (0 = success).
    """
    logger.debug("Running: %s", " ".join(cmd))
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as proc:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if callback:
                callback(line)
            else:
                print(line)
    return proc.returncode
