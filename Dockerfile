# Dockerfile for blzbak backup server daemon
FROM python:3.10-slim

# Build argument for user ID (defaults to 1000, can be overridden)
ARG USER_ID=1000

# Install rsync (required for backup operations)
RUN apt-get update && \
    apt-get install -y rsync && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user for running the daemon
# Uses USER_ID build argument to match host user
RUN useradd -m -u ${USER_ID} -s /bin/bash blzbak

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml LICENSE ./
COPY blzbak/ ./blzbak/
COPY bin/ ./bin/

# Install the package
RUN pip install --no-cache-dir -e .

# Create backup directories
RUN mkdir -p /blzbak/diffs && \
    chown -R blzbak:blzbak /blzbak

# Switch to non-root user
USER blzbak

# Expose the daemon port
EXPOSE 7890

# Set environment variable for config location
ENV BLZBAK_CONFIG=/app/daemon.config

# Default command runs the daemon
CMD ["blzbakd", "--config", "/app/daemon.config"]
