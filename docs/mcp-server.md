# PKM MCP Server

PKM includes a built-in [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that allows AI coding assistants (like Claude Desktop, Cursor, or Cline) to interact directly with your PKM vault.

## Features

The MCP server runs a JSON-RPC 2.0 server over `stdio` and exposes the following tools to the AI assistant:

**Write tools**
- **`note_add`**: Create a durable atomic note in the vault. Use only for concepts, entities, processes, principles, patterns, decisions, and index-worthy knowledge.
- **`patch_note`**: Replace, append, prepend, or upsert a section of an existing note, with optional stale-write guards.
- **`rename_note`**: Rename a note ID and update inbound wikilinks.
- **`add_wikilink`**: Add a reasoned link to the Related section of a source note.
- **`create_hub_note`**: Create an index note for a discovered topic cluster.
- **`daily_add`**: Append a timestamped log entry or TODO to today's daily note. Use for time-bound session state, progress, and transient observations.
- **`create_daily_subnote`**: Create a dated subnote (`YYYY-MM-DD-{title}.md`) tagged `daily-note` and add a `[[wikilink]]` entry to today's daily note. Use for structured time-bound material such as meetings, investigations, and long session notes.

**Search & discovery tools**
- **`read_daily_log`**: Read a past or present daily note. Use `offset=N` for N days ago (`0`=today, `1`=yesterday) or `date_str=YYYY-MM-DD` for an explicit date (`date_str` wins if both given).
- **`search`**: Perform semantic search across your notes to retrieve context.
- **`read_note`**: Read a note's full body and metadata before using it as evidence.
- **`list_notes`**: List notes, optionally filtering by title substring.
- **`list_tags`**: List all tags used in the vault with their note counts, sorted by frequency.
- **`tag_search`**: Filter notes by tag pattern (exact, glob `db*`, AND `python+testing`, OR `python,rust`).
- **`find_backlinks_for_note`**: Find all notes that link TO a given note (daemon-free inbound wikilink scan).
- **`get_note_neighbors`**: Get all neighbors of a note — outbound wikilinks, inbound backlinks, tag nodes, ghost nodes, and optionally semantic similarity connections. Reads `graph.json` directly (daemon-free). Returns `{note_id, outbound, inbound, semantic}` where each item has `note_id`, `title`, and `type` fields. Pass `include_semantic=true` to include embedding-based connections from `graph_enriched.json`.
- **`find_surprising_connections`**: Find semantic bridges between topic clusters.
- **`list_clusters`**: List indexed topic clusters and hub coverage.
- **`list_god_nodes`**: List structurally central notes in the graph.

**Vault health tools**
- **`vault_stats`**: Get a snapshot of vault health — note count, orphan count, tag count, avg links, index status.
- **`list_orphans`**: List all notes with zero inbound AND outbound wikilinks.
- **`list_stale_notes`**: List notes not modified in the last N days.
- **`read_recent_note_activity`**: Read the last N entries from the note operation log.

**Zettelkasten workflow tools**
- **`list_consolidation_candidates`**: List daily notes eligible for distillation (not today, not already consolidated).
- **`mark_consolidated`**: Mark a daily note as consolidated after distilling insights — requires `distilled_note_ids` for auditability.

**Promotion rule**
Before using `note_add`, verify the material has a stable definition, long-term
scope, and at least one meaningful relation or source link. If it only describes
what happened today, use `daily_add` or `create_daily_subnote`.

**Index tool**
- **`index`**: Rebuild the semantic search index so the assistant can query recent changes.

**Host-side synthesis**
For questions that span notes, the assistant should use `search` to find starting
points, `get_note_neighbors` to traverse no more than two graph depths, and
`read_note` to load the selected sources before synthesizing an answer in the MCP
host. These are ordinary FastMCP tools discovered through `tools/list`; PKM does
not provide a separate answer-generation tool.

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
- *"Create a daily subnote for this investigation transcript, then promote only the durable findings."*
