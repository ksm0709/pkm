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

  `pkm setup --web` is fail-closed: if `Linger=no` it exits non-zero with a
  remediation message and writes nothing.

- `systemd --user` available (any modern Linux desktop / server).
- `pkm` on PATH; vaults discoverable via `pkm vault list`.

## 2. Run setup

```bash
pkm setup --web
```

This single command:

1. Verifies user lingering is enabled.
2. Generates a 256-bit token and writes it to
   `~/.config/pkm/web-token` (mode `0600`).
3. Writes a systemd user unit at
   `~/.config/systemd/user/pkm-web.service`.
4. Prints the token to stdout exactly once for you to copy.

If the token file already exists it is **not** rotated — delete it first if
you need a fresh token.

## 3. Enable + start the unit

```bash
systemctl --user daemon-reload
systemctl --user enable --now pkm-web
systemctl --user status pkm-web
```

The daemon listens on `127.0.0.1:7420` by default. The web UI is served from
the same port under `/`.

## 4. Where the token lives

```text
~/.config/pkm/web-token        # mode 0600
```

The frontend stores the token in `localStorage` after first login so it
persists across reloads.

## 5. Access — Tailscale only (recommended)

The token is bearer-only and not bound to the device. Anyone who can reach
the bind address with the token has full vault read/write access. Therefore:

- **Bind to Tailscale.** Set the unit's `bind=` to your `tailscale0` IP
  (or `100.x.y.z`) so the daemon is unreachable from the public internet.
- Do **not** expose `7420` via reverse proxies on the open internet.
- Treat the token like an SSH key.

## 6. Threat model

| Threat | Impact | Mitigation |
|---|---|---|
| Malicious browser extension reads `localStorage` | Token exfiltration → full vault access | Tailscale-only access; revoke + rotate token (`rm ~/.config/pkm/web-token && pkm setup --web` again, then `systemctl --user restart pkm-web`) |
| Cross-tenant access on shared host | Other users on box read token file | Token mode `0600`; `~/.config/pkm/` is user-private |
| Lost laptop / device | Persistent attacker has token | Tailscale ACL revocation + token rotation |
| Network MITM | Read of bearer token in flight | Tailscale provides WireGuard-grade transport encryption |

The threat model **does not** cover untrusted browsers or shared user
sessions — pkm-webapp is single-tenant by design.

## 7. Updating

```bash
pip install -U pkm           # or your preferred install path
systemctl --user restart pkm-web
```

The bundled SPA assets ship inside the wheel under
`pkm/web/static/`, so a `pip install -U` updates the frontend in lockstep
with the daemon.
