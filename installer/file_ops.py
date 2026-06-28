"""File operations for the blzbak installer.

Handles zip extraction, file installation, and configuration generation.
"""

import os
import shutil
import tempfile
import zipfile
import yaml
from pathlib import Path
from typing import Optional


def find_blzbak_zip() -> Optional[Path]:
    """Find the blzbak.zip file in the installer directory.
    
    Returns:
        Path to the zip file, or None if not found.
    """
    # Get installer directory
    installer_dir = Path(__file__).parent.resolve()
    
    # Look for blzbak.zip
    zip_path = installer_dir / 'blzbak.zip'
    if zip_path.exists():
        return zip_path
    
    # Also check parent directory
    parent_zip = installer_dir.parent / 'blzbak.zip'
    if parent_zip.exists():
        return parent_zip
    
    return None


def extract_blzbak_zip(zip_path: Path) -> Optional[Path]:
    """Extract the blzbak.zip file to a temporary directory.
    
    Args:
        zip_path: Path to the zip file
    
    Returns:
        Path to the temporary extraction directory, or None on failure.
    """
    try:
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp(prefix='blzbak_install_'))
        
        # Extract zip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        return temp_dir
        
    except Exception as e:
        print(f"Error extracting zip: {e}")
        return None


def install_daemon_files(temp_dir: Path, install_path: str) -> bool:
    """Install daemon files from temporary directory to installation path.
    
    Args:
        temp_dir: Temporary directory with extracted files
        install_path: Target installation directory
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        install_dir = Path(install_path)
        install_dir.mkdir(parents=True, exist_ok=True)
        
        # Find the blzbak directory in the temp extraction
        # It might be directly in temp_dir or in a subdirectory
        blzbak_dir = None
        if (temp_dir / 'blzbak').exists():
            blzbak_dir = temp_dir / 'blzbak'
        else:
            # Look for it in subdirectories
            for item in temp_dir.iterdir():
                if item.is_dir() and (item / 'blzbak').exists():
                    blzbak_dir = item / 'blzbak'
                    break
        
        if not blzbak_dir:
            print(f"Could not find blzbak directory in {temp_dir}")
            return False
        
        # Look for daemon directory
        daemon_dir = blzbak_dir / 'daemon'
        if not daemon_dir.exists():
            print(f"Daemon directory not found in {blzbak_dir}")
            return False
        
        # Create the blzbak package structure in install location
        # /opt/blzbak/blzbak/daemon/ and /opt/blzbak/blzbak/protocol.py
        blzbak_pkg_dir = install_dir / 'blzbak'
        blzbak_pkg_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy the entire daemon directory into blzbak package
        daemon_dst = blzbak_pkg_dir / 'daemon'
        shutil.copytree(daemon_dir, daemon_dst, dirs_exist_ok=True)
        
        # Copy blzbak/__init__.py
        init_file = blzbak_dir / '__init__.py'
        if init_file.exists():
            shutil.copy2(init_file, blzbak_pkg_dir / '__init__.py')
        
        # Copy protocol.py into blzbak package
        protocol_file = blzbak_dir / 'protocol.py'
        if protocol_file.exists():
            shutil.copy2(protocol_file, blzbak_pkg_dir / 'protocol.py')
        
        # Create a launcher script that adds parent to path
        launcher_content = f"""#!/usr/bin/env python3
\"\"\"Launch script for blzbakd daemon.\"\"\"

import sys
import os

# Add installation directory to path so blzbak package can be imported
sys.path.insert(0, '{install_path}')

# Import and run daemon CLI
from blzbak.daemon.cli import main

if __name__ == '__main__':
    main()
"""
        
        launcher_path = install_dir / 'blzbakd'
        launcher_path.write_text(launcher_content)
        launcher_path.chmod(0o755)  # Make executable
        
        # Set ownership to blzbak user
        os.system(f"chown -R blzbak:blzbak {install_path}")
        
        return True
        
    except Exception as e:
        print(f"Error installing daemon files: {e}")
        return False


def create_daemon_config(config: dict) -> bool:
    """Create the daemon configuration file.
    
    Args:
        config: Dictionary with configuration values
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        install_path = Path(config['install_path'])
        config_path = install_path / '.config'
        
        # Create configuration content
        config_content = {
            'base_path': config['base_path'],
            'port': int(config['port']),
            'host': config['host'],
            'diff_dir': config['diff_path'],
            'max_workers': 4,
            'log_level': 'INFO',
        }
        
        # Write YAML configuration
        with open(config_path, 'w') as f:
            yaml.dump(config_content, f, default_flow_style=False)
        
        # Set ownership
        os.system(f"chown blzbak:blzbak {config_path}")
        os.chmod(config_path, 0o640)  # Read/write for user, read for group
        
        return True
        
    except Exception as e:
        print(f"Error creating configuration: {e}")
        return False


def cleanup_temp_files(temp_dir: Optional[Path]) -> None:
    """Clean up temporary files and directories.
    
    Args:
        temp_dir: Temporary directory to remove
    """
    if temp_dir and temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Warning: Could not clean up temp directory: {e}")


def validate_installation(install_path: str) -> tuple[bool, str]:
    """Validate that the installation was successful.
    
    Args:
        install_path: Installation directory to check
    
    Returns:
        Tuple of (success, message)
    """
    install_dir = Path(install_path)
    
    # Check for required files
    required_files = ['blzbakd', '.config', 'cli.py']
    missing_files = []
    
    for file in required_files:
        if not (install_dir / file).exists():
            missing_files.append(file)
    
    if missing_files:
        return False, f"Missing required files: {', '.join(missing_files)}"
    
    # Check if blzbakd is executable
    blzbakd = install_dir / 'blzbakd'
    if not os.access(blzbakd, os.X_OK):
        return False, "blzbakd is not executable"
    
    return True, "Installation validation passed"
