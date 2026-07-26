"""Tests for Houdini-side startup health checks."""

from __future__ import annotations

# Built-in
import os
import sys

# Third-party
import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "houdini", "scripts", "python"),
)

from fxhoudinimcp_server import startup  # noqa: E402


@pytest.fixture(autouse=True)
def reset_startup_state(monkeypatch):
    monkeypatch.setattr(startup, "_server_started", False)
    monkeypatch.setattr(startup, "_port", 8100)
    monkeypatch.setattr(startup, "_validation_thread", None)


def test_wait_for_current_process_health_accepts_current_pid(monkeypatch):
    monkeypatch.setattr(
        startup,
        "_query_health",
        lambda port: {
            "status": "ok",
            "pid": os.getpid(),
            "houdini_version": "21.0.631",
        },
    )

    health = startup._wait_for_current_process_health(8100)

    assert health is not None
    assert health["pid"] == os.getpid()


def test_hwebserver_binds_to_loopback_by_default(monkeypatch):
    monkeypatch.delenv("FXHOUDINIMCP_BIND_HOST", raising=False)

    assert startup._hwebserver_settings() == {"ADDRESS": "127.0.0.1"}


def test_hwebserver_bind_host_can_be_overridden(monkeypatch):
    monkeypatch.setenv("FXHOUDINIMCP_BIND_HOST", "192.0.2.10")

    assert startup._hwebserver_settings() == {"ADDRESS": "192.0.2.10"}


def test_ensure_running_keeps_started_server_without_blocking_probe(monkeypatch):
    calls = []
    monkeypatch.setattr(startup, "_server_started", True)
    monkeypatch.setattr(
        startup,
        "_wait_for_current_process_health",
        lambda *args, **kwargs: pytest.fail(
            "ensure_running must not block Houdini's UI thread with HTTP"
        ),
    )
    monkeypatch.setattr(startup, "start", lambda: calls.append("start"))

    startup.ensure_running()

    assert calls == []


def test_background_validation_marks_current_process_ready(monkeypatch):
    monkeypatch.setattr(startup, "_server_started", True)
    monkeypatch.setattr(
        startup,
        "_wait_for_current_process_health",
        lambda port: {
            "status": "ok",
            "pid": os.getpid(),
            "houdini_version": "22.0.368",
        },
    )

    startup._validate_health_in_background(8100)
    startup._validation_thread.join(timeout=1)

    assert startup._server_started is True


def test_background_validation_rejects_another_houdini_process(monkeypatch):
    monkeypatch.setattr(startup, "_server_started", True)
    monkeypatch.setattr(
        startup,
        "_wait_for_current_process_health",
        lambda port: {"status": "ok", "pid": os.getpid() + 1},
    )

    startup._validate_health_in_background(8100)
    startup._validation_thread.join(timeout=1)

    assert startup._server_started is False
