<script lang="ts">
  import { page } from "$app/stores";
  import { apiGet } from "$lib/api/client.js";

  interface WorkflowSummary {
    id: string;
    title: string;
    trigger_time: string;
    schedule_hour: number;
    enabled: boolean;
    snippet: string;
    marker_file: string;
  }

  let vaultName = $derived($page.params.vault);
  let workflows = $state<WorkflowSummary[]>([]);
  let loading = $state(true);
  let error = $state("");

  async function loadWorkflows(vault: string) {
    workflows = [];
    loading = true;
    error = "";
    try {
      workflows = await apiGet<WorkflowSummary[]>(
        `/api/v1/vault/${vault}/workflows`,
      );
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load workflows.";
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (!vaultName) return;
    void loadWorkflows(vaultName);
  });
</script>

<svelte:head>
  <title>Workflows — {vaultName} — pkm</title>
</svelte:head>

<main class="workflow-page">
  {#if loading}
    <p class="status-msg">Loading…</p>
  {:else if error}
    <p class="status-msg error">{error}</p>
  {:else if workflows.length === 0}
    <p class="status-msg faint">No workflows configured.</p>
  {:else}
    <section class="workflow-ledger" aria-label="Workflow ledger">
      <div class="ledger-head">
        <span>WORKFLOW</span>
        <span>TRIGGER</span>
        <span>STATE</span>
      </div>
      <ul class="workflow-list">
        {#each workflows as workflow (workflow.id)}
          <li class="workflow-entry">
            <a
              href="/{vaultName}/workflows/{workflow.id}"
              class="workflow-link"
            >
              <span class="workflow-title">{workflow.title || workflow.id}</span
              >
              <span class="workflow-trigger">{workflow.trigger_time}</span>
              <span class:off={!workflow.enabled} class="workflow-state">
                {workflow.enabled ? "on" : "off"}
              </span>
              <span class="workflow-snippet">{workflow.snippet}</span>
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</main>

<style>
  .workflow-page {
    width: min(1180px, calc(100vw - 64px));
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .workflow-ledger {
    border-top: 1px solid var(--border);
  }

  .ledger-head,
  .workflow-link {
    display: grid;
    grid-template-columns: minmax(220px, 1.2fr) 110px 80px minmax(0, 1.4fr);
    gap: var(--space-4, 16px);
    align-items: center;
  }

  .ledger-head {
    min-height: 34px;
    border-bottom: 1px solid var(--border);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .workflow-list {
    display: flex;
    flex-direction: column;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .workflow-entry {
    border-bottom: 1px solid var(--border);
  }

  .workflow-link {
    min-height: 54px;
    color: var(--text);
    text-decoration: none;
  }

  .workflow-link:hover .workflow-title,
  .workflow-link:focus-visible .workflow-title {
    color: var(--accent);
  }

  .workflow-title,
  .workflow-trigger,
  .workflow-state,
  .workflow-snippet {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .workflow-title {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
  }

  .workflow-trigger,
  .workflow-state,
  .workflow-snippet {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .workflow-state {
    color: var(--accent);
  }

  .workflow-state.off {
    color: var(--text-faint);
  }

  .status-msg {
    font-family: var(--font-mono);
    color: var(--text-muted);
  }

  .status-msg.error {
    color: var(--signal-danger, #c0392b);
  }

  .status-msg.faint {
    color: var(--text-faint);
  }

  @media (max-width: 760px) {
    .workflow-page {
      width: min(100%, calc(100vw - 32px));
    }

    .ledger-head {
      display: none;
    }

    .workflow-link {
      grid-template-columns: minmax(0, 1fr) auto;
      gap: var(--space-2, 8px);
      padding: var(--space-3, 12px) 0;
    }

    .workflow-snippet {
      grid-column: 1 / -1;
    }
  }
</style>
