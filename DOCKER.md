# Docker Deployment Guide for blzbak

This guide explains how to deploy the blzbak backup server daemon using Docker.

## Quick Start

### Prerequisites

Ensure Docker is installed and your user has permission to run Docker commands:

```bash
# Check if you're in the docker group
groups

# If 'docker' is not listed, add your user to the docker group:
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker

# Verify Docker works without sudo:
docker ps
```

### Setup Steps

1. **Copy the Docker configuration template:**
   ```bash
   cp daemon.config.docker daemon.config
   ```
   
   Or if using the example config:
   ```bash
   cp daemon.config.example daemon.config
   ```

2. **Edit the configuration** (if needed):
   ```bash
   nano daemon.config
   ```
   
   **Critical settings for Docker:**
   - `base_path`: **MUST be `/blzbak`** (this is where Docker mounts the volume inside the container)
   - `port`: `7890` (default, mapped in docker-compose.yml)
   - `host`: `0.0.0.0` (listen on all interfaces to accept external connections)
   
   ⚠️ **Common mistake:** Do NOT use `/mnt/blzbak` or any other path for `base_path`. Inside the Docker container, the volume is always at `/blzbak`.

3. **Build and start the container:**
   ```bash
   docker-compose up -d
   ```
   
   > **Note:** If you get a "Permission denied" error, you need to add your user to the docker group:
   > ```bash
   > sudo usermod -aG docker $USER
   > newgrp docker
   > ```
   > Then try the command again.

4. **Verify the daemon is running:**
   ```bash
   # Check container status
   docker-compose ps
   
   # The output should show the blzbak-daemon container as "Up"
   ```
   
   > **Important:** The daemon runs in Docker, NOT as a systemd service. Don't use `systemctl status blzbakd` - it won't work!

5. **Check the logs:**
   ```bash
   docker-compose logs -f
   ```

6. **Test the connection (from a client machine):**
   ```bash
   # Note: --server and --port must come BEFORE the test command
   blzbak --server YOUR_SERVER_IP --port 7890 test
   ```

## Docker Compose Configuration

The `docker-compose.yml` file includes:
- Port mapping: `7890:7890` (daemon TCP port)
- Volume mounts:
  - `/mnt/blzbak:/blzbak` - Backup storage on ZFS RAID (host path : container path)
  - `./daemon.config:/app/daemon.config:ro` - Configuration file (read-only)

**Important:** The format is `HOST_PATH:CONTAINER_PATH`. 
- **Right side** (`/blzbak`): What you reference in `daemon.config` (always `/blzbak`)
- **Left side** (`/mnt/blzbak`): Where files are actually stored on your host

### Customizing Backup Storage Location

If your backup storage is in a different location, edit `docker-compose.yml` and change the LEFT side (host path):

```yaml
volumes:
  - /your/storage/path:/blzbak  # Change left side only!
  - ./daemon.config:/app/daemon.config:ro
```

**Examples:**
```yaml
# For ZFS RAID volume at /mnt/blzbak (default in docker-compose.yml)
- /mnt/blzbak:/blzbak

# For local directory
- ./backups:/blzbak

# For mounted NFS share
- /mnt/nfs-backups:/blzbak

# For different ZFS pool
- /tank/backups:/blzbak
```

**Remember:** Your `daemon.config` should ALWAYS use `base_path: /blzbak` (the container path), regardless of where files are stored on the host.

## Manual Docker Commands

### Build the image:
```bash
docker build -t blzbak:latest .
```

### Run the container:
```bash
docker run -d \
  --name blzbak-daemon \
  -p 7890:7890 \
  -v $(pwd)/backups:/blzbak \
  -v $(pwd)/daemon.config:/app/daemon.config:ro \
  --restart unless-stopped \
  blzbak:latest
```

### View logs:
```bash
docker logs -f blzbak-daemon
```

### Stop the container:
```bash
docker stop blzbak-daemon
```

### Remove the container:
```bash
docker rm blzbak-daemon
```

## Management Commands

