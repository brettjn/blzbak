"""System operations for the blzbak installer.

Handles user creation, systemd service installation, and daemon management.
"""

import os
import subprocess
import pwd
import grp
from pathlib import Path


def check_root_privileges() -> bool:
    """Check if running with root privileges."""
    return os.geteuid() == 0


def user_exists(username: str) -> bool:
    """Check if a user exists."""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def group_exists(groupname: str) -> bool:
    """Check if a group exists."""
    try:
        grp.getgrnam(groupname)
        return True
    except KeyError:
        return False


def create_blzbak_user() -> bool:
    """Create the blzbak system user and group.
    
    Returns:
        True if successful or user already exists, False otherwise.
    """
    try:
        # Check if group exists
        if not group_exists('blzbak'):
            result = subprocess.run(
                ['groupadd', '--system', 'blzbak'],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"Failed to create group: {result.stderr}")
                return False
        
        # Check if user exists
        if not user_exists('blzbak'):
            result = subprocess.run(
                [
                    'useradd',
                    '--system',
                    '--gid', 'blzbak',
                    '--shell', '/usr/sbin/nologin',
                    '--home-dir', '/nonexistent',
                    '--no-create-home',
                    '--comment', 'blzbak backup daemon',
                    'blzbak'
                ],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"Failed to create user: {result.stderr}")
                return False
        
        return True
        
    except Exception as e:
        print(f"Error creating user/group: {e}")
        return False


def install_systemd_service(config: dict) -> bool:
    """Install and enable the systemd service.
    
    Args:
        config: Dictionary with install_path, base_path, etc.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        install_path = config['install_path']
        daemon_path = Path(install_path) / 'blzbakd'
        config_path = Path(install_path) / '.config'
        
        # Create systemd service file
        service_content = f"""[Unit]
Description=blzbak backup server daemon
After=network.target

[Service]
Type=simple
User=blzbak
Group=blzbak
ExecStart={daemon_path} --config {config_path}
Restart=on-failure
RestartSec=5s

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={config['base_path']} {config['diff_path']}

[Install]
WantedBy=multi-user.target
"""
        
        # Write service file
        service_file = Path('/etc/systemd/system/blzbakd.service')
        service_file.write_text(service_content)
        
        # Reload systemd
        result = subprocess.run(
            ['systemctl', 'daemon-reload'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Failed to reload systemd: {result.stderr}")
            return False
        
        # Enable service
        result = subprocess.run(
            ['systemctl', 'enable', 'blzbakd.service'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Failed to enable service: {result.stderr}")
            return False
        
        return True
        
    except Exception as e:
        print(f"Error installing systemd service: {e}")
        return False


def start_daemon() -> tuple[bool, str]:
    """Start the blzbakd daemon.
    
    Returns:
        Tuple of (success, message)
    """
    try:
        result = subprocess.run(
            ['systemctl', 'start', 'blzbakd.service'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return True, "Daemon started successfully"
        else:
            return False, result.stderr or "Unknown error"
            
    except subprocess.TimeoutExpired:
        return False, "Timeout waiting for daemon to start"
    except Exception as e:
        return False, str(e)


def stop_daemon() -> tuple[bool, str]:
    """Stop the blzbakd daemon.
    
    Returns:
        Tuple of (success, message)
    """
    try:
        result = subprocess.run(
            ['systemctl', 'stop', 'blzbakd.service'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return True, "Daemon stopped successfully"
        else:
            return False, result.stderr or "Unknown error"
            
    except subprocess.TimeoutExpired:
        return False, "Timeout waiting for daemon to stop"
    except Exception as e:
        return False, str(e)


def daemon_is_running() -> bool:
    """Check if the blzbakd daemon is currently running.
    
    Returns:
        True if running, False otherwise.
    """
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'blzbakd.service'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and result.stdout.strip() == 'active'
    except Exception:
        return False


def get_daemon_status() -> str:
    """Get the status of the blzbakd daemon.
    
    Returns:
        Status string or error message.
    """
    try:
        result = subprocess.run(
            ['systemctl', 'status', 'blzbakd.service'],
            capture_output=True,
            text=True
        )
        return result.stdout
    except Exception as e:
        return f"Error getting status: {e}"
