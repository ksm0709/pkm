# `pkm ask`

Ask a natural language question about your vault.

The `pkm ask` command allows you to query your PKM vault using natural language. It sends the query to a background ML daemon which leverages an LLM to answer questions using the context of your vault.

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
