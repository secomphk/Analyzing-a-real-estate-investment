"""Tests for the logging redactor."""

from __future__ import annotations

from src.core.logging import _sanitize


def test_redacts_top_level_sensitive_keys() -> None:
    event = {
        "event": "login",
        "password": "hunter2",
        "user": "alice",
        "api_key": "abc123",
    }
    out = _sanitize(None, "info", event)
    assert out["password"] == "***redacted***"
    assert out["api_key"] == "***redacted***"
    assert out["user"] == "alice"


def test_redacts_nested_dict_keys() -> None:
    event = {
        "event": "external_call",
        "headers": {"Authorization": "Bearer abc", "X-Trace-Id": "t-1"},
    }
    out = _sanitize(None, "info", event)
    assert out["headers"]["Authorization"] == "***redacted***"
    assert out["headers"]["X-Trace-Id"] == "t-1"


def test_passthrough_when_no_sensitive_keys() -> None:
    event = {"event": "ok", "duration_ms": 12.3}
    out = _sanitize(None, "info", event)
    assert out == event


def test_substring_match_is_case_insensitive() -> None:
    event = {"AccessKey": "AKIA...", "AuthToken": "abc"}
    out = _sanitize(None, "info", event)
    assert out["AccessKey"] == "***redacted***"
    assert out["AuthToken"] == "***redacted***"
