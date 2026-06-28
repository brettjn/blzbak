# Quick Start Guide - blzbak Installer

## For Users

### Prerequisites
1. Ubuntu 24.04 or compatible Linux distribution
2. Root/sudo access
3. Python 3.10+ installed

### Installation Steps

1. **Install Python dependencies:**
   ```bash
   pip install PyQt6 PyYAML
   ```

2. **Run the installer:**
   ```bash
   cd installer
   sudo bash run_installer.sh
   ```

   Or directly:
   ```bash
   sudo python3 installer_gui.py
   ```

3. **Follow the wizard:**
   - Review the welcome screen
   - Configure installation paths (or use defaults)
   - Wait for installation to complete
   - Choose whether to start the daemon now
   - Click Finish

4. **Verify installation:**
   ```bash
   sudo systemctl status blzbakd
   ```

### Default Locations

- **Daemon**: `/opt/blzbak/blzbakd`
- **Config**: `/opt/blzbak/.config`
- **Backups**: `/blzbak/`
- **Diffs**: `/blzbak/diffs/`
- **Service**: `/etc/systemd/system/blzbakd.service`

### Common Commands

```bash
# Check status
sudo systemctl status blzbakd

# Start daemon
sudo systemctl start blzbakd

# Stop daemon
sudo systemctl stop blzbakd

# View logs
sudo journalctl -u blzbakd -f

# Edit configuration
sudo nano /opt/blzbak/.config
sudo systemctl restart blzbakd
```

---

## For Developers

### Building the Installer Package

1. **Create the package:**
   ```bash
   cd installer
   python3 create_package.py
   ```

   This creates `blzbak.zip` containing the daemon files.

2. **Verify package contents:**
   ```bash
   unzip -l blzbak.zip
   ```

### Testing the Installer

**Option 1: Full Test (requires root)**
```bash
sudo python3 installer_gui.py
```

**Option 2: Module Testing**
```bash
# Test without GUI
python3 -c "
from file_ops import find_blzbak_zip
print(find_blzbak_zip())
"

# Test system checks
sudo python3 -c "
from system_ops import check_root_privileges, user_exists
print('Root:', check_root_privileges())
print('User exists:', user_exists('blzbak'))
"
```

### Project Structure

```
installer/
├── __init__.py                # Package init
├── installer_gui.py           # Main Qt6 application (570+ lines)
├── system_ops.py              # System operations (220+ lines)
├── file_ops.py                # File operations (200+ lines)
├── create_package.py          # Package builder (70+ lines)
├── run_installer.sh           # Launch script
├── requirements.txt           # Python dependencies
├── README.md                  # Full documentation
├── QUICKSTART.md             # This file
└── blzbak.zip                # Package (created by create_package.py)
```

### Customization

**Change default paths:**
Edit `PathConfigPage.__init__()` in `installer_gui.py`:
```python
self.install_path_edit = QLineEdit("/your/custom/path")
self.base_path_edit = QLineEdit("/your/backup/path")
```

**Modify systemd service:**
Edit `install_systemd_service()` in `system_ops.py`.

**Add more validation:**
Add checks in `PathConfigPage.validatePage()` or `IntroPage.validatePage()`.

### Debugging

**Enable verbose output:**
```python
# In installer_gui.py, set debug flag
DEBUG = True
```

**Check for errors:**
```bash
# Run from terminal to see print() output
sudo python3 installer_gui.py 2>&1 | tee install.log
```

**Test individual components:**
```python
# Test file extraction
from file_ops import find_blzbak_zip, extract_blzbak_zip
zip_path = find_blzbak_zip()
temp_dir = extract_blzbak_zip(zip_path)
print(f"Extracted to: {temp_dir}")
```

### Building a Distributable

To create a standalone installer:

1. **Using PyInstaller:**
   ```bash
   pip install pyinstaller
   pyinstaller --onefile --windowed \
     --add-data "blzbak.zip:." \
     installer_gui.py
   ```

2. **Create a .deb package:**
   - Create debian package structure
   - Include dependencies and postinst script
   - Build with `dpkg-deb`

3. **Create an AppImage:**
   - Use linuxdeploy-plugin-python
   - Bundle Python and all dependencies

### Contributing

To contribute improvements:

1. Test thoroughly on a clean Ubuntu 24.04 system
2. Ensure all paths are configurable
3. Add proper error handling
4. Update README.md with new features
5. Test uninstallation procedure

### Troubleshooting Development

**Import errors:**
```bash
# Ensure dependencies are installed
pip install -r requirements.txt

# Check Python path
python3 -c "import sys; print(sys.path)"
```

**PyQt6 display issues:**
```bash
# Set display variable if running remotely
export DISPLAY=:0
```

**Permission errors during testing:**
```bash
# Always use sudo for installation testing
sudo python3 installer_gui.py
```

---

## Support

- See [README.md](README.md) for complete documentation
- Check [daemon/README.md](../blzbak/daemon/README.md) for daemon details
- Review system logs: `sudo journalctl -u blzbakd -n 100`
