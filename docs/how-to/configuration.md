# :material-cog:{.scale-in-center} Configuration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOUDINI_HOST` | `localhost` | Houdini host address |
| `HOUDINI_PORT` | `8100` | Houdini hwebserver port |
| `FXHOUDINIMCP_PORT` | `8100` | Port for the Houdini plugin to listen on |
| `FXHOUDINIMCP_BIND_HOST` | `127.0.0.1` | Address for the Houdini plugin to bind; expose it remotely only on a protected network |
| `FXHOUDINIMCP_ACCESS_MODE` | `full` | Houdini command policy: `full`, confirmation-gated `safe`, or `read-only` |
| `FXHOUDINIMCP_JOURNAL` | `1` | Record mutating commands and compact before/after scene diffs |
| `FXHOUDINIMCP_AUDIT_LOG` | `$HOUDINI_USER_PREF_DIR/fxhoudinimcp/audit.jsonl` | Persistent activity-journal path |
| `FXHOUDINIMCP_TOOL_PROFILE` | `all` | Comma-separated external MCP tool profiles |
| `FXHOUDINIMCP_AUTOSTART` | `1` | Set to `0` to disable auto-start |
| `FXHOUDINIMCP_AUTO_LAYOUT` | `1` | Set to `0` to disable automatic node layout |
| `MCP_TRANSPORT` | `stdio` | MCP transport (`stdio` or `streamable-http`) |
| `LOG_LEVEL` | `INFO` | Logging level |

## Auto-Start

The Houdini plugin auto-starts when the UI is ready via `uiready.py`, which
stacks cleanly with other Houdini packages. Startup registers the MCP endpoints,
starts Houdini's `hwebserver` when needed, and validates `mcp.health` in the
background so the UI event loop remains responsive. Disable auto-start by
setting:

``` shell
export FXHOUDINIMCP_AUTOSTART=0
```

You can still toggle the server manually using the **MCP Server** shelf tool.

The listener is restricted to `127.0.0.1` by default because MCP tools can
execute code in Houdini. Set `FXHOUDINIMCP_BIND_HOST=0.0.0.0` only when remote
access is intentional and the network is protected.

If an assistant cannot reach Houdini, use `get_houdini_connection_status` to
return structured diagnostics without raising a tool error. If port `8100` is
owned by a different Houdini process, either close that process or set both
`FXHOUDINIMCP_PORT` and `HOUDINI_PORT` to a matching free port.

## Tool Profiles

The external MCP server registers only the schemas selected by
`FXHOUDINIMCP_TOOL_PROFILE`. A smaller schema gives the model fewer unrelated
tools to consider; it does not change Houdini cook speed or model inference
speed. Available profiles are `core`, `sop`, `solaris`, `simulation`,
`copernicus`, `animation`, `developer`, and `all`.

Profiles can be composed:

``` shell
export FXHOUDINIMCP_TOOL_PROFILE=sop,solaris
```

`core` is included in every domain profile. `all` preserves the complete
186-tool interface and is the default.

## Access Modes and Confirmation

`FXHOUDINIMCP_ACCESS_MODE` is enforced inside Houdini, so changing MCP clients
does not bypass it:

- `full` allows all registered commands and preserves backwards compatibility.
- `safe` requires `confirm=true` for high-risk operations such as deleting
  nodes, replacing or saving scenes, writing caches, starting renders,
  modifying HDAs, and executing Python or HScript.
- `read-only` fails closed: only commands explicitly classified as inspection
  operations are accepted.

Use `get_access_policy` to inspect the live Houdini policy and the schemas
loaded by the external MCP process. Confirmation is per command; it does not
create or change Houdini undo transactions.

## Persistent Activity Journal

When `FXHOUDINIMCP_JOURNAL=1`, successful and failed mutating commands are
written as JSON Lines to `FXHOUDINIMCP_AUDIT_LOG`. Each entry includes timing,
sanitized parameters, the HIP path, and compact before/after differences for
nodes, connections, and explicitly targeted parameters. Source payloads are
hashed instead of stored verbatim, and common secret fields are redacted.

Use `get_activity_journal` to inspect recent entries across Houdini sessions.
`clear_activity_journal` is itself confirmation-gated in `safe` mode.

## Auto-Layout

By default, tools tidy the network editor as they work: node-creation handlers
and workflow tools call `layoutChildren()` on the parent network, and the
server instructions tell assistants to call `layout_children` frequently. This
re-arranges *all* nodes in the affected network — including ones you placed by
hand.

To preserve your manual layouts, disable auto-layout:

``` shell
export FXHOUDINIMCP_AUTO_LAYOUT=0
```

Set it both in the MCP client environment (where `python -m fxhoudinimcp`
runs) and in the Houdini environment (e.g. `houdini.env`), since each process
reads it independently. Inside a running Houdini session you can also toggle
it without restarting:

``` python
hou.putenv("FXHOUDINIMCP_AUTO_LAYOUT", "0")
```

When disabled, the server instructions tell assistants never to move nodes,
the `layout_children` tool becomes a no-op, and the Houdini-side handlers skip
every automatic `layoutChildren()` call. Newly created nodes keep the position
Houdini assigns at creation time.

## Transport Modes

### stdio (Default)

The AI client spawns the MCP server as a child process. Communication happens over stdin/stdout. This is the simplest setup, no ports or networking required on the MCP side.

### streamable-http

Runs the MCP server as an HTTP endpoint. Useful for remote or shared setups:

``` shell
export MCP_TRANSPORT=streamable-http
python -m fxhoudinimcp
```

## Custom Port

If Houdini's hwebserver is already bound to port 8100, configure a different port:

1. Set `FXHOUDINIMCP_PORT` in your Houdini environment
2. Set `HOUDINI_PORT` in your MCP client config to match
