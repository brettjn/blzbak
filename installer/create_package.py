#!/usr/bin/env python3
"""
Package the blzbak daemon into a zip file for the installer.

This script creates blzbak.zip containing the daemon and necessary files.
"""

import zipfile
import sys
from pathlib import Path


def create_package():
    """Create the blzbak.zip package."""
    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    blzbak_dir = project_root / 'blzbak'
    
    if not blzbak_dir.exists():
        print(f"Error: Could not find blzbak directory at {blzbak_dir}")
        return False
    
    # Output zip file
    zip_path = script_dir / 'blzbak.zip'
    
    print(f"Creating package: {zip_path}")
    print(f"Source directory: {blzbak_dir}")
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Files to include
            files_to_include = [
                # Core daemon files
                'daemon/__init__.py',
                'daemon/cli.py',
                'daemon/config.py',
                'daemon/handler.py',
                'daemon/server.py',
                'daemon/storage.py',
                'daemon/README.md',
                # Protocol (needed by daemon)
                'protocol.py',
                # Example config
                '../daemon.config.example',
            ]
            
            for file_path in files_to_include:
                source = blzbak_dir / file_path
                if source.exists():
                    arcname = f"blzbak/{file_path}"
                    zipf.write(source, arcname)
                    print(f"  Added: {arcname}")
                else:
                    print(f"  Warning: File not found: {source}")
            
            # Add __init__.py for blzbak package if it exists
            init_file = blzbak_dir / '__init__.py'
            if init_file.exists():
                zipf.write(init_file, 'blzbak/__init__.py')
                print(f"  Added: blzbak/__init__.py")
        
        print(f"\n✓ Package created successfully: {zip_path}")
        print(f"  Size: {zip_path.stat().st_size / 1024:.1f} KB")
        return True
        
    except Exception as e:
        print(f"\n✗ Error creating package: {e}")
        return False


if __name__ == '__main__':
    success = create_package()
    sys.exit(0 if success else 1)
