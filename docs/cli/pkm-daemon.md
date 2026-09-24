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

## Status

`pkm daemon status` prints `running`, `stale` (live lock-file PID, socket down), `stopped (idle exit)`, or `stopped`. The PID comes from `~/.config/pkm/daemon.lock` while that process holds the lock and its argv is exactly `python -m pkm.daemon` or `pkm daemon run`. Idle shutdown writes `idle` to `~/.config/pkm/daemon.exit` and the next start removes it. `pkm daemon start` closes the daemon's stdin.

## Examples
```bash
pkm daemon start
pkm daemon status
pkm daemon logs
```
