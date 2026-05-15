# pkm update

Update pkm to the latest version.

## Usage
`pkm update [OPTIONS] [VERSION]`

## Description
Updates your PKM installation to the latest version, or a specific VERSION tag (e.g., `v0.3.0`).

After a successful reinstall, `pkm update` also refreshes installed skill files,
shell aliases, an existing web unit, and recognizable locally copied bundled
workflow settings in `~/.config/pkm/workflow.json`.

## Examples
```bash
pkm update
pkm update v2.4.0
```
