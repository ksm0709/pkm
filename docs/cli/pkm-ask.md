# `pkm ask`

Ask a natural language question about your vault.

The `pkm ask` command allows you to query your PKM vault using natural language. It sends the query to a background ML daemon which performs semantic search to retrieve relevant context (RAG) and leverages an LLM to answer questions using that context.

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

The daemon uses [LiteLLM](https://docs.litellm.ai/) to proxy API calls, which supports over 100+ LLM providers. By default, the model is set to `auto`.

When `auto` is used, PKM will automatically pick the best available model from a curated list based on the API keys exported in your environment. If one model's API fails, it will seamlessly fall back to the next best model in the list.

To use the default configuration, export your API key (e.g. Gemini or OpenAI) before starting the daemon:
```bash
export GEMINI_API_KEY="your-gemini-api-key"
# or
export OPENAI_API_KEY="your-openai-api-key"

pkm daemon start
```

### Changing the Model or Provider

You can change the LLM model globally via configuration or per-command using the `--model` flag.

**Method 1: Global Configuration**
```bash
pkm config set model "claude-3-5-sonnet-20241022"
export ANTHROPIC_API_KEY="..."
pkm daemon restart
```

**Method 2: Per-Command Flag**
```bash
pkm ask "what was that idea?" --model "gemini/gemini-1.5-pro"
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

## Requirements

The `ask` command requires the PKM daemon to be running. Start it with:

```bash
pkm daemon start
```

## Options

- `--timeout <seconds>`: Set the timeout to wait for the LLM response (default: 120 seconds).
- `--model <model_name>`: LLM model to use (overrides global config).
- `--list-models`: List available model providers via litellm.

```bash
pkm ask "summarize my notes on project Y" --timeout 300
```
