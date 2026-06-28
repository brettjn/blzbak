# blzbak Daemon Graphical Installer

A PyQt6-based graphical installer for the blzbak backup daemon (blzbakd) on Ubuntu 24.04.

## Features

- **Step-by-step wizard interface** - Guides you through installation
- **Automatic user/group creation** - Creates dedicated `blzbak` system user
- **Configurable paths** - Choose installation and storage locations
- **Systemd integration** - Sets up automatic daemon startup at boot
- **One-click daemon start** - Option to start daemon immediately after installation
- **Progress tracking** - Visual feedback during installation
- **Error handling** - Clear error messages and validation

## Requirements

- Ubuntu 24.04 (or compatible Linux distribution)
- Python 3.10 or later
- PyQt6
- Root/sudo privileges
- blzbak.zip package file (created with `create_package.py`)

## Installation of Installer Dependencies

Before running the installer, install the required Python packages:

```bash
pip install PyQt6 pyyaml
```

Or using the requirements file:

```bash
pip install -r requirements.txt
```

## Preparing the Package

Before running the installer, you need to create the blzbak.zip package:

```bash
cd installer
python3 create_package.py
```

This will create `blzbak.zip` containing the daemon files needed for installation.

## Running the Installer

The installer requires root privileges to create system users and install services:

```bash
sudo python3 installer_gui.py
```

Or if you prefer to use a virtual environment:

```bash
sudo /path/to/venv/bin/python installer_gui.py
```

## Installation Steps

The wizard will guide you through these steps:

### 1. Welcome
- Checks for blzbak.zip package
- Verifies root privileges
- Displays installation overview

### 2. Path Configuration
- **Installation Directory** - Where to install blzbakd (default: `/opt/blzbak`)
- **Backup Directory** - Root directory for storing backups (default: `/blzbak`)
- **Diffs Directory** - Where to store differential archives (default: `/blzbak/diffs`)
- **Network Settings** - TCP port (default: 7890) and bind address (default: 0.0.0.0)

### 3. Installation
- Extracts package files
- Creates blzbak system user and group
- Installs daemon files
- Creates configuration file
- Sets up storage directories with proper permissions
- Installs and enables systemd service
- Cleans up temporary files

### 4. Completion
- Displays installation summary
- Option to start daemon immediately
- Shows next steps and useful commands

## What Gets Installed

### Files
- `/opt/blzbak/blzbakd` - Daemon executable (configurable location)
- `/opt/blzbak/.config` - Daemon configuration (YAML)
- `/opt/blzbak/*.py` - Daemon modules

### System Integration
- `/etc/systemd/system/blzbakd.service` - Systemd service file
- System user: `blzbak`
- System group: `blzbak`

### Storage
- `/blzbak/` - Backup storage (configurable)
- `/blzbak/diffs/` - Differential archives (configurable)

## Post-Installation

### Check Daemon Status
```bash
sudo systemctl status blzbakd
```

### View Logs
```bash
sudo journalctl -u blzbakd -f
```

### Start/Stop/Restart
```bash
sudo systemctl start blzbakd
sudo systemctl stop blzbakd
sudo systemctl restart blzbakd
```

### Disable Auto-Start
```bash
sudo systemctl disable blzbakd
```

### Re-enable Auto-Start
```bash
sudo systemctl enable blzbakd
```

## Uninstallation

To uninstall blzbakd:

```bash
# Stop and disable service
sudo systemctl stop blzbakd
sudo systemctl disable blzbakd

# Remove service file
sudo rm /etc/systemd/system/blzbakd.service
sudo systemctl daemon-reload

# Remove installation directory (adjust path if you used a different location)
sudo rm -rf /opt/blzbak

# Optionally remove storage directories (WARNING: This deletes all backups!)
# sudo rm -rf /blzbak

# Optionally remove user and group
# sudo userdel blzbak
# sudo groupdel blzbak
```

## Configuration File

The installer creates a YAML configuration file at `{install_path}/.config`:

```yaml
base_path: /blzbak
port: 7890
host: 0.0.0.0
diff_dir: /blzbak/diffs
max_workers: 4
log_level: INFO
```

You can manually edit this file and restart the daemon to apply changes:

```bash
sudo nano /opt/blzbak/.config
sudo systemctl restart blzbakd
```

## Troubleshooting

### "Insufficient Privileges" Error
Run the installer with sudo:
```bash
sudo python3 installer_gui.py
```

### "blzbak.zip not found" Error
Run `create_package.py` first to create the package:
```bash
python3 create_package.py
```

### Port Already in Use
If port 7890 is already in use, you can:
1. Choose a different port during installation
2. Or manually edit `/opt/blzbak/.config` and restart the daemon

### Permission Denied on Storage Directories
The installer should set permissions automatically, but if issues occur:
```bash
sudo chown -R blzbak:blzbak /blzbak
sudo chmod -R 750 /blzbak
```

### Daemon Won't Start
Check the logs for errors:
```bash
sudo journalctl -u blzbakd -n 50
```

Common issues:
- Port already in use
- Configuration file syntax error
- Storage directories don't exist or have wrong permissions

### Python Module Not Found
Ensure all dependencies are installed:
```bash
pip install PyQt6 pyyaml
```

## Security Considerations

- The installer must run as root to create system users and install services
- The daemon runs as a dedicated `blzbak` user with limited privileges
- The systemd service includes security hardening options
- Storage directories are owned by the `blzbak` user
- Configuration file has restricted permissions (640)

## Development

### Project Structure
```
installer/
├── __init__.py
├── installer_gui.py      # Main Qt6 wizard application
├── system_ops.py         # System operations (user creation, systemd)
├── file_ops.py           # File operations (extraction, installation)
├── create_package.py     # Package creation script
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

### Testing
To test the installer without actually installing:
1. Modify the code to skip privileged operations
2. Use a test directory instead of system paths
3. Test individual modules in isolation

### Creating Custom Installers
The installer is modular and can be adapted for different:
- Linux distributions (update paths and commands in system_ops.py)
- Installation locations (change defaults in PathConfigPage)
- Package contents (modify create_package.py)

## License

This installer is part of the blzbak project. See the project's LICENSE file for details.

## Support

For issues or questions:
- Check the daemon documentation: `blzbak/daemon/README.md`
- Review systemd logs: `sudo journalctl -u blzbakd`
- Check the project repository for updates

## See Also

- [Daemon Documentation](../blzbak/daemon/README.md)
- [Client CLI Documentation](../README.md)
- [Protocol Documentation](../blzbak/protocol.py)
