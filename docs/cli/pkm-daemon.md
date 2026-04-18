# pkm daemon

Manage the background ML daemon for fast semantic search.

## Usage
`pkm daemon [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`logs`**: Show daemon log output.
- **`restart`**: Restart the daemon.
- **`start`**: Start the daemon in the background.
- **`status`**: Show whether the daemon is running.
- **`stop`**: Stop the running daemon.

## Examples
```bash
pkm daemon start
pkm daemon status
pkm daemon logs
```
