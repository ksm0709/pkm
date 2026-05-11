# pkm setup

Interactive setup wizard.

## Usage
`pkm setup [OPTIONS]`

## Options
- `--web`: Set up the pkm web systemd user unit and browser auth state.
- `--reset`: With `--web`, reset the browser login password and invalidate sessions.
- `--port <PORT>`: With `--web`, persist the pkm web daemon port in config.

## Description
Guides you through the setup process. It can:
- Install optional semantic search dependencies.
- Create or discover your vaults.
- Choose a default vault.
- Install PKM skill files for agent workflows.
- Install or refresh the pkm web service unit.

## Examples
```bash
pkm setup
pkm setup --web --port 8123
```
