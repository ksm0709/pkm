# pkm config

Manage PKM configuration.

## Usage
`pkm config [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`get`**: Get a configuration value.
- **`list`**: List all configuration settings.
- **`set`**: Set a configuration value.

## Available Keys
- `auto`: Auto-link and split commands execute changes automatically (true/false)
- `default-vault`: Default vault name used when `--vault` is not specified
- `editor`: Editor command used by `pkm daily edit` (e.g. 'vim', 'code --wait')
- `graph-depth`: Default graph traversal depth for search and show commands
- `graph-semantic-*`: Threshold, neighborhood, weighting, and cross-domain controls for semantic graph edges
- `web-bind`: Bind address used by the pkm web daemon
- `web-port`: Port used by the pkm web daemon
- `web-window-padding`: Symmetric page window padding in the pkm web app, in px (0-128, default: 32)

## Examples
```bash
pkm config set default-vault work-vault
pkm config set editor vim
pkm config set web-port 8123
pkm config set web-window-padding 48
pkm config get default-vault
pkm config list
```
