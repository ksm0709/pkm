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

## Examples
```bash
pkm config set default-vault work-vault
pkm config set editor vim
pkm config get default-vault
pkm config list
```
