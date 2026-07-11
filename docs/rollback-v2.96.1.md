# Roll back to PKM v2.96.1

Use v2.96.1 only as a temporary compatibility release. Rollback restores code
that can execute scheduled workflows and embedded answer tasks, so preserved v2
configuration must remain quarantined until the owner explicitly approves each
workflow to resume.

## 1. Stop all PKM processes

Stop the user service before installing v2 or touching executable state:

```bash
systemctl --user stop pkm-web.service
pkm daemon stop || true
systemctl --user is-active pkm-web.service || true
pgrep -af '[p]km\.daemon|[p]km\.worker' || true
```

Do not continue while the service reports `active` or either process remains.
The service stop terminates the daemon and its worker control group; manually
launched processes must be stopped separately.

## 2. Inventory and quarantine executable state

Do not print workflow JSON or credential values. Record only which executable
configuration files exist, then move them aside without changing their bytes:

```bash
install -d -m 700 ~/.config/pkm/rollback-v2-quarantine
quarantine_dir="$(mktemp -d \
  ~/.config/pkm/rollback-v2-quarantine/run.XXXXXXXX)"
chmod 700 "$quarantine_dir"
if test -f ~/.config/pkm/workflow.json; then
  printf '%s\n' 'global workflow configuration: present'
  mv ~/.config/pkm/workflow.json "$quarantine_dir/workflow.json"
fi
```

For every configured vault, repeat the same operation for
`<vault>/.pkm/workflow.json`, creating a new private `mktemp -d` quarantine
directory for that vault before moving the file. Never reuse an existing
destination path. Preserve `workflow-history.jsonl`, old model settings, keyring
entries,
`secrets.env`, and browser `pkm.askSession.*` data in place; they are evidence or
credentials, not permission to resume execution. Never display their contents.

With override files quarantined, v2.96.1 sees only its bundled workflow, which is
disabled by default. The v3 activation already deleted `task_queue.json`; do not
restore or reconstruct that queue.

## 3. Approval checkpoint

**Stop here and obtain explicit owner approval before restoring any quarantined
workflow file or enabling any workflow.** Approval must identify the workflow ID,
target vault, schedule, and credentials it may use. A rollback needed only for
legacy read/API compatibility should keep all workflow files quarantined.

## 4. Install v2.96.1

The v3 updater supports tagged non-Git installs:

```bash
pkm update v2.96.1
pkm --version
```

The output must report `2.96.1`. If `pkm update` is unavailable, use the stable
hardened-bridge installer, which downloads the requested rollback tag:

```bash
curl -fsSL https://raw.githubusercontent.com/ksm0709/pkm/v2.96.6/cli/install.sh \
  | PKM_INSTALL_REF=v2.96.1 bash
pkm --version
```

Do not use a floating `main` installer for rollback.

## 5. Start and verify

Start one service only after the version and quarantine checks pass:

```bash
systemctl --user start pkm-web.service
systemctl --user is-active pkm-web.service
pkm --version
```

Then reconnect MCP clients, verify expected v2 tool discovery and required HTTP
routes, and run a retained note read plus search against the intended vault.
Confirm no scheduled workflow runs and no `task_queue.json` is recreated.

If the owner later approves a specific workflow, inspect its quarantined copy
without exposing secrets, restore only that approved configuration, explicitly
review its `enabled`, schedule, vault, model, and credential references, and
restart the service. Do not bulk-restore legacy workflow state.

## Data restoration expectations

Rollback can read preserved legacy history, settings, credentials, and browser
state again, subject to their original validity. It cannot restore queue entries:
v3 permanently deletes `~/.config/pkm/task_queue.json` without an archive because
payloads may contain secrets. Re-create only an explicitly approved task.

After the compatibility need is resolved, follow the
[v3 migration guide](migrations/v3.md) through v2.96.6 again.
