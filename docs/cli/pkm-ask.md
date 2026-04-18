# `pkm ask`

Ask a natural language question about your vault.

The `pkm ask` command allows you to query your PKM vault using natural language. It sends the query to a background ML daemon which leverages an LLM to answer questions using the context of your vault.

## Architecture & Security

The `pkm ask` command is powered by a split-architecture background daemon:
- **Host Daemon**: Orchestrates tasks, manages a JSON-based task queue, tracks LiteLLM token budgets, and proxies API calls.
- **Air-gapped Sandbox LLM Worker**: Executes tasks isolated to the Vault directory with zero network access, communicating strictly via IPC (stdin/stdout) with the Host Daemon.

This ensures that the LLM has high reasoning capability without exposing the host to prompt injection or unauthorized file access.

## Token Limits & Queue

The Host Daemon enforces hard token limits per time window. If the token budget is exhausted, `pkm ask` will fail fast, and background tasks in the JSON queue will pause until the budget resets.

## MCP Integration

The natural language reporting capability is also exposed as an MCP tool (`pkm_ask`) via FastMCP. This allows external agents (like Claude Code or Cursor) to query the vault safely. The tool only accepts structured, parameterized inputs to minimize injection vectors and supports streaming/progressive status updates for long generations.

## LLM Configuration

The daemon uses [LiteLLM](https://docs.litellm.ai/) to proxy API calls, which supports over 100+ LLM providers. By default, it uses `gpt-4o-mini`.

To use the default configuration, export your OpenAI API key before starting the daemon:
```bash
export OPENAI_API_KEY="your-openai-api-key"
pkm daemon start
```

### Changing the Model or Provider

Currently, the model string is defined in `cli/src/pkm/daemon.py` and must be modified in the source code to change it.

1. Open `cli/src/pkm/daemon.py`.
2. Locate the model fallback string (e.g., `model = msg.get("model", "gpt-4o-mini")`).
3. Change it to your desired LiteLLM model string (e.g., `"claude-3-5-sonnet-20241022"` for Anthropic or `"ollama/llama3"` for local usage).
4. Export the necessary API key (e.g., `export ANTHROPIC_API_KEY="..."`).
5. Restart the daemon: `pkm daemon restart`.

## Usage

```bash
pkm ask <query>
pkm ask "what was that idea about X?"
```

## Requirements

The `ask` command requires the PKM daemon to be running. Start it with:

```bash
pkm daemon start
```

## Options

- `--timeout <seconds>`: Set the timeout to wait for the LLM response (default: 120 seconds).

```bash
pkm ask "summarize my notes on project Y" --timeout 300
```
