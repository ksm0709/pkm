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

Run `pkm setup --web` once per machine before using `pkm web start`.
`pkm update` refreshes an existing web unit after upgrade, but it does not
create the first `pkm-web.service` because setup must create local auth files
and verify systemd user lingering.