### Check if the daemon is running:
```bash
# Check container status with docker-compose
docker-compose ps

# Or check with docker directly
docker ps | grep blzbak

# View detailed container status
docker inspect blzbak-daemon
```

**Important:** The daemon runs inside a Docker container, not as a systemd service. Do NOT use `systemctl status blzbakd` - that won't work. Use the Docker commands above instead.

### Start the daemon:
```bash
docker-compose up -d
```

### Stop the daemon:
```bash
docker-compose down
```

### Restart the daemon:
```bash
docker-compose restart
```

### View logs (follow mode):
```bash
docker-compose logs -f blzbakd
```

### View recent logs:
```bash
docker-compose logs --tail=100 blzbakd
```

### Access the container shell:
```bash
docker-compose exec blzbakd bash
```

### Update the daemon:
```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Backup Storage Structure

Inside the container, backups are stored at `/blzbak`:
```
/blzbak/
├── backup_set_1/
│   ├── C/          # Current backup
│   ├── O/          # Once-removed backup
│   └── metadata.yaml
├── backup_set_2/
│   ├── C/
│   ├── O/
│   └── metadata.yaml
└── diffs/          # Differential archives
    ├── backup_set_1/
    └── backup_set_2/
```

This directory is mapped to `./backups` on your host (or wherever you configured it).

## Security Considerations

1. **Firewall**: Ensure port 7890 is only accessible from trusted networks
2. **Volume Permissions**: The container runs as user `blzbak` (UID 1000)
3. **Config File**: Keep `daemon.config` secure, especially if you add authentication
4. **Backup Directory**: Ensure the host backup directory has appropriate permissions

### Understanding User and Permission Mapping:

The Docker container creates and runs as user `blzbak` inside the container. The UID of this user is configurable via the `USER_ID` build argument in `docker-compose.yml` (defaults to 1000). When the container writes to `/blzbak` (inside the container), it's actually writing to your host directory (e.g., `/mnt/blzbak`) with this UID.

**For this to work properly:**

#### Step 1: Find your host blzbak user's UID:
```bash
id -u blzbak
# Output: 997 (or whatever your UID is)
```

#### Step 2: Update docker-compose.yml to match:

Edit `docker-compose.yml` and set `USER_ID` to match your host blzbak user:

```yaml
services:
  blzbakd:
    build:
      context: .
      args:
        USER_ID: 997  # Change this to match your host blzbak UID
```

#### Step 3: Ensure proper ownership on host:
```bash
# For ZFS volume or mount point
sudo chown -R blzbak:blzbak /mnt/blzbak
sudo chmod 755 /mnt/blzbak

# For local directory
sudo chown -R blzbak:blzbak ./backups
sudo chmod 755 ./backups
```

#### Step 4: Build and start:
```bash
# Build with the correct UID
docker-compose build --no-cache

# Start the container
docker-compose up -d
```

#### Step 5: Verify permissions:
```bash
ls -ld /mnt/blzbak
# Should show: drwxr-xr-x ... blzbak blzbak ... /mnt/blzbak
```

**Note:** If you change the `USER_ID` after already building the image, you MUST rebuild with `docker-compose build --no-cache` for the change to take effect.

## Verifying the Installation

After starting the container, verify everything is working:

### 1. Check Container Status:
```bash
# Using docker-compose
docker-compose ps

# Expected output shows "Up" status:
#      Name                 Command           State           Ports         
# --------------------------------------------------------------------------
# blzbak-daemon   blzbakd --config ...   Up      0.0.0.0:7890->7890/tcp
```

### 2. Check Daemon Logs:
```bash
docker-compose logs blzbakd

# You should see output like:
# blzbak.daemon.cli: blzbakd - Backup Server Daemon
# blzbak.daemon.server: blzbakd listening on 0.0.0.0:7890
```

### 3. Test Connection from Client:
```bash
# From any machine with blzbak installed, test the connection
# Note: --server and --port must come BEFORE the test command
blzbak --server YOUR_SERVER_IP --port 7890 test

