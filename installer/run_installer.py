#!/usr/bin/env python3
"""
Launcher script for the blzbak daemon installer.

This script ensures proper Python path setup before launching the GUI.
"""

import sys
import os
from pathlib import Path

# Get the installer directory (where this script is located)
installer_dir = Path(__file__).parent.resolve()

# Add installer directory to Python path for imports
sys.path.insert(0, str(installer_dir))

# Change to installer directory to find blzbak.zip
os.chdir(installer_dir)

# Check for root privileges before starting GUI
if os.geteuid() != 0:
    print("Error: This installer requires root privileges.")
    print("")
    print("Please run with sudo:")
    print(f"  sudo {' '.join(sys.argv)}")
    sys.exit(1)

# Check for PyQt6
try:
    import PyQt6
except ImportError:
    print("Error: PyQt6 is not installed.")
    print("")
    print("Please install dependencies first:")
    print("  pip install -r requirements.txt")
    print("")
    print("Or install manually:")
    print("  pip install PyQt6 PyYAML")
    sys.exit(1)

# Check for blzbak.zip
if not (installer_dir / 'blzbak.zip').exists():
    print("Error: blzbak.zip not found in installer directory.")
    print("")
    print("Please create the package first:")
    print("  python3 create_package.py")
    sys.exit(1)

# Import and run the installer
try:
    from installer_gui import main
    main()
except Exception as e:
    print(f"Error starting installer: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
