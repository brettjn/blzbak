"""Configuration management for blzbakd daemon.

The daemon config file (.config) should be placed in the same directory
as the daemon executable or can be specified via --config flag.
"""

import os
import yaml
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


DEFAULT_BASE_PATH = "/blzbak"
DEFAULT_PORT = 7890
DEFAULT_HOST = "0.0.0.0"


@dataclass
class DaemonConfig:
    """Configuration for the blzbak daemon."""
    base_path: str = DEFAULT_BASE_PATH
    port: int = DEFAULT_PORT
    host: str = DEFAULT_HOST
    max_workers: int = 4
    log_level: str = "INFO"
    diff_dir: str = field(default="")  # Defaults to {base_path}/diffs

    def __post_init__(self):
        """Set defaults that depend on other fields."""
        if not self.diff_dir:
            self.diff_dir = os.path.join(self.base_path, "diffs")

    @classmethod
    def load(cls, config_path: Optional[str] = None, create_dirs: bool = True) -> "DaemonConfig":
        """Load daemon configuration from file or use defaults.
        
        Args:
            config_path: Path to config file. If None, looks for .config
                        in the directory containing the daemon executable.
            create_dirs: If True, create base_path and diff_dir if they don't exist.
        
        Returns:
            DaemonConfig instance with merged settings.
        """
        config = cls()
        
        if config_path is None:
            # Look for .config next to executable
            exe_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent
            config_path = exe_dir / ".config"
        else:
            config_path = Path(config_path)
        
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    data = yaml.safe_load(f) or {}
                
                # Merge loaded values with defaults
                if "base_path" in data:
                    config.base_path = data["base_path"]
                if "port" in data:
                    config.port = int(data["port"])
                if "host" in data:
                    config.host = data["host"]
                if "max_workers" in data:
                    config.max_workers = int(data["max_workers"])
                if "log_level" in data:
                    config.log_level = data["log_level"].upper()
                if "diff_dir" in data:
                    config.diff_dir = data["diff_dir"]
                else:
                    # Recalculate default diff_dir based on loaded base_path
                    config.diff_dir = os.path.join(config.base_path, "diffs")
                    
            except Exception as e:
                print(f"Warning: Failed to load config from {config_path}: {e}")
                print("Using default configuration")
        
        # Ensure directories exist
        if create_dirs:
            Path(config.base_path).mkdir(parents=True, exist_ok=True)
            Path(config.diff_dir).mkdir(parents=True, exist_ok=True)
        
        return config

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            "base_path": self.base_path,
            "port": self.port,
            "host": self.host,
            "max_workers": self.max_workers,
            "log_level": self.log_level,
            "diff_dir": self.diff_dir,
        }
