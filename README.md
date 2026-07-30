# blzbak — Automated backup system

This repository contains `blzbak`, a small CLI for managing backups and talking to a backup daemon.

**Quick usage**

- Show help (includes where config/ignore are looked for):

```bash
.venv/bin/blzbak --help
```

- Example: list configured sets (client mode):

```bash
.venv/bin/blzbak set list
```

**Config file location**

The CLI looks for configuration in the following places (in order):

- Explicit file passed with `--config FILE`.
- A file named `.config` in the same directory as the `blzbak` executable (i.e. a sibling of `sys.argv[0]`).

The ignore file `.blzbak-ignore` is also searched as a sibling of the executable.

**Config file format**

The config file is YAML. Known fields:

- `server` (mapping)
  - `host`: daemon hostname (default: `localhost`)
  - `port`: daemon port (default: `7890`)
  - `ssh_user`: SSH user for server operations (optional)
  - `ssh_key_path`: path to SSH private key for rsync operations (optional)
  - `backup_base`: base path on server for backup sets (default: `/blzbak`)
- `sets_directory`: directory where backup set definitions live (default: `/etc/blzbak`)
- `log_level`: logging level (e.g. `INFO`, `DEBUG`)

Example `.config`:

```yaml
server:
  host: 192.168.1.100
  port: 7890
  ssh_user: backup
  ssh_key_path: /home/user/.ssh/id_rsa
  backup_base: /blzbak
sets_directory: /opt/blzbak/sets
log_level: INFO
```

**SSH Key Override**

You can override the SSH key path on the command line for any backup or restore operation:

```bash
blzbak --ssh-key /path/to/custom_key backup run MYBACKUP
blzbak --ssh-key ~/.ssh/special_key restore file MYBACKUP /path/to/file
```

**Ignore file**

`.blzbak-ignore` is a simple newline-separated file. Lines starting with `#` are comments. Non-empty, non-comment lines are treated as ignore patterns.

**Defaults**

- Default daemon port: `7890`
- Default backup base: `/blzbak`
- Default sets directory: `/etc/blzbak`

If you want the help text to include other paths or examples, tell me what to add.
