# PKM MCP Server

PKM includes a built-in [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that allows AI coding assistants (like Claude Desktop, Cursor, or Cline) to interact directly with your PKM vault.

## Features

The MCP server runs a JSON-RPC 2.0 server over `stdio` and exposes the following tools to the AI assistant:

- **`note_add`**: Create a new atomic note in the vault.
- **`daily_add`**: Append a timestamped log entry or TODO to today's daily note.
- **`search`**: Perform semantic search across your notes to retrieve context.
- **`index`**: Rebuild the semantic search index so the assistant can query recent changes.
- **`pkm_ask`**: Ask a natural language question about your vault (requires `pkm daemon start` to be running).

## Registration How-To

To use the PKM MCP server, you need to register it in your MCP client's configuration file. 

### For Claude Desktop

1. Open your Claude Desktop configuration file:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the `pkm` server to the `mcpServers` section. You can use `uvx` to run it dynamically or specify the path to your `pkm` installation:

```json
{
  "mcpServers": {
    "pkm": {
      "command": "uvx",
      "args": [
        "pkm",
        "mcp"
      ]
    }
  }
}
```

*Note: If you have a specific vault you want the MCP server to use, you can pass the `--vault` option:*

```json
{
  "mcpServers": {
    "pkm": {
      "command": "uvx",
      "args": [
        "pkm",
        "mcp",
        "--vault",
        "my-work-vault"
      ]
    }
  }
}
```

### For Cursor

1. Open Cursor Settings.
2. Go to **Features** > **MCP Servers**.
3. Add a new server:
   - **Name**: `PKM`
   - **Type**: `stdio`
   - **Command**: `uvx pkm mcp` (or point directly to your pkm binary)

## Usage

Once registered and the client is restarted, your AI assistant will have access to your vault. You can ask it to:
- *"Search my PKM vault for notes about concurrent SQLite writes."*
- *"Add a daily log entry to my PKM saying I finished the auth refactor."*
- *"Create a new PKM note about this retry strategy pattern we just implemented."*
