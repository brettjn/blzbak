# blzbakd - Backup Server Daemon

The `blzbakd` daemon is the server-side component of the blzbak backup system. It listens on a TCP port for backup requests from client machines running the `blzbak` CLI utility.

## Features

- **Multi-threaded TCP server** - Handles multiple concurrent client connections
- **Snapshot management** - Maintains Current (C) and Once-removed (O) backup snapshots
- **Differential backups** - Creates diff archives before rotating snapshots
- **Storage management** - Organizes backups by set name with separate C/O directories
- **Protocol support** - Implements all blzbak protocol commands

## Installation

The daemon is installed automatically when you install the blzbak package:

```bash
pip install -e .
```

This creates the `blzbakd` command in your Python environment.

## Configuration

The daemon looks for a `.config` file in YAML format. By default, it searches for this file in the same directory as the executable. You can also specify a custom config file location:

```bash
blzbakd --config /etc/blzbak/daemon.config
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `base_path` | `/blzbak` | Base directory for storing backups |
| `port` | `7890` | TCP port to listen on |
| `host` | `0.0.0.0` | Host/interface to bind to (0.0.0.0 = all) |
| `max_workers` | `4` | Maximum concurrent worker threads |
| `log_level` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `diff_dir` | `{base_path}/diffs` | Directory for storing diff archives |

### Example Configuration

See `daemon.config.example` for a complete example configuration file.

## Storage Structure

The daemon organizes backups on disk as follows:

```
/blzbak/                      (base_path)
├── backup_set_1/
│   ├── C/                    (Current backup)
│   │   └── ...files...
│   ├── O/                    (Once-removed backup)
│   │   └── ...files...
│   └── metadata.yaml
├── backup_set_2/
│   ├── C/
│   ├── O/
│   └── metadata.yaml
└── diffs/                    (diff archives)
    ├── backup_set_1/
    │   ├── diff_20260617_120000.tar.gz
    │   └── diff_20260617_130000.tar.gz
    └── backup_set_2/
        └── diff_20260617_120000.tar.gz
```

## Running the Daemon

### Basic Usage

Start the daemon with default settings:

```bash
blzbakd
```

### With Custom Settings

Override configuration via command-line arguments:

```bash
blzbakd --port 8000 --base-path /mnt/backups --log-level DEBUG
```

### As a Systemd Service

To run blzbakd as a system service, create `/etc/systemd/system/blzbakd.service`:

```ini
[Unit]
Description=blzbak backup server daemon
After=network.target

[Service]
Type=simple
User=backup
Group=backup
ExecStart=/usr/local/bin/blzbakd --config /etc/blzbak/daemon.config
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Then enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable blzbakd
sudo systemctl start blzbakd
```

Check status:

```bash
sudo systemctl status blzbakd
```

View logs:

```bash
sudo journalctl -u blzbakd -f
```

## Protocol Commands

The daemon implements the following protocol commands:

| Command | Description |
|---------|-------------|
| `PING` | Health check / connectivity test |
| `PREPARE_BACKUP` | Create diffs and sync O→C to prepare for new backup |
| `BACKUP_COMPLETE` | Notification that client finished rsync |
| `LIST_SETS` | List all backup sets on the server |
| `LIST_SNAPSHOTS` | List snapshots (C/O) for a specific set |
| `LIST_FILES` | List files in a specific snapshot |

## Backup Workflow

When a client initiates a backup:

1. **Client sends PREPARE_BACKUP** with set name
2. **Daemon processes preparation:**
   - If both C and O exist:
     - Creates a diff archive capturing changes between C and O
     - Syncs O to match C (using `rsync --delete`)
   - If only C exists:
     - Creates empty O directory
   - If neither exist:
     - Creates both C and O directories (first backup)
3. **Client performs rsync** to daemon's C directory
4. **Client sends BACKUP_COMPLETE** notification

## Security Considerations

- The daemon listens on TCP without built-in encryption
- Use SSH tunnels or VPN for secure communication over untrusted networks
- Run the daemon as a dedicated user with limited permissions
- Restrict access using firewall rules (iptables/ufw)
- The daemon accepts connections from any client - implement network-level access control

## Troubleshooting

### Port Already in Use

If port 7890 is already in use, specify a different port:

```bash
blzbakd --port 7891
```

### Permission Denied on /blzbak

The daemon needs write access to the base_path. Either:
- Change the base_path to a location where the user has permissions
- Create the directory and set appropriate permissions:
  ```bash
  sudo mkdir -p /blzbak
  sudo chown backup:backup /blzbak
  ```

### Connection Refused from Client

Check:
1. Daemon is running: `ps aux | grep blzbakd`
2. Listening on correct port: `sudo netstat -tlnp | grep 7890`
3. Firewall allows connections: `sudo ufw status`
4. Client is connecting to correct host/port

### Check Logs

Increase logging verbosity for debugging:

```bash
blzbakd --log-level DEBUG
```

## Development

### Running Tests

```bash
pytest tests/test_daemon.py -v
```

### Architecture

- `daemon/config.py` - Configuration loading and management
- `daemon/storage.py` - Backup storage and filesystem operations
- `daemon/handler.py` - Protocol command handler
- `daemon/server.py` - Multi-threaded TCP server
- `daemon/cli.py` - Command-line interface

## See Also

- `blzbak` - Client CLI utility
- [Protocol Documentation](../blzbak/protocol.py)
- [Project README](../README.md)
