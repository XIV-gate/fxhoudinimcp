"""Main-thread dispatch mechanism for executing hou.* calls safely.

Houdini requires all hou.* API calls to run on the main thread.
hwebserver handlers run on worker threads, so we use
hdefereval.executeInMainThreadWithResult() to marshal calls
to the main thread and block until they complete.
"""

from __future__ import annotations

# Built-in
import logging
import threading
import time
import traceback
from collections.abc import Callable
from typing import Any

# Third-party (hdefereval is only available in graphical Houdini sessions)
try:
    import hdefereval
    HAS_HDEFEREVAL = True
except ImportError:
    HAS_HDEFEREVAL = False

# Internal
from fxhoudinimcp_server import journal
from fxhoudinimcp_server.policy import authorize, is_read_only_command

logger = logging.getLogger(__name__)

###### Constants

_COMMAND_TIMEOUT = 120  # seconds

# Registry of command name -> handler function
_handler_registry: dict[str, Callable] = {}


def register_handler(command: str, handler: Callable) -> None:
    """Register a handler function for a command name.

    Args:
        command: Dotted command name (e.g. "scene.get_scene_info")
        handler: Function to call with **params
    """
    _handler_registry[command] = handler


def list_commands() -> list[str]:
    """Return all registered command names."""
    return sorted(_handler_registry.keys())


def dispatch(command: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a command on the main thread and return the result.

    This is called from hwebserver worker threads. It uses
    hdefereval.executeInMainThreadWithResult() to safely execute
    hou.* calls on the main thread.

    Args:
        command: The command name to execute
        params: Parameters to pass to the handler

    Returns:
        A response dict with "status", "data"/"error", and "timing_ms" keys.
    """
    handler = _handler_registry.get(command)
    if handler is None:
        return {
            "status": "error",
            "error": {
                "code": "UNKNOWN_COMMAND",
                "message": f"No handler registered for command: {command}",
                "available_commands": list_commands(),
            },
        }

    clean_params, policy_error = authorize(command, params)
    if policy_error is not None:
        policy_error["timing_ms"] = 0.0
        return policy_error

    start_time = time.time()
    should_journal = (
        not is_read_only_command(command)
        and not command.startswith("audit.")
    )

    def _execute():
        before = None
        if should_journal:
            try:
                before = journal.capture_scene_state(clean_params)
            except Exception:
                logger.debug(
                    "Failed to capture pre-command scene state",
                    exc_info=True,
                )

        execution_start = time.time()
        try:
            handler_result = handler(**clean_params)
            result = {"status": "success", "data": handler_result}
        except Exception as e:
            result = {
                "status": "error",
                "error": {
                    "code": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                },
            }
        if should_journal:
            after = None
            try:
                after = journal.capture_scene_state(clean_params)
            except Exception:
                logger.debug(
                    "Failed to capture post-command scene state",
                    exc_info=True,
                )
            try:
                journal.record(
                    command=command,
                    params=clean_params,
                    success=result["status"] == "success",
                    timing_ms=(time.time() - execution_start) * 1000,
                    before=before,
                    after=after,
                    error=result.get("error"),
                )
            except Exception:
                logger.debug("Failed to record MCP activity", exc_info=True)
        return result

    try:
        if (
            HAS_HDEFEREVAL
            and threading.current_thread() is not threading.main_thread()
        ):
            # Run hdefereval call in a worker thread so we can enforce a timeout
            container: dict[str, Any] = {}

            def _run():
                try:
                    container["result"] = hdefereval.executeInMainThreadWithResult(_execute)
                except Exception as exc:
                    container["error"] = exc
                    container["tb"] = traceback.format_exc()

            worker = threading.Thread(target=_run, daemon=True)
            worker.start()
            worker.join(timeout=_COMMAND_TIMEOUT)

            if worker.is_alive():
                logger.error(
                    "Command '%s' timed out after %s seconds", command, _COMMAND_TIMEOUT
                )
                result = {
                    "status": "error",
                    "error": {
                        "code": "TIMEOUT",
                        "message": (
                            f"Command '{command}' did not complete within "
                            f"{_COMMAND_TIMEOUT} seconds."
                        ),
                    },
                }
            elif "error" in container:
                result = {
                    "status": "error",
                    "error": {
                        "code": "DISPATCH_ERROR",
                        "message": f"Failed to dispatch to main thread: {container['error']}",
                        "traceback": container.get("tb", ""),
                    },
                }
            else:
                result = container["result"]
        else:
            # Hython and nested calls already running on Houdini's main thread
            # can execute directly. Re-dispatching those through hdefereval
            # would deadlock until the timeout expires.
            result = _execute()
    except Exception as e:
        result = {
            "status": "error",
            "error": {
                "code": "DISPATCH_ERROR",
                "message": f"Failed to dispatch to main thread: {e}",
                "traceback": traceback.format_exc(),
            },
        }

    result["timing_ms"] = round((time.time() - start_time) * 1000, 2)
    return result