# Example with actual IP:
blzbak --server 10.0.0.177 --port 7890 test

# This will display daemon configuration and confirm connectivity
```

### 4. Test from Server Itself:
```bash
# Install blzbak client if needed
# Then test local connection
blzbak --server localhost --port 7890 test
```

## Troubleshooting

### Daemon Not Running ("systemctl status blzbakd" shows nothing):

**This is normal!** When running in Docker, the daemon is NOT a systemd service. 

**Solution:** Use Docker commands instead:
```bash
# Check if container is running
docker-compose ps

# View container logs
docker-compose logs -f blzbakd
```

### Docker Permission Denied Error:

**Symptom:** Getting `PermissionError: [Errno 13] Permission denied` when running `docker-compose` or `docker` commands.

**Solution:**
```bash
# Add your user to the docker group
sudo usermod -aG docker $USER

# Log out and back in for changes to take effect, or run:
newgrp docker

# Verify it works
docker ps
```

**Alternative:** Run commands with sudo (not recommended for regular use):
```bash
sudo docker-compose up -d
```

### Container won't start:
```bash
# Check logs
docker-compose logs blzbakd

# Verify config file exists
ls -l daemon.config

# Check port availability
sudo netstat -tlnp | grep 7890
```

### Container keeps restarting - "Permission denied: '/mnt/blzbak'" or similar path error:

**Symptom:** Container status shows "Restarting", and logs show:
```
PermissionError: [Errno 13] Permission denied: '/mnt/blzbak'
```

**Cause:** The `base_path` in your `daemon.config` doesn't match where Docker mounts the volume.

**Solution:** Edit your `daemon.config` file to use `/blzbak` (the path INSIDE the container):

```yaml
# daemon.config - Use /blzbak (the container path), NOT /mnt/blzbak
base_path: /blzbak
port: 7890
host: 0.0.0.0
max_workers: 4
log_level: INFO
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

**Important:** Inside the container, the volume is always mounted at `/blzbak`, regardless of where it's located on your host machine. Your `daemon.config` must use `/blzbak`.

### Permission errors when writing to backup directory:

**Symptom:** Container keeps restarting with "Permission denied" errors when trying to write to the backup directory.

**Cause:** UID mismatch between the container user and the host directory ownership.

**Solution:**

1. Find your host blzbak user's UID:
   ```bash
   id -u blzbak
   # Example output: 997
   ```

2. Update `docker-compose.yml` to use the correct UID:
   ```yaml
   services:
     blzbakd:
       build:
         context: .
         args:
           USER_ID: 997  # Use your actual UID here
   ```

3. Ensure host directory is owned by your blzbak user:
   ```bash
   sudo chown -R blzbak:blzbak /mnt/blzbak
   sudo chmod 755 /mnt/blzbak
   ```

4. Rebuild and restart:
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

### Connection refused:
- Verify the container is running: `docker-compose ps`
- Check firewall rules on the host
- Ensure port 7890 is exposed in docker-compose.yml

### Rebuild after changes:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Production Deployment

For production use, consider:

1. **Use explicit volume paths** instead of relative paths
2. **Set up log rotation** for Docker logs
3. **Configure resource limits** in docker-compose.yml (CPU, memory)
4. **Use Docker secrets** for sensitive configuration
5. **Set up monitoring** (e.g., with Prometheus/Grafana)
6. **Configure backup retention policies**
7. **Set up regular health checks**

### Example production docker-compose.yml snippet:
```yaml
services:
  blzbakd:
    build: .
    restart: always
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 512M
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; s = socket.socket(); s.connect(('localhost', 7890)); s.close()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Environment Variables

You can override configuration with environment variables:

```yaml
environment:
  - BLZBAK_PORT=7890
  - BLZBAK_HOST=0.0.0.0
  - BLZBAK_BASE_PATH=/blzbak
  - BLZBAK_LOG_LEVEL=INFO
```

Note: The daemon needs to be modified to support environment variable overrides.
