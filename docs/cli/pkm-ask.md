# `pkm ask`

Ask a natural language question about your vault.

The `pkm ask` command allows you to query your PKM vault using natural language. It sends the query to a background ML daemon which performs semantic search to retrieve relevant context (RAG) and leverages an LLM to answer questions using that context. It is equipped with a wrapper layer that exposes 17 typed PKM tools to the autonomous agent (see [Available Tools](#available-tools) below).

## Architecture & Security

The `pkm ask` command is powered by a split-architecture background daemon:
- **Host Daemon**: Orchestrates tasks, manages a JSON-based task queue, and proxies IPC calls.

## Architecture & Security

`pkm ask` leverages a separated architecture:
1. **Client (`pkm ask`)**: Sends the query via Unix socket.
2. **Host Daemon**: Maintains the semantic search index in memory and routes requests.
3. **Sandbox Worker**: An air-gapped subprocess managed by `tiny-agent-py` that holds the LLM API keys and executes tool calls.

This ensures that the LLM has high reasoning capability without exposing the host to prompt injection or unauthorized file access.

## Background Tasks

If you use agent hooks that enqueue background tasks, the daemon processes them sequentially.

## MCP Integration

The natural language reporting capability is also exposed as an MCP tool (`pkm_ask`) via FastMCP. This allows external agents (like Claude Code or Cursor) to query the vault safely. The tool only accepts structured, parameterized inputs to minimize injection vectors and supports streaming/progressive status updates for long generations.

## LLM Configuration

The daemon uses [LiteLLM](https://docs.litellm.ai/) to proxy API calls, which supports over 100+ LLM providers. By default, the model is set to `auto`.

When `auto` is used, PKM will automatically pick the best available model from a curated list based on the API keys exported in your environment. If one model's API fails, it will seamlessly fall back to the next best model in the list.

To use the default configuration, export your API key (e.g. Gemini or OpenAI) before starting the daemon:
```bash
export GEMINI_API_KEY="your-gemini-api-key"
# or
export OPENAI_API_KEY="your-openai-api-key"

pkm daemon start
```

For OpenAI-only environments, `auto` prioritizes thinking-model price/performance: `gpt-5.4-nano` first for note extraction, ranking, summarization, and low-cost RAG; then GPT-5 reasoning fallbacks such as `gpt-5-mini`, `gpt-5-nano`, and `gpt-5.4-mini`.

### Changing the Model or Provider

You can change the LLM model globally via configuration or per-command using the `--model` flag.

**Method 1: Global Configuration**
```bash
pkm config set model "gpt-5.4-nano"
export OPENAI_API_KEY="..."
pkm daemon restart
```

**Method 2: Per-Command Flag**
```bash
pkm ask "what was that idea?" --model "gpt-5.4-nano"
```

To list all available models and providers from LiteLLM, run:
```bash
pkm ask --list-models
```
*Note: Depending on the provider chosen, you must export the appropriate API keys in the environment where the daemon is running.*

## Usage

```bash
pkm ask <query>
pkm ask "what was that idea about X?"
```

### Reasoning Display
When using capable models with reasoning enabled (e.g. via `--reasoning-effort`), the daemon will automatically stream the model's internal thinking/reasoning chunks directly to your terminal. Reasoning is displayed in a subtle dim, italic style to separate it clearly from the final answer.

The CLI stream renderer treats daemon events as user-facing status: reasoning is
shown transiently, internal lifecycle tools are hidden, task updates are shown as
compact status rows, PKM tool calls are highlighted by name, and daemon protocol
errors exit non-zero with an actionable message.

## Requirements

The `ask` command requires the PKM daemon to be running. Start it with:

```bash
pkm daemon start
```

## Available Tools

The agent has access to typed tools for vault interaction, including:

| Tool | When to use |
|------|-------------|
| `read_daily_log(date_str)` | Read a daily note |
| `add_daily_log(text)` | Append to today's daily note |
| `read_note(note_id)` | Read an atomic note by ID |
| `search_notes(query)` | Title-substring search |
| `semantic_search(query, ...)` | Semantic similarity search |
| `add_note(title, content, ...)` | Create a new atomic note |
| `patch_note(note_id, operation, ...)` | Patch part of an existing note without replacing the full body |
| `update_note(note_id, content, ...)` | Replace an existing note's full body |
| `get_note_neighbors(note_id)` | Graph neighbors (outbound/inbound/semantic, daemon-free) |
| `vault_stats()` | Vault health overview |
| `list_stale_notes(days)` | Notes not modified in N days |
| `list_orphans()` | Notes with no inbound or outbound links |
| `find_backlinks_for_note(note_id)` | Inbound links (daemon-free) |
| `list_tags()` | All tags with counts |
| `tag_search(pattern)` | Filter by tag (exact/glob/AND/OR) |
| `list_consolidation_candidates()` | Daily notes ready for distillation |
| `mark_consolidated(date_str, distilled_note_ids)` | Mark daily as consolidated |
| `read_recent_note_activity(tail)` | Last N entries from operation log |

**Tool selection guidance:** use `search_notes` for title match, `semantic_search` for meaning, `tag_search` for topic, `find_backlinks_for_note` when the daemon is unavailable.

## Options

- `--timeout <seconds>`: Set the timeout to wait for the LLM response (default: 120 seconds).
- `--model <model_name>`: LLM model to use (overrides global config).
- `--list-models`: List available model providers via litellm.

```bash
pkm ask "summarize my notes on project Y" --timeout 300
```
