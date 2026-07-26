"""Auto-start FXHoudini-MCP server when Houdini's UI is ready.

Houdini 22 ships Python 3.13, so it only discovers ``uiready.py`` from
``python3.13libs``.  Keep this entry point in sync with the other
version-specific copies.

Set FXHOUDINIMCP_AUTOSTART=0 to disable auto-start.
"""

import os

if os.environ.get("FXHOUDINIMCP_AUTOSTART", "1") == "1":
    try:
        import fxhoudinimcp_server.startup

        fxhoudinimcp_server.startup.ensure_running()
    except Exception as e:
        print(f"[fxhoudinimcp] Auto-start failed: {e}")
