"""Server startup and lifecycle management.

Handles starting/stopping the hwebserver and loading handler modules.
"""

from __future__ import annotations

# Built-in
import json
import os
import threading
import time
import urllib.parse
import urllib.request

_server_started = False
_port = 8100
_validation_thread = None


def _hwebserver_settings() -> dict[str, str]:
    """Return secure-by-default settings for Houdini's HTTP listener."""
    bind_host = os.environ.get(
        "FXHOUDINIMCP_BIND_HOST", "127.0.0.1"
    ).strip()
    return {"ADDRESS": bind_host or "127.0.0.1"}


def _health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/api"


def _health_body() -> bytes:
    return urllib.parse.urlencode(
        {"json": json.dumps(["mcp.health", [], {}])}
    ).encode("utf-8")


def _query_health(port: int, timeout: float = 0.5) -> dict | None:
    request = urllib.request.Request(
        _health_url(port),
        data=_health_body(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except Exception:
        return None

    try:
        data = json.loads(payload)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _wait_for_current_process_health(
    port: int,
    timeout_seconds: float = 3.0,
) -> dict | None:
    deadline = time.time() + max(0.0, timeout_seconds)
    current_pid = os.getpid()
    last_health = None
    while time.time() < deadline:
        health = _query_health(port)
        if health is not None:
            last_health = health
            if health.get("pid") == current_pid:
                return health
        time.sleep(0.1)
    return last_health


def _validate_health_in_background(port: int) -> None:
    """Validate the GUI web server after the UI thread is released.

    Houdini's GUI serves Python hwebserver handlers through its UI event
    loop.  Performing the HTTP health request synchronously from
    ``uiready.py`` blocks that same loop, so the server cannot answer until
    startup returns.  Run the validation on a worker instead.
    """
    global _server_started, _validation_thread

    def _validate() -> None:
        global _server_started

        health = _wait_for_current_process_health(port)
        if health is None:
            if _port == port:
                _server_started = False
            print(
                f"[fxhoudinimcp] Server on port {port} did not answer mcp.health"
            )
            return

        health_pid = health.get("pid")
        if health_pid != os.getpid():
            if _port == port:
                _server_started = False
            print(
                f"[fxhoudinimcp] Server validation failed: port {port} is owned by "
                f"Houdini pid {health_pid}, current pid {os.getpid()}"
            )
            return

        print(
            "[fxhoudinimcp] Server ready on port {} "
            "(Houdini {}, pid {})".format(
                port,
                health.get("houdini_version", "unknown"),
                health_pid,
            )
        )

    _validation_thread = threading.Thread(
        target=_validate,
        name="fxhoudinimcp-health",
        daemon=True,
    )
    _validation_thread.start()


def start(port: int | None = None) -> None:
    """Start the FXHoudini-MCP server.

    Registers all command handlers and ensures hwebserver is running.

    Args:
        port: Port for hwebserver. Defaults to FXHOUDINIMCP_PORT env var or 8100.
    """
    global _server_started, _port

    if _server_started:
        print("[fxhoudinimcp] Server already running")
        return

    _port = port or int(os.environ.get("FXHOUDINIMCP_PORT", "8100"))

    import hwebserver

    # Import handlers and the web app to trigger command/API registration.
    from fxhoudinimcp_server import (
        handlers,  # noqa: F401
        hwebserver_app,  # noqa: F401
    )

    # Start hwebserver if not already running. In Houdini 20.5+ it may already
    # be running for built-in features; hwebserver.run() is idempotent for that
    # case and raises when the requested port cannot be bound.
    hwebserver.run(
        _port,
        debug=False,
        settings=_hwebserver_settings(),
    )
    _server_started = True
    _validate_health_in_background(_port)


def stop() -> None:
    """Stop the FXHoudini-MCP server."""
    global _server_started
    if not _server_started:
        return

    # Note: we don't call hwebserver.requestShutdown() because that would
    # kill Houdini's built-in web server too. We just mark ourselves as stopped.
    _server_started = False
    print("[fxhoudinimcp] Server stopped")


def is_running() -> bool:
    """Check if the server is currently running."""
    return _server_started


def get_port() -> int:
    """Get the port the server is running on."""
    return _port


def ensure_running() -> None:
    """Start the server if it's not already running."""
    if _server_started:
        return
    start()
