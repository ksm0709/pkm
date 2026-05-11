# pkm web

Manage the `pkm-web` systemd user service.

## Usage
`pkm web COMMAND [OPTIONS]`

## Commands
- `setup`: Create browser auth state, install the systemd user unit, reload systemd, and enable/start `pkm-web`.
- `start`: Start the existing `pkm-web` user service.
- `stop`: Stop the service.
- `restart`: Restart the service.
- `status`: Show service status.
- `enable`: Enable the service to start on login.
- `tunnel`: Expose the local web service through a temporary Cloudflare tunnel.

## Setup Options
- `--reset`: Reset the browser login password and invalidate existing sessions.
- `--port <PORT>`: Persist the pkm web daemon port in config before starting.

## Examples
Run once per machine:

```bash
pkm web setup --port 7420
pkm web status
pkm web restart
```

If setup reports `Linger=no`, enable lingering and retry:

```bash
sudo loginctl enable-linger "$USER"
pkm web setup
```

`pkm update` refreshes an existing web unit after upgrade, but it does not
create the first unit because setup must create local auth files and verify
systemd user lingering.
