# Docker Deployment Guide for blzbak

This guide explains how to deploy the blzbak backup server daemon using Docker.

## Quick Start

1. **Copy the example configuration:**
   ```bash
   cp daemon.config.example daemon.config
   ```

2. **Edit the configuration** (optional):
   ```bash
   nano daemon.config
   ```
   
   Key settings:
   - `base_path`: `/blzbak` (already mapped to volume)
   - `port`: `7890` (default)
   - `host`: `0.0.0.0` (listen on all interfaces)

3. **Build and start the container:**
   ```bash
   docker-compose up -d
   ```

4. **Check the logs:**
   ```bash
   docker-compose logs -f
   ```

## Docker Compose Configuration

The `docker-compose.yml` file includes:
- Port mapping: `7890:7890` (daemon TCP port)
- Volume mounts:
  - `./backups:/blzbak` - Backup storage (create this directory)
  - `./daemon.config:/app/daemon.config:ro` - Configuration file

### Customizing Backup Storage Location

Edit `docker-compose.yml` and change the volume path:
```yaml
volumes:
  - /path/to/your/backup/storage:/blzbak
```

For example, to use `/mnt/backups`:
```yaml
volumes:
  - /mnt/backups:/blzbak
  - ./daemon.config:/app/daemon.config:ro
```

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

### Setting up host directory permissions:
```bash
mkdir -p backups
sudo chown -R 1000:1000 backups
chmod 755 backups
```

## Testing the Connection

From a client machine with `blzbak` installed:

```bash
# Create a backup set configuration pointing to your Docker host
blzbak set create mybackup \
  --source /path/to/backup \
  --dest server://YOUR_DOCKER_HOST_IP:7890/mybackup

# Run a backup
blzbak backup mybackup
```

## Troubleshooting

### Container won't start:
```bash
# Check logs
docker-compose logs blzbakd

# Verify config file exists
ls -l daemon.config

# Check port availability
sudo netstat -tlnp | grep 7890
```

### Permission errors:
```bash
# Fix backup directory permissions
sudo chown -R 1000:1000 ./backups
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
