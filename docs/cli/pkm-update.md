# pkm update

Update pkm to the latest version.

## Usage
`pkm update [OPTIONS] [VERSION]`

## Description
Updates your PKM installation to the latest version, or a specific VERSION tag (e.g., `v0.3.0`).

After a successful reinstall, a fresh helper process refreshes installed skill
files, shell aliases, and an existing web service unit. The fresh process avoids
reusing modules from the package version that performed the reinstall.

`v2.96.6` is the supported forward-migration bridge from v2 to v3. It
stops an active web service before replacement and restarts it only after
reinstall, fresh post-update synchronization, and version verification all
succeed. If update fails, the service remains stopped and the command prints a
manual recovery command. `v2.96.1` remains the temporary rollback target only.
See the [v3 migration guide](../migrations/v3.md) before upgrading and the
[v2.96.1 rollback guide](../rollback-v2.96.1.md) if you need to return to v2.

`v2.96.6` is the supported forward-migration bridge from v2 to v3. It stops an
active web service before replacement and restarts it only after reinstall,
fresh post-update synchronization, and version verification all succeed. If an
update fails, the service remains stopped and the command prints a manual
recovery command. `v2.96.1` remains the temporary rollback target only.

## Examples
```bash
pkm update
pkm update v2.96.6
```
