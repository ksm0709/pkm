# pkm vault

Manage multiple vaults.

## Usage
`pkm vault [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`add`**: Create a new vault.
- **`edit`**: Open the vault in the configured editor.
- **`list`**: List all discovered vaults.
- **`open`**: Switch the active vault (set as default).
- **`remove`**: Remove a vault by moving it to trash.
- **`setup`**: Declare the current directory as a PKM vault.
- **`unset`**: Unset the current directory's vault and optionally migrate...
- **`where`**: Show the currently active vault path.

## Examples
```bash
pkm vault list
pkm vault add personal
pkm vault open personal
pkm vault where
```
