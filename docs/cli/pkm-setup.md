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

For first-time web service installation, prefer `pkm web setup`. It wraps the
same auth/unit setup flow and then runs `systemctl --user daemon-reload` plus
`systemctl --user enable --now pkm-web`.

`pkm setup --web` remains available for scripts that want to create the auth
files and unit without starting the service immediately.
