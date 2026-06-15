"""Tests for blzbak.models."""

import pytest

from blzbak.models import BackupSet, ServerConfig, validate_set_name


# ---------------------------------------------------------------------------
# validate_set_name
# ---------------------------------------------------------------------------

def test_validate_set_name_valid():
    assert validate_set_name("my-backup")  == "my-backup"
    assert validate_set_name("docs_2026")  == "docs_2026"
    assert validate_set_name("HOME")       == "HOME"
    assert validate_set_name("x")          == "x"


def test_validate_set_name_invalid():
    for bad in ("my backup", "../evil", "foo/bar", "a b", "", "with spaces"):
        with pytest.raises(ValueError):
            validate_set_name(bad)


# ---------------------------------------------------------------------------
# ServerConfig
# ---------------------------------------------------------------------------

def test_rsync_dest_with_user():
    srv = ServerConfig(host="192.168.1.1", ssh_user="backup", dest_path="/blzbak/docs")
    assert srv.rsync_dest("C") == "backup@192.168.1.1:/blzbak/docs/C"
    assert srv.rsync_dest("O") == "backup@192.168.1.1:/blzbak/docs/O"


def test_rsync_dest_without_user():
    srv = ServerConfig(host="192.168.1.1", dest_path="/blzbak/docs")
    assert srv.rsync_dest("C") == "192.168.1.1:/blzbak/docs/C"


def test_server_config_roundtrip():
    srv = ServerConfig(host="10.0.0.5", port=8000, ssh_user="bak", dest_path="/data/x")
    restored = ServerConfig.from_dict(srv.to_dict())
    assert restored.host      == srv.host
    assert restored.port      == srv.port
    assert restored.ssh_user  == srv.ssh_user
    assert restored.dest_path == srv.dest_path


# ---------------------------------------------------------------------------
# BackupSet
# ---------------------------------------------------------------------------

def _make_bs() -> BackupSet:
    srv = ServerConfig(host="10.0.0.1", port=7890, ssh_user="bak", dest_path="/blzbak/test")
    return BackupSet(
        name             = "test",
        source_paths     = ["/home/user/docs", "/home/user/photos"],
        server           = srv,
        schedule         = "0 3 * * *",
        exclude_patterns = ["*.tmp", ".cache/"],
    )


def test_backup_set_to_dict_keys():
    d = _make_bs().to_dict()
    for key in ("name", "version", "created_at", "updated_at",
                "source_paths", "schedule", "server", "exclude_patterns"):
        assert key in d, f"Missing key: {key}"


def test_backup_set_roundtrip():
    bs = _make_bs()
    d  = bs.to_dict()
    r  = BackupSet.from_dict(d)
    assert r.name             == bs.name
    assert r.source_paths     == bs.source_paths
    assert r.schedule         == bs.schedule
    assert r.exclude_patterns == bs.exclude_patterns
    assert r.server.host      == bs.server.host
    assert r.server.ssh_user  == bs.server.ssh_user
    assert r.server.dest_path == bs.server.dest_path
