# Server-Side Backup Set Creation

## Overview

When creating a backup set with `blzbak set create`, the client now connects to the server first to create the backup set structure and metadata before configuring locally.

## What Gets Created on the Server

When you run:
```bash
blzbak set create mybackup /home/user/documents /home/user/photos --schedule "0 3 * * *"
```

The server creates:
```
/blzbak/mybackup/
├── C/                    # Current snapshot directory (empty initially)
├── O/                    # Once-removed snapshot directory (empty initially)
└── metadata.yaml         # Backup set metadata and configuration
```

## Metadata File Contents

The `metadata.yaml` file stores comprehensive information about the backup set:

```yaml
name: mybackup
created_at: '2026-07-30T12:34:56.789012+00:00'
updated_at: '2026-07-30T12:34:56.789012+00:00'
command_line: blzbak set create mybackup /home/user/documents /home/user/photos --schedule 0 3 * * *
source_paths:
  - /home/user/documents
  - /home/user/photos
schedule: 0 3 * * *
exclude_patterns:
  - '*.tmp'
  - '.cache/'
  - '__pycache__/'
server:
  host: backup-server.example.com
  port: 7890
  dest_path: /blzbak/mybackup
```

### Metadata Fields

- **name**: Backup set identifier
- **created_at**: ISO 8601 timestamp of when the set was created
- **updated_at**: ISO 8601 timestamp of last update
- **command_line**: The exact command used to create the backup set (for reference/recovery)
- **source_paths**: List of directories being backed up from the client
- **schedule**: Cron schedule expression for automated backups
- **exclude_patterns**: File patterns to exclude from backups
- **server**: Server connection details

## Creation Flow

1. **Client connects to server** - Validates server is accessible
2. **Server creates structure**:
   - Creates `/blzbak/<set_name>/` directory
   - Creates `C/` and `O/` snapshot directories
   - Writes `metadata.yaml` with full configuration
3. **Client saves local config** - Creates YAML file in local `sets/` directory
4. **Client installs cron job** - Sets up automated backup schedule

## Benefits

- **Auditability**: Server maintains record of when and how each backup set was created
- **Recovery**: Complete backup configuration stored on server for disaster recovery
- **Consistency**: Ensures server directories exist before first backup runs
- **Transparency**: Easy to inspect what's configured by reading metadata.yaml on server
- **History**: Command line shows exactly how the backup was originally configured

## Failure Handling

If server creation fails:
- Server automatically cleans up any partially created directories
- Client does not save local configuration
- No cron job is installed
- User receives clear error message

If server is not configured (no host in config):
- Client shows warning: "No server configured. Backup set created locally only."
- Local configuration is still saved
- Cron job is still installed (for manual backups or future server setup)

## Example Output

```
$ blzbak set create mybackup /home/user/docs --schedule "0 2 * * *"
Connecting to server backup.example.com:7890...
Creating backup set 'mybackup' on remote server...
Successfully created backup set 'mybackup' on server.

Created on server:
  - Set directory: /blzbak/mybackup
  - C snapshot directory: /blzbak/mybackup/C
  - O snapshot directory: /blzbak/mybackup/O
  - Metadata file: /blzbak/mybackup/metadata.yaml

Backup set 'mybackup' configuration saved locally.
Cron job installed: 0 2 * * *
```

## Viewing Metadata on Server

If you have shell access to the backup server:

```bash
# View metadata for a backup set
cat /blzbak/mybackup/metadata.yaml

# List all backup sets with their creation dates
for set in /blzbak/*/metadata.yaml; do
  echo "=== $(dirname $set | basename) ==="
  grep -E '^(created_at|command_line):' "$set"
done
```

## Protocol Command

The feature uses the new `CREATE_SET` protocol command:

```python
# Client sends:
{
    "cmd": "CREATE_SET",
    "set_name": "mybackup",
    "metadata": {
        "command_line": "blzbak set create ...",
        "source_paths": ["/home/user/docs"],
        "schedule": "0 2 * * *",
        "exclude_patterns": ["*.tmp"],
        "server": {...}
    }
}

# Server responds:
{
    "status": "ok",
    "message": "Backup set 'mybackup' created successfully",
    "details": {
        "set_name": "mybackup",
        "set_path": "/blzbak/mybackup",
        "created_items": [
            "Set directory: /blzbak/mybackup",
            "C snapshot directory: /blzbak/mybackup/C",
            "O snapshot directory: /blzbak/mybackup/O",
            "Metadata file: /blzbak/mybackup/metadata.yaml"
        ],
        "metadata_path": "/blzbak/mybackup/metadata.yaml"
    }
}
```
