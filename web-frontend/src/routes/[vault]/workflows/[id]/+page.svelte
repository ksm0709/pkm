<script lang="ts">
  import { page } from '$app/stores';
  import { apiClient, apiGet } from '$lib/api/client.js';

  interface WorkflowDetail {
    id: string;
    title: string;
    trigger_time: string;
    schedule_hour: number;
    enabled: boolean;
    marker_file: string;
    pre_hook: string | null;
    post_hook: string | null;
    snippet: string;
    body: string;
    jitter_type: string;
  }

  let vaultName = $derived($page.params.vault);
  let workflowId = $derived($page.params.id);
  let workflow = $state<WorkflowDetail | null>(null);
  let loading = $state(true);
  let error = $state('');
  let modalOpen = $state(false);
  let saving = $state(false);
  let enabledDraft = $state(true);
  let triggerTimeDraft = $state('00:00');

  async function loadWorkflow(vault: string, id: string) {
    workflow = null;
    loading = true;
    error = '';
    try {
      workflow = await apiGet<WorkflowDetail>(`/api/v1/vault/${vault}/workflows/${id}`);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load workflow.';
    } finally {
      loading = false;
    }
  }

  function openSettings() {
    if (!workflow) return;
    enabledDraft = workflow.enabled;
    triggerTimeDraft = workflow.trigger_time;
    modalOpen = true;
  }

  async function saveSettings() {
    if (!workflow || saving) return;
    saving = true;
    error = '';
    try {
      const response = await apiClient(
        `/api/v1/vault/${vaultName}/workflows/${workflow.id}`,
        {
          method: 'PATCH',
          body: JSON.stringify({
            enabled: enabledDraft,
            trigger_time: triggerTimeDraft
          })
        }
      );
      if (!response.ok) throw new Error(`PATCH workflow -> ${response.status}`);
      workflow = (await response.json()) as WorkflowDetail;
      modalOpen = false;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to update workflow.';
    } finally {
      saving = false;
    }
  }

  $effect(() => {
    if (!vaultName || !workflowId) return;
    void loadWorkflow(vaultName, workflowId);
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
      <button type="button" class="settings-btn" aria-label="Workflow settings" onclick={openSettings}>
        settings
      </button>
    </header>

    <section class="workflow-meta" aria-label="Workflow metadata">
      <span>{workflow.trigger_time}</span>
      <span>{workflow.enabled ? 'on' : 'off'}</span>
      <span>{workflow.marker_file}</span>
    </section>

    {#if error}
      <p class="status-msg error">{error}</p>
    {/if}

    <article class="workflow-body" aria-label="Workflow body">
      <pre>{workflow.body}</pre>
    </article>
  {/if}
</main>

{#if modalOpen && workflow}
  <div class="modal-backdrop">
    <div
      class="settings-modal"
      role="dialog"
      aria-label="Workflow settings"
    >
      <form
        class="settings-form"
        onsubmit={(event) => {
          event.preventDefault();
          void saveSettings();
        }}
      >
        <div class="modal-row">
          <label for="workflow-enabled">Enabled</label>
          <input id="workflow-enabled" type="checkbox" bind:checked={enabledDraft} />
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
        <div class="modal-actions">
          <button type="button" onclick={() => (modalOpen = false)}>Cancel</button>
          <button type="submit" disabled={saving} aria-label="Save workflow settings">
            Save
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<style>
  .workflow-detail {
    width: min(1180px, calc(100vw - 64px));
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

  .meta-rail,
  .workflow-meta,
  .settings-btn,
  .status-msg,
  .settings-modal {
    font-family: var(--font-mono);
  }

  .meta-rail {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.10em;
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

  .workflow-body {
    border-top: 1px solid var(--border);
    padding-top: var(--space-4, 16px);
  }

  .workflow-body pre {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    word-break: break-word;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
  }

  .status-msg {
    color: var(--text-muted);
  }

  .status-msg.error {
    color: var(--signal-danger, #c0392b);
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
    width: min(420px, calc(100vw - 32px));
    padding: var(--space-4, 16px);
    border: 1px solid var(--border);
    border-top: 2px solid var(--accent);
    background: var(--surface, var(--bg));
    color: var(--text);
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

  .modal-row input[type='time'] {
    width: 120px;
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
    .workflow-detail {
      width: min(100%, calc(100vw - 32px));
    }
  }
</style>
