"""Tests for blzbak.cron."""

from unittest.mock import patch

import pytest

from blzbak.cron import (
    _make_entry, _set_tag_name,
    install_cron_job, remove_cron_job, list_cron_jobs,
)

_SAMPLE_CRONTAB = (
    "# This is a comment\n"
    "0 2 * * * /usr/local/bin/blzbak backup run documents # blzbak-managed:documents\n"
    "30 3 * * * /usr/local/bin/blzbak backup run photos # blzbak-managed:photos\n"
)


# ---------------------------------------------------------------------------
# _make_entry / _set_tag_name
# ---------------------------------------------------------------------------

def test_make_entry_contains_schedule():
    entry = _make_entry("0 2 * * *", "docs", "/usr/local/bin/blzbak")
    assert entry.startswith("0 2 * * *")


def test_make_entry_contains_command():
    entry = _make_entry("0 2 * * *", "docs", "/usr/local/bin/blzbak")
    assert "/usr/local/bin/blzbak backup run docs" in entry


def test_make_entry_contains_tag():
    entry = _make_entry("0 2 * * *", "docs", "/bin/blzbak")
    assert "# blzbak-managed:docs" in entry


def test_set_tag_name_present():
    line = "0 2 * * * /bin/blzbak backup run docs # blzbak-managed:docs"
    assert _set_tag_name(line) == "docs"


def test_set_tag_name_absent():
    assert _set_tag_name("0 5 * * * /bin/someother") is None


# ---------------------------------------------------------------------------
# list_cron_jobs
# ---------------------------------------------------------------------------

def test_list_cron_jobs():
    with patch("blzbak.cron._get_crontab", return_value=_SAMPLE_CRONTAB):
        jobs = list_cron_jobs()
    assert len(jobs) == 2
    names = {j["set_name"] for j in jobs}
    assert names == {"documents", "photos"}


def test_list_cron_jobs_empty():
    with patch("blzbak.cron._get_crontab", return_value="# only comments\n"):
        jobs = list_cron_jobs()
    assert jobs == []


# ---------------------------------------------------------------------------
# remove_cron_job
# ---------------------------------------------------------------------------

def test_remove_cron_job_found():
    saved: list[str] = []

    with patch("blzbak.cron._get_crontab", return_value=_SAMPLE_CRONTAB), \
         patch("blzbak.cron._set_crontab", side_effect=saved.append):
        removed = remove_cron_job("documents")

    assert removed is True
    result = saved[0]
    assert "blzbak-managed:documents" not in result
    assert "blzbak-managed:photos"    in result


def test_remove_cron_job_not_found():
    with patch("blzbak.cron._get_crontab", return_value=_SAMPLE_CRONTAB), \
         patch("blzbak.cron._set_crontab") as mock_set:
        removed = remove_cron_job("nonexistent")
    assert removed is False
    mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# install_cron_job (idempotent replace)
# ---------------------------------------------------------------------------

def test_install_cron_job_replaces_existing():
    saved: list[str] = []

    with patch("blzbak.cron._get_crontab", return_value=_SAMPLE_CRONTAB), \
         patch("blzbak.cron._set_crontab", side_effect=saved.append):
        install_cron_job("documents", "0 4 * * *", "/bin/blzbak")

    result = saved[0]
    # Old entry removed, new entry added
    assert result.count("blzbak-managed:documents") == 1
    assert "0 4 * * *" in result
    assert "blzbak-managed:photos" in result   # unrelated entry preserved
