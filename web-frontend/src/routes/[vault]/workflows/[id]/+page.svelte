<script lang="ts">
  import { page } from "$app/stores";
  import { apiClient, apiGet } from "$lib/api/client.js";
  import MarkdownRenderer from "$lib/components/MarkdownRenderer.svelte";

  interface WorkflowDetail {
    id: string;
    title: string;
    trigger_time: string;
    schedule_hour: number;
    enabled: boolean;
    model: string;
    model_options?: string[];
    marker_file: string;
    pre_hook: string | null;
    post_hook: string | null;
    snippet: string;
    body: string;
    jitter_type: string;
  }

  interface WorkflowHistoryRecord {
    workflow_id: string;
    task_id: string;
    hostname: string;
    time: string;
    status: "success" | "failure" | "queued" | "running";
    source: string;
    phase: string;
    error: string | null;
    result_summary: string;
  }

  interface WorkflowRunStatus {
    status: "idle" | "queued" | "running";
    task_id: string | null;
  }

  let vaultName = $derived($page.params.vault);
  let workflowId = $derived($page.params.id);
  let workflow = $state<WorkflowDetail | null>(null);
  let loading = $state(true);
  let error = $state("");
  let modalOpen = $state(false);
  let saving = $state(false);
  let enabledDraft = $state(true);
  let triggerTimeDraft = $state("00:00");
  let modelDraft = $state("auto");
  let historyOpen = $state(false);
  let historyLoading = $state(false);
  let historyError = $state("");
  let historyEntries = $state<WorkflowHistoryRecord[]>([]);
  let runStatus = $state<WorkflowRunStatus>({ status: "idle", task_id: null });
  let runBusy = $state(false);
  let runError = $state("");
  let runMessage = $state("");

  let runUnavailable = $derived(
    runBusy || runStatus.status === "queued" || runStatus.status === "running",
  );

  async function loadWorkflow(vault: string, id: string) {
    workflow = null;
    loading = true;
    error = "";
    try {
      workflow = await apiGet<WorkflowDetail>(
        `/api/v1/vault/${vault}/workflows/${id}`,
      );
      await loadRunStatus(vault, id);
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load workflow.";
    } finally {
      loading = false;
    }
  }

  async function loadRunStatus(vault = vaultName, id = workflow?.id) {
    if (!vault || !id) return;
    try {
      runStatus = await apiGet<WorkflowRunStatus>(
        `/api/v1/vault/${vault}/workflows/${id}/run-status`,
      );
    } catch {
      runStatus = { status: "idle", task_id: null };
    }
  }

  function openSettings() {
    if (!workflow) return;
    enabledDraft = workflow.enabled;
    triggerTimeDraft = workflow.trigger_time;
    modelDraft = workflow.model || "auto";
    modalOpen = true;
  }

  async function saveSettings() {
    if (!workflow || saving) return;
    saving = true;
    error = "";
    try {
      const response = await apiClient(
        `/api/v1/vault/${vaultName}/workflows/${workflow.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            enabled: enabledDraft,
            trigger_time: triggerTimeDraft,
            model: modelDraft,
          }),
        },
      );
      if (!response.ok) throw new Error(`PATCH workflow -> ${response.status}`);
      workflow = (await response.json()) as WorkflowDetail;
      modalOpen = false;
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to update workflow.";
    } finally {
      saving = false;
    }
  }

  async function openHistory() {
    if (!workflow || historyLoading) return;
    historyOpen = true;
    historyLoading = true;
    historyError = "";
    try {
      historyEntries = await apiGet<WorkflowHistoryRecord[]>(
        `/api/v1/vault/${vaultName}/workflows/${workflow.id}/history`,
      );
    } catch (e) {
      historyError =
        e instanceof Error ? e.message : "Failed to load workflow history.";
      historyEntries = [];
    } finally {
      historyLoading = false;
    }
  }

  async function runWorkflow() {
    if (!workflow || runUnavailable) return;
    runBusy = true;
    runError = "";
    runMessage = "";
    try {
      const response = await apiClient(
        `/api/v1/vault/${vaultName}/workflows/${workflow.id}/run`,
        { method: "POST" },
      );
      if (!response.ok)
        throw new Error(`POST workflow run -> ${response.status}`);
      const result = (await response.json()) as WorkflowRunStatus;
      runStatus = result;
      runMessage = `Queued ${result.task_id}`;
      if (historyOpen) await openHistory();
    } catch (e) {
      runError = e instanceof Error ? e.message : "Failed to run workflow.";
    } finally {
      runBusy = false;
    }
  }

  $effect(() => {
    if (!vaultName || !workflowId) return;
    void loadWorkflow(vaultName, workflowId);
  });

  $effect(() => {
    if (!workflow || runStatus.status === "idle") return;
    const timer = window.setInterval(() => {
      void loadRunStatus();
    }, 3000);
    return () => window.clearInterval(timer);
  });
</script>

<svelte:head>
  <title>{workflowId} — workflows — {vaultName}</title>
</svelte:head>

<main class="workflow-detail">
  {#if loading}
    <p class="status-msg">Loading…</p>
  {:else if error && !workflow}
    <p class="status-msg error">{error}</p>
  {:else if workflow}
    <header class="workflow-header">
      <div class="meta-rail">
        <span>WORKFLOW</span>
        <strong>{workflow.id}</strong>
      </div>
      <div class="workflow-actions">
        <button
          type="button"
          class="settings-btn run-btn"
          aria-label="Run workflow"
          disabled={runUnavailable}
          onclick={runWorkflow}
        >
          {runBusy
            ? "queueing"
            : runStatus.status === "idle"
              ? "run"
              : runStatus.status}
        </button>
        <button
          type="button"
          class="settings-btn"
          aria-label="Workflow history"
          onclick={openHistory}
        >
          history
        </button>
        <button
          type="button"
          class="settings-btn"
          aria-label="Workflow settings"
          onclick={openSettings}
        >
          settings
        </button>
      </div>
    </header>

    <section class="workflow-meta" aria-label="Workflow metadata">
      <span>{workflow.trigger_time}</span>
      <span>{workflow.enabled ? "on" : "off"}</span>
      <span>{workflow.model || "auto"}</span>
      <span class:active-run={runStatus.status !== "idle"}>
        {runStatus.status}{runStatus.task_id ? `:${runStatus.task_id}` : ""}
      </span>
      <span>{workflow.marker_file}</span>
    </section>

    {#if error}
      <p class="status-msg error">{error}</p>
    {/if}
    {#if runError}
      <p class="status-msg error">{runError}</p>
    {:else if runMessage}
      <p class="status-msg">{runMessage}</p>
    {/if}

    <article class="workflow-body" aria-label="Workflow body">
      <MarkdownRenderer markdown={workflow.body} vault={vaultName} />
    </article>
  {/if}
</main>

{#if modalOpen && workflow}
  <div class="modal-backdrop">
    <div class="settings-modal" role="dialog" aria-label="Workflow settings">
      <form
        class="settings-form"
        onsubmit={(event) => {
          event.preventDefault();
          void saveSettings();
        }}
      >
        <div class="modal-row">
          <label for="workflow-enabled">Enabled</label>
          <input
            id="workflow-enabled"
            type="checkbox"
            bind:checked={enabledDraft}
          />
        </div>
        <div class="modal-row">
          <label for="workflow-trigger">Trigger time</label>
          <input
            id="workflow-trigger"
            type="time"
            step="3600"
            bind:value={triggerTimeDraft}
          />
        </div>
        <div class="modal-row wide">
          <label for="workflow-model">Model</label>
          <select id="workflow-model" bind:value={modelDraft}>
            {#each workflow.model_options?.length ? workflow.model_options : [workflow.model || "auto"] as option (option)}
              <option value={option}>{option}</option>
            {/each}
          </select>
        </div>
        <div class="modal-actions">
          <button type="button" onclick={() => (modalOpen = false)}
            >Cancel</button
          >
          <button
            type="submit"
            disabled={saving}
            aria-label="Save workflow settings"
          >
            Save
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if historyOpen && workflow}
  <div class="modal-backdrop">
    <div class="history-modal" role="dialog" aria-label="Workflow history">
      <div class="history-head">
        <div>
          <span>HISTORY</span>
          <strong>{workflow.id}</strong>
        </div>
        <button
          type="button"
          class="settings-btn"
          aria-label="Close workflow history"
          onclick={() => (historyOpen = false)}
        >
          close
        </button>
      </div>

      {#if historyLoading}
        <p class="status-msg">Loading…</p>
      {:else if historyError}
        <p class="status-msg error">{historyError}</p>
      {:else if historyEntries.length === 0}
        <p class="status-msg faint">No workflow history found.</p>
      {:else}
        <ol class="history-list">
          {#each historyEntries as entry (`${entry.task_id}:${entry.status}:${entry.phase}:${entry.time}`)}
            <li
              class:failed={entry.status === "failure"}
              class:pending={entry.status === "queued" ||
                entry.status === "running"}
              class="history-entry"
            >
              <div class="history-entry-main">
                <span>{entry.time}</span>
                <strong>{entry.status}</strong>
                <span>{entry.hostname}</span>
              </div>
              <p>{entry.result_summary || entry.phase}</p>
              {#if entry.error}
                <pre>{entry.error}</pre>
              {/if}
            </li>
          {/each}
        </ol>
      {/if}
    </div>
  </div>
{/if}

<style>
  .workflow-detail {
    width: var(--page-content-width);
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .workflow-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 16px);
    margin-bottom: var(--space-4, 16px);
  }

  .workflow-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-2, 8px);
  }

  .meta-rail,
  .workflow-meta,
  .settings-btn,
  .status-msg,
  .settings-modal,
  .history-modal {
    font-family: var(--font-mono);
  }

  .meta-rail {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .meta-rail strong {
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--text);
    font-size: var(--type-chrome-size, 13px);
    font-weight: 600;
    text-transform: none;
    letter-spacing: 0;
  }

  .settings-btn,
  .modal-actions button {
    color: var(--accent);
    background: transparent;
    border: 0;
    padding: var(--space-2, 8px);
    cursor: pointer;
  }

  .settings-btn:disabled {
    color: var(--text-faint);
    cursor: default;
    text-decoration: none;
  }

  .run-btn:not(:disabled) {
    font-weight: 600;
  }

  .settings-btn:hover,
  .modal-actions button:hover {
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .workflow-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3, 12px);
    margin-bottom: var(--space-5, 24px);
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  .workflow-meta .active-run {
    color: var(--accent);
  }

  .workflow-body {
    border-top: 1px solid var(--border);
    padding-top: var(--space-4, 16px);
  }

  .status-msg {
    color: var(--text-muted);
  }

  .status-msg.error {
    color: var(--signal-danger, #c0392b);
  }

  .status-msg.faint {
    color: var(--text-faint);
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    z-index: 1100;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4, 16px);
    background: rgba(9, 11, 13, 0.62);
  }

  .settings-modal {
    width: min(420px, var(--modal-available-width));
    padding: var(--space-4, 16px);
    border: 1px solid var(--border);
    border-top: 2px solid var(--accent);
    background: var(--surface, var(--bg));
    color: var(--text);
  }

  .history-modal {
    width: min(720px, var(--modal-available-width));
    max-height: min(720px, calc(100vh - 64px));
    overflow: auto;
    padding: var(--space-4, 16px);
    border: 1px solid var(--border);
    border-top: 2px solid var(--accent);
    background: var(--surface, var(--bg));
    color: var(--text);
  }

  .history-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-4, 16px);
    margin-bottom: var(--space-3, 12px);
    padding-bottom: var(--space-3, 12px);
    border-bottom: 1px solid var(--border);
  }

  .history-head div {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 4px;
  }

  .history-head span {
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.1em;
  }

  .history-head strong {
    overflow-wrap: anywhere;
    font-size: var(--type-chrome-size, 13px);
  }

  .history-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .history-entry {
    border-left: 2px solid var(--accent);
    padding-left: var(--space-3, 12px);
  }

  .history-entry.failed {
    border-left-color: var(--signal-danger, #c0392b);
  }

  .history-entry.pending {
    border-left-color: var(--text-faint);
  }

  .history-entry-main {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(100px, auto);
    gap: var(--space-3, 12px);
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  .history-entry-main span,
  .history-entry-main strong {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .history-entry-main strong {
    color: var(--text);
  }

  .history-entry p {
    margin: var(--space-2, 8px) 0 0;
    color: var(--text);
    line-height: var(--type-body-lh, 1.7);
  }

  .history-entry pre {
    margin: var(--space-2, 8px) 0 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    color: var(--signal-danger, #c0392b);
  }

  .settings-form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4, 16px);
  }

  .modal-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: var(--space-3, 12px);
    align-items: center;
  }

  .modal-row input[type="time"] {
    width: 120px;
    color: var(--text);
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--accent);
    padding: var(--space-1, 4px);
    font-family: var(--font-mono);
  }

  .modal-row.wide {
    grid-template-columns: 1fr;
  }

  .modal-row select {
    min-width: 0;
    width: 100%;
    color: var(--text);
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--accent);
    padding: var(--space-1, 4px);
    font-family: var(--font-mono);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2, 8px);
  }

  @media (max-width: 760px) {
    .workflow-header {
      align-items: flex-start;
      flex-direction: column;
    }

    .workflow-actions {
      justify-content: flex-start;
    }

    .history-entry-main {
      grid-template-columns: 1fr;
    }
  }
</style>
