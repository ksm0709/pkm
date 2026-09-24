# pkm mcp

Start MCP server (stdio transport).

## Usage
`pkm mcp [OPTIONS]`

## Description
Runs a foreground JSON-RPC 2.0 server on stdin/stdout. An MCP client spawns this process automatically via its server configuration.

FastMCP discovers direct tools for note creation, partial edits, reads and
renames; daily logs and subnotes; semantic search and indexing; backlinks, tags,
graph neighbors and graph analysis; vault health; and consolidation tracking.
For a cross-note answer, the MCP host should call `search`, follow relevant
`get_note_neighbors` results for at most two graph depths, call `read_note` on the
selected evidence, and synthesize the answer itself.

`search` uses the background daemon. If the daemon socket is down, the server starts one process (unless the daemon lock is already held), waits until the socket accepts connections, and retries the search once. That wait and the retried read share one budget, `PKM_DAEMON_STARTUP_TIMEOUT` (default 45 seconds, polled every `PKM_DAEMON_STARTUP_POLL_SECONDS`, default 0.5). The retry's read timeout is the time left in that budget, or 0.2 seconds if the socket appears at the deadline. The tool returns `Daemon unavailable` only when the socket does not come up in time.

The MCP tool wrappers are covered by scenario tests at the function layer and
by a JSON-RPC tools/list contract test. This keeps the stdio protocol contract
stable while allowing wrapper behavior such as missing notes, rename conflicts,
graph-missing errors, and consolidation refusals to be tested without spawning a
subprocess for every case.

## Options
- `-v, --vault TEXT`: Vault name to use.

## Examples
```bash
pkm mcp
pkm mcp --vault work-vault
```
