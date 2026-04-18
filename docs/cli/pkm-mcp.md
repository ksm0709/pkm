# pkm mcp

Start MCP server (stdio transport).

## Usage
`pkm mcp [OPTIONS]`

## Description
Runs a foreground JSON-RPC 2.0 server on stdin/stdout. An MCP client spawns this process automatically via its server configuration.

Tools exposed to the MCP client: `note_add`, `daily_add`, `search`, `index`, `pkm_ask`.

## Options
- `-v, --vault TEXT`: Vault name to use.

## Examples
```bash
pkm mcp
pkm mcp --vault work-vault
```
