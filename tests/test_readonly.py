"""Tests for the read-only guarantees of this fork."""

import os

import pytest

from timetree_exporter.api.calendar import (
    ReadOnlySession,
    ReadOnlyViolationError,
    TimeTreeCalendar,
)
from timetree_exporter.cli import resolve_password


def test_calendar_uses_read_only_session():
    calendar = TimeTreeCalendar("dummy-session-id")
    assert isinstance(calendar.session, ReadOnlySession)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post"])
def test_read_only_session_blocks_write_methods(method):
    session = ReadOnlySession()
    with pytest.raises(ReadOnlyViolationError):
        session.request(method, "https://timetreeapp.com/api/v1/calendar/1/event")


@pytest.mark.parametrize(
    "url",
    [
        "http://timetreeapp.com/api/v1/calendars",
        "https://example.com/api/v1/calendars",
        "https://timetreeapp.com.evil.example/api/v1/calendars",
        "https://eviltimetreeapp.com/",
    ],
)
def test_read_only_session_blocks_non_timetree_urls(url):
    session = ReadOnlySession()
    with pytest.raises(ReadOnlyViolationError):
        session.request("GET", url)


def test_password_file_is_read_when_private(tmp_path, monkeypatch):
    password_file = tmp_path / "pw"
    password_file.write_text("s3cret\n", encoding="utf-8")
    os.chmod(password_file, 0o600)
    monkeypatch.setenv("TIMETREE_PASSWORD_FILE", str(password_file))
    monkeypatch.delenv("TIMETREE_PASSWORD", raising=False)
    assert resolve_password() == "s3cret"


def test_password_file_readable_by_others_is_rejected(tmp_path, monkeypatch):
    password_file = tmp_path / "pw"
    password_file.write_text("s3cret", encoding="utf-8")
    os.chmod(password_file, 0o644)
    monkeypatch.setenv("TIMETREE_PASSWORD_FILE", str(password_file))
    with pytest.raises(PermissionError):
        resolve_password()


def test_keychain_lookup_uses_security_without_shell(monkeypatch):
    calls = []

    class _Result:
        returncode = 0
        stdout = "kc-secret\n"

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return _Result()

    monkeypatch.delenv("TIMETREE_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("TIMETREE_KEYCHAIN_SERVICE", "timetree-exporter")
    monkeypatch.setattr("timetree_exporter.cli.subprocess.run", fake_run)
    assert resolve_password("me@example.com") == "kc-secret"
    command, kwargs = calls[0]
    assert command[0] == "/usr/bin/security"
    assert command[command.index("-a") + 1] == "me@example.com"
    assert "shell" not in kwargs
