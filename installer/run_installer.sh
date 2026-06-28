#!/usr/bin/env bash
#
# Quick start script to run the blzbak installer with proper environment
#

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "This installer requires root privileges."
    echo "Please run with sudo:"
    echo "  sudo $0"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "blzbak Daemon Installer"
echo "======================="
echo ""

# Check for blzbak.zip
if [ ! -f "$SCRIPT_DIR/blzbak.zip" ]; then
    echo "Error: blzbak.zip not found in $SCRIPT_DIR"
    echo ""
    echo "Please create the package first:"
    echo "  python3 create_package.py"
    exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    echo "Please install Python 3"
    exit 1
fi

# Check for PyQt6
if ! python3 -c "import PyQt6" 2>/dev/null; then
    echo "Error: PyQt6 not installed"
    echo ""
    echo "Please install dependencies first:"
    echo "  pip install -r requirements.txt"
    echo ""
    echo "Or install manually:"
    echo "  pip install PyQt6 PyYAML"
    exit 1
fi

# Run the installer
echo "Starting graphical installer..."
echo ""

# Method 1: Use the Python launcher (recommended)
if [ -f "$SCRIPT_DIR/run_installer.py" ]; then
    python3 "$SCRIPT_DIR/run_installer.py"
    exit $?
fi

# Method 2: Run directly with proper path setup
cd "$SCRIPT_DIR"
PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" python3 installer_gui.py

exit $?
