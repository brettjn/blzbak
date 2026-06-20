"""Tests for blzbakd daemon components."""

import os
import tempfile
import pytest
from pathlib import Path

from blzbak.daemon.config import DaemonConfig, DEFAULT_BASE_PATH, DEFAULT_PORT
from blzbak.daemon.storage import StorageManager, SnapshotInfo
from blzbak.daemon.handler import ProtocolHandler
from blzbak.protocol import Command


# ------------------------------------------------------------------
# Config tests
# ------------------------------------------------------------------

def test_daemon_config_defaults():
    """Test default daemon configuration."""
    config = DaemonConfig()
    assert config.base_path == DEFAULT_BASE_PATH
    assert config.port == DEFAULT_PORT
    assert config.host == "0.0.0.0"
    assert config.max_workers == 4
    assert config.log_level == "INFO"


def test_daemon_config_load_missing_file():
    """Test loading config when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "nonexistent.config"
        config = DaemonConfig.load(str(config_path), create_dirs=False)
        # Should use defaults
        assert config.base_path == DEFAULT_BASE_PATH
        assert config.port == DEFAULT_PORT


def test_daemon_config_load_from_file():
    """Test loading config from YAML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test.config"
        test_base = Path(tmpdir) / "backups"
        config_path.write_text(f"""
base_path: {test_base}
port: 9999
host: 127.0.0.1
log_level: DEBUG
max_workers: 8
""")
        config = DaemonConfig.load(str(config_path))
        assert config.base_path == str(test_base)
        assert config.port == 9999
        assert config.host == "127.0.0.1"
        assert config.log_level == "DEBUG"
        assert config.max_workers == 8


# ------------------------------------------------------------------
# StorageManager tests
# ------------------------------------------------------------------

