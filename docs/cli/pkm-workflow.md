# pkm workflow

Manage PKM daemon workflows — scheduled AI maintenance tasks that run automatically via the daemon.

## Usage
`pkm workflow [OPTIONS] COMMAND [ARGS]...`

## Commands
- **`list`**: List all configured workflows (bundled defaults + global overrides + vault overrides).
- **`run WORKFLOW_ID`**: Immediately queue a workflow for execution by the daemon worker.

## Workflow Configuration

Workflows are defined in JSON and merged from three sources (later sources override earlier):

1. **Bundled defaults** — shipped with `pkm`, always present as a baseline.
2. **Global config** — `~/.config/pkm/workflow.json`
3. **Vault override** — `{vault}/.pkm/workflow.json`

### Schema

```json
[
  {
    "id": "my_workflow",
    "schedule_hour": 3,
    "jitter_type": "md5_hostname",
    "marker_file": "my-wf-last-run",
    "system_prompt_template": "Run the {rollover_result} task.",
    "pre_hook": "pkm.workflows.hooks:build_daily_summary",
    "post_hook": null
  }
]
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique workflow identifier |
| `schedule_hour` | yes | Hour of day (0–23) to run |
| `jitter_type` | yes | Jitter strategy: `md5_hostname` or `md5_hostname_suffix:<seed>` |
| `marker_file` | yes | Marker filename under `{vault}/.pkm/` to prevent duplicate runs |
| `system_prompt_template` | yes | Prompt template; `{key}` placeholders filled from pre-hook result |
| `pre_hook` | no | Python callable `"module:function"` run before the agent; return dict injected into template |
| `post_hook` | no | Python callable `"module:function"` run after the agent completes |

### Jitter Types

| Value | Behaviour |
|-------|-----------|
| `md5_hostname` | Minute offset = `md5(hostname) % 30` — stable per machine |
| `md5_hostname_suffix:<seed>` | Minute offset = `md5(hostname + seed) % 30` — different per workflow on same machine |

## Bundled Workflows

| ID | Hour | Description |
|----|------|-------------|
| `zettelkasten_maintenance` | 3 | Nightly graph maintenance: surprising connections, cluster review, hub notes |
| `daily_task_summary` | 8 | Morning daily note rollover: carries forward incomplete tasks from yesterday |

## Examples

```bash
# List all workflows
pkm workflow list

# List workflows for a specific vault (applies vault overrides)
pkm workflow list --vault /path/to/vault

# Queue zettelkasten maintenance to run now
pkm workflow run zettelkasten_maintenance

# Queue daily summary for a specific vault
pkm workflow run daily_task_summary
```

## Notes

- `pkm workflow run` writes a task to `~/.config/pkm/task_queue.json` (raw JSON array). The daemon worker picks it up on its next poll cycle.
- The daemon auto-schedules all configured workflows on startup via `workflow_checker` coroutines; `pkm workflow run` is for on-demand execution.
- Custom hooks must be importable from the Python environment where the daemon runs.
