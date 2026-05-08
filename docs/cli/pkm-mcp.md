# pkm mcp

Start MCP server (stdio transport).

## Usage
`pkm mcp [OPTIONS]`

## Description
Runs a foreground JSON-RPC 2.0 server on stdin/stdout. An MCP client spawns this process automatically via its server configuration.

The server exposes the same vault workflow tools used by local agents,
including note creation, daily logs, note reads/renames, vault stats, stale note
and orphan discovery, backlink/tag search, graph neighbors, consolidation
tracking, and `pkm_ask`.

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
