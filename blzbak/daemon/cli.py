"""Command-line interface for blzbakd daemon."""

import argparse
import logging
import signal
import sys
from pathlib import Path

from .config import DaemonConfig
from .server import DaemonServer


# Global server instance for signal handling
_server = None


def setup_logging(level: str):
    """Configure logging for the daemon."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _server
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, shutting down...")
    if _server:
        _server.stop()
    sys.exit(0)


def main():
    """Main entry point for blzbakd."""
    global _server
    
    parser = argparse.ArgumentParser(
        prog="blzbakd",
        description="blzbak backup server daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  blzbakd                           # Start daemon with default config
  blzbakd --config /etc/blzbak/daemon.config
  blzbakd --port 8000 --base-path /mnt/backups
  blzbakd --log-level DEBUG

Configuration:
  The daemon looks for a .config file in the same directory as the
  executable, or uses the path specified with --config.
  
  Default values:
    - base_path: /blzbak
    - port: 7890
    - host: 0.0.0.0 (listen on all interfaces)
    - log_level: INFO
""",
    )
    
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="Path to daemon configuration file (YAML)",
    )
    
    parser.add_argument(
        "--base-path",
        metavar="PATH",
        help="Override base backup storage path",
    )
    
    parser.add_argument(
        "--port",
        type=int,
        metavar="PORT",
        help="Override TCP port to listen on",
    )
    
    parser.add_argument(
        "--host",
        metavar="HOST",
        help="Override host/interface to bind to",
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level",
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="blzbakd 0.1.0",
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = DaemonConfig.load(args.config)
    
    # Apply command-line overrides
    if args.base_path:
        config.base_path = args.base_path
        # Recalculate diff_dir based on new base_path
        config.diff_dir = str(Path(config.base_path) / "diffs")
        Path(config.base_path).mkdir(parents=True, exist_ok=True)
        Path(config.diff_dir).mkdir(parents=True, exist_ok=True)
    
    if args.port:
        config.port = args.port
    
    if args.host:
        config.host = args.host
    
    if args.log_level:
        config.log_level = args.log_level
    
    # Setup logging
    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)
    
    # Log configuration
    logger.info("=" * 60)
    logger.info("blzbakd - Backup Server Daemon")
    logger.info("=" * 60)
    logger.info(f"Configuration:")
    for key, value in config.to_dict().items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * 60)
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start server
    try:
        _server = DaemonServer(config)
        _server.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
