"""Tests for blzbak.config."""

import textwrap
from pathlib import Path

import pytest

from blzbak.config import load_config, load_ignore_patterns, _deep_merge


def test_load_config_defaults(tmp_path):
    cfg = load_config(config_path=tmp_path / "nonexistent.config")
    assert cfg["server"]["port"]        == 7890
    assert cfg["server"]["host"]        == "localhost"
    assert cfg["server"]["backup_base"] == "/blzbak"
    assert "sets_directory" in cfg


def test_load_config_file_overrides(tmp_path):
    cfg_file = tmp_path / ".config"
    cfg_file.write_text(textwrap.dedent("""\
        server:
          host: 192.168.1.100
          port: 8000
          ssh_user: myuser
        log_level: DEBUG
    """))
    cfg = load_config(config_path=cfg_file)
    assert cfg["server"]["host"]     == "192.168.1.100"
    assert cfg["server"]["port"]     == 8000
    assert cfg["server"]["ssh_user"] == "myuser"
    assert cfg["log_level"]          == "DEBUG"
    # Unchanged defaults should survive
    assert cfg["server"]["backup_base"] == "/blzbak"


def test_load_config_partial_override(tmp_path):
    """Only the keys present in the file should be overridden."""
    cfg_file = tmp_path / ".config"
    cfg_file.write_text("server:\n  host: 10.0.0.5\n")
    cfg = load_config(config_path=cfg_file)
    assert cfg["server"]["host"] == "10.0.0.5"
    assert cfg["server"]["port"] == 7890   # default preserved


def test_load_ignore_patterns(tmp_path):
    ig = tmp_path / ".blzbak-ignore"
    ig.write_text(textwrap.dedent("""\
        # Comment line
        *.tmp
        .cache/
        node_modules/
    """))
    patterns = load_ignore_patterns(ignore_path=ig)
    assert patterns == ["*.tmp", ".cache/", "node_modules/"]


def test_load_ignore_patterns_skips_blank_and_comments(tmp_path):
    ig = tmp_path / ".blzbak-ignore"
    ig.write_text("# comment\n\n*.log\n  # indented comment\n*.bak\n")
    patterns = load_ignore_patterns(ignore_path=ig)
    assert patterns == ["*.log", "*.bak"]


def test_load_ignore_patterns_missing(tmp_path):
    patterns = load_ignore_patterns(ignore_path=tmp_path / "nofile")
    assert patterns == []


def test_deep_merge_nested():
    base     = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99, "e": 5}, "f": 6}
    _deep_merge(base, override)
    assert base == {"a": 1, "b": {"c": 99, "d": 3, "e": 5}, "f": 6}


def test_deep_merge_flat():
    base     = {"x": 1, "y": 2}
    override = {"y": 20, "z": 30}
    _deep_merge(base, override)
    assert base == {"x": 1, "y": 20, "z": 30}