@pytest.fixture
def storage():
    """Create a temporary storage manager for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir) / "backups"
        diff_dir = Path(tmpdir) / "diffs"
        yield StorageManager(str(base_path), str(diff_dir))


def test_storage_manager_init(storage):
    """Test storage manager initialization."""
    assert storage.base_path.exists()
    assert storage.diff_dir.exists()


def test_storage_list_sets_empty(storage):
    """Test listing sets when storage is empty."""
    sets = storage.list_sets()
    assert sets == []


def test_storage_list_sets_with_data(storage):
    """Test listing sets after creating some."""
    # Create some backup set directories
    (storage.base_path / "set1" / "C").mkdir(parents=True)
    (storage.base_path / "set2" / "O").mkdir(parents=True)
    (storage.base_path / "notaset").mkdir()  # No C or O subdirs
    
    sets = storage.list_sets()
    assert sorted(sets) == ["set1", "set2"]


def test_storage_get_snapshot_info_missing(storage):
    """Test getting info for a non-existent snapshot."""
    info = storage.get_snapshot_info("testset", "C")
    assert info.label == "C"
    assert not info.exists
    assert info.size_bytes == 0


def test_storage_get_snapshot_info_exists(storage):
    """Test getting info for an existing snapshot."""
    # Create a snapshot with a file
    c_path = storage.base_path / "testset" / "C"
    c_path.mkdir(parents=True)
    (c_path / "testfile.txt").write_text("test content")
    
    info = storage.get_snapshot_info("testset", "C")
    assert info.label == "C"
    assert info.exists
    assert info.size_bytes > 0
    assert info.mtime is not None


def test_storage_list_snapshots(storage):
    """Test listing snapshots for a set."""
    # Create C and O snapshots
    (storage.base_path / "testset" / "C").mkdir(parents=True)
    (storage.base_path / "testset" / "O").mkdir(parents=True)
    
    snapshots = storage.list_snapshots("testset")
    assert len(snapshots) == 2
    labels = [s.label for s in snapshots]
    assert "C" in labels
    assert "O" in labels


def test_storage_prepare_backup_first_time(storage):
    """Test preparing backup for the first time (no existing snapshots)."""
    result = storage.prepare_backup("newset")
    
    assert not result["c_exists"]
    assert not result["o_exists"]
    assert not result["diff_created"]
    assert not result["synced"]
    
    # Directories should be created
    assert (storage.base_path / "newset" / "C").exists()
    assert (storage.base_path / "newset" / "O").exists()


def test_storage_prepare_backup_with_c_only(storage):
    """Test preparing backup when only C exists."""
    # Create C snapshot
    c_path = storage.base_path / "testset" / "C"
    c_path.mkdir(parents=True)
    (c_path / "file1.txt").write_text("content")
    
    result = storage.prepare_backup("testset")
    
    assert result["c_exists"]
    assert not result["o_exists"]
    assert not result["diff_created"]
    assert not result["synced"]
    
    # O should be created
    assert (storage.base_path / "testset" / "O").exists()


def test_storage_list_files(storage):
    """Test listing files in a snapshot."""
    # Create snapshot with files
    c_path = storage.base_path / "testset" / "C"
    c_path.mkdir(parents=True)
    (c_path / "file1.txt").write_text("content1")
    (c_path / "subdir").mkdir()
    (c_path / "subdir" / "file2.txt").write_text("content2")
    
    # List root
    files = storage.list_files("testset", "C", "/")
    assert len(files) == 2
    names = [f["name"] for f in files]
    assert "file1.txt" in names
    assert "subdir" in names
    
    # List subdir
    files = storage.list_files("testset", "C", "/subdir")
    assert len(files) == 1
    assert files[0]["name"] == "file2.txt"


# ------------------------------------------------------------------
# ProtocolHandler tests
# ------------------------------------------------------------------

@pytest.fixture
def handler(storage):
    """Create a protocol handler for testing."""
    return ProtocolHandler(storage)


def test_handler_ping(handler):
    """Test PING command."""
    response = handler.handle_request({"cmd": Command.PING})
    assert response["status"] == "ok"
    assert "message" in response


def test_handler_missing_command(handler):
    """Test request with missing command."""
    response = handler.handle_request({})
    assert response["status"] == "error"
    assert "cmd" in response["message"].lower()


def test_handler_unknown_command(handler):
    """Test request with unknown command."""
    response = handler.handle_request({"cmd": "UNKNOWN"})
    assert response["status"] == "error"
    assert "unknown" in response["message"].lower()


def test_handler_list_sets_empty(handler):
    """Test LIST_SETS with no sets."""
    response = handler.handle_request({"cmd": Command.LIST_SETS})
    assert response["status"] == "ok"
    assert response["sets"] == []


def test_handler_list_sets_with_data(handler, storage):
    """Test LIST_SETS with some sets."""
    (storage.base_path / "set1" / "C").mkdir(parents=True)
    (storage.base_path / "set2" / "C").mkdir(parents=True)
    
    response = handler.handle_request({"cmd": Command.LIST_SETS})
    assert response["status"] == "ok"
    assert len(response["sets"]) == 2
    names = [s["name"] for s in response["sets"]]
    assert "set1" in names
    assert "set2" in names


def test_handler_prepare_backup_missing_set_name(handler):
    """Test PREPARE_BACKUP without set_name."""
    response = handler.handle_request({"cmd": Command.PREPARE_BACKUP})
    assert response["status"] == "error"
    assert "set_name" in response["message"].lower()


def test_handler_prepare_backup_first_time(handler):
    """Test PREPARE_BACKUP for first backup."""
    response = handler.handle_request({
        "cmd": Command.PREPARE_BACKUP,
        "set_name": "newset"
    })
    assert response["status"] == "ok"
    assert "details" in response


def test_handler_backup_complete(handler, storage):
    """Test BACKUP_COMPLETE command."""
    # Create a C snapshot
    c_path = storage.base_path / "testset" / "C"
    c_path.mkdir(parents=True)
    (c_path / "file.txt").write_text("data")
    
    response = handler.handle_request({
        "cmd": Command.BACKUP_COMPLETE,
        "set_name": "testset"
    })
    assert response["status"] == "ok"
    assert "snapshot" in response


def test_handler_list_snapshots(handler, storage):
    """Test LIST_SNAPSHOTS command."""
    # Create snapshots
    (storage.base_path / "testset" / "C").mkdir(parents=True)
    (storage.base_path / "testset" / "O").mkdir(parents=True)
    
    response = handler.handle_request({
        "cmd": Command.LIST_SNAPSHOTS,
        "set_name": "testset"
    })
    assert response["status"] == "ok"
    assert len(response["snapshots"]) == 2


def test_handler_list_files(handler, storage):
    """Test LIST_FILES command."""
    # Create snapshot with files
    c_path = storage.base_path / "testset" / "C"
    c_path.mkdir(parents=True)
    (c_path / "file1.txt").write_text("content")
    
    response = handler.handle_request({
        "cmd": Command.LIST_FILES,
        "set_name": "testset",
        "snapshot": "C",
        "path": "/"
    })
    assert response["status"] == "ok"
    assert len(response["files"]) == 1
    assert response["files"][0]["name"] == "file1.txt"
