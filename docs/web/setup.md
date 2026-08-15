# pkm-webapp — Setup

End-to-end setup for the local web UI served by the `pkm` daemon over a
systemd user unit. This guide assumes you have already installed the `pkm`
CLI (see top-level README) and have at least one vault registered.

## 1. Prerequisites

- **systemd user lingering must be enabled.** Without lingering, the user
  unit stops at logout and the web UI becomes unreachable from Tailscale.

  ```bash
  sudo loginctl enable-linger "$USER"
  loginctl show-user --property=Linger "$USER"   # → Linger=yes
  ```

  `pkm web setup` is fail-closed: if `Linger=no` it exits non-zero with a
  remediation message and writes nothing.

- `systemd --user` available (any modern Linux desktop / server).
- `pkm` on PATH; vaults discoverable via `pkm vault list`.

## 2. Run setup

```bash
pkm web setup
```

Run this once on each machine where you want `pkm-web.service` installed.
`pkm update` upgrades the CLI and refreshes an existing web unit, but it does
not create the first unit because setup must verify lingering and create local
browser auth files.

This single command:

1. Verifies user lingering is enabled.
2. Prompts for the browser login password and writes its salted PBKDF2 hash to
   `~/.config/pkm/web-password` (mode `0600`).
3. Generates a 256-bit compatibility bearer token and writes it to
   `~/.config/pkm/web-token` (mode `0600`).
4. Writes a systemd user unit at
   `~/.config/systemd/user/pkm-web.service`.
5. Runs `systemctl --user daemon-reload`.
6. Runs `systemctl --user enable --now pkm-web`.
7. Prints the token to stdout exactly once for CLI/curl clients.

To use a non-default port, persist it in the config during setup:

```bash
pkm web setup --port 8123
```

You can also change it later:

```bash
pkm config set web-port 8123
systemctl --user restart pkm-web
```

If the token file already exists it is **not** rotated — delete it first if
you need a fresh token. To reset the browser password and invalidate existing
browser sessions:

```bash
pkm web setup --reset
```

## 3. Manual setup path

`pkm setup --web` remains available for scripts that want to write auth files
and the unit without starting it immediately. In that mode, run:

```bash
pkm setup --web
systemctl --user daemon-reload
systemctl --user enable --now pkm-web
systemctl --user status pkm-web
```

The daemon listens on port `7420` by default. The effective URL and port are
printed in `journalctl --user -u pkm-web` at startup. The web UI is served from
the same port under `/`.

## 4. Where auth state lives

```text
~/.config/pkm/web-password        # browser password hash, mode 0600
~/.config/pkm/web-session-reset   # reset marker, mode 0600
~/.config/pkm/web-token           # compatibility bearer token, mode 0600
```

The frontend does not store the bearer token. Browser login exchanges the
password for an HttpOnly `pkm_session` cookie. The bearer token remains
available for CLI/curl clients using `Authorization: Bearer ...`.

## 5. Access — Tailscale only (recommended)

The browser password and compatibility bearer token both grant full vault
read/write access. Anyone who can reach the bind address and authenticate has
single-user owner access. Therefore:

- **Bind to Tailscale.** Set `pkm config set web-bind <tailscale-ip>` to your
  `tailscale0` IP (or `100.x.y.z`) so the daemon is unreachable from the
  public internet.
- Do **not** expose `7420` via reverse proxies on the open internet.
- Treat the token like an SSH key.

## 6. Threat model

| Threat | Impact | Mitigation |
|---|---|---|
| Malicious browser extension reads web storage | Bearer token is not stored; active browser session may still be abused | Tailscale-only access; reset password with `pkm web setup --reset`; rotate bearer token if exposed |
| Cross-tenant access on shared host | Other users on box read token file | Token mode `0600`; `~/.config/pkm/` is user-private |
| Lost laptop / device | Persistent attacker has token | Tailscale ACL revocation + token rotation |
| Network MITM | Read of bearer token in flight | Tailscale provides WireGuard-grade transport encryption |

The threat model **does not** cover untrusted browsers or shared user
sessions — pkm-webapp is single-tenant by design.

## 7. Updating

```bash
pkm update
pkm web restart              # wraps: systemctl --user restart pkm-web
```

On a new machine, run `pkm web setup` before `pkm web start`; otherwise the
systemd user unit does not exist yet.

The bundled SPA assets ship inside the wheel under
`pkm/web/static/`, so a `pip install -U` updates the frontend in lockstep
with the daemon.

## 8. Feedback email notifications

To email every web feedback entry to `ksm07091@gmail.com`, configure SMTP in a
private systemd environment file:

```bash
mkdir -p ~/.config/pkm
chmod 700 ~/.config/pkm
```

Create `~/.config/pkm/feedback-mail.env` with mode `0600`:

```ini
PKM_FEEDBACK_SMTP_HOST=smtp.gmail.com
PKM_FEEDBACK_SMTP_PORT=587
PKM_FEEDBACK_SMTP_USERNAME=ksm07091@gmail.com
PKM_FEEDBACK_SMTP_PASSWORD=<Google app password>
PKM_FEEDBACK_EMAIL_FROM=ksm07091@gmail.com
PKM_FEEDBACK_SMTP_STARTTLS=true
```

Add this drop-in at `~/.config/systemd/user/pkm-web.service.d/feedback-mail.conf`:

```ini
[Service]
EnvironmentFile=%h/.config/pkm/feedback-mail.env
```

Then apply it:

```bash
systemctl --user daemon-reload
pkm web restart
```

The recipient defaults to `ksm07091@gmail.com`; set
`PKM_FEEDBACK_EMAIL_TO` in the environment file to override it. Feedback is
always saved to the vault even if SMTP is unavailable, and the page reports
the delivery state.
