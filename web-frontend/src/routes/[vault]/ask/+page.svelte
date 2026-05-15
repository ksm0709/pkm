<script lang="ts">
  import { onMount, tick } from "svelte";
  import { afterNavigate } from "$app/navigation";
  import { page } from "$app/stores";
  import AskTranscript from "$lib/components/AskTranscript.svelte";
  import AskInput from "$lib/components/AskInput.svelte";
  import { getAskSession, type ManagedTask } from "$lib/ask/session.svelte";

  let vaultName = $derived($page.params.vault);
  let askSession = $derived(getAskSession(vaultName));
  let turns = $derived(askSession.turns);
  let busy = $derived(askSession.busy);
  let modelLabel = $derived(askSession.modelLabel);
  let selectedModel = $derived(askSession.selectedModel);
  let modelOptions = $derived(askSession.modelOptions);
  let managedTasks = $derived(askSession.managedTasks);
  let inputValue = $state("");
  let scrollEl: HTMLDivElement | null = $state(null);
  let tasksCollapsed = $state(false);

  function scrollToEnd() {
    void tick().then(() => {
      if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    });
  }

  function taskMarker(task: ManagedTask) {
    if (task.checked) return "✓";
    if (task.status === "in_progress") return ">";
    if (task.status === "cancelled") return "~";
    return "";
  }

  onMount(() => {
    askSession.hydrate();
    void askSession.loadOptions();
    maybeSubmitQueryParam();
  });

  afterNavigate(() => {
    maybeSubmitQueryParam();
  });

  $effect(() => {
    turns;
    managedTasks;
    busy;
    scrollToEnd();
  });

  $effect(() => {
    if (!managedTasks.length) tasksCollapsed = false;
  });

  function maybeSubmitQueryParam() {
    const q = $page.url.searchParams.get("q");
    const trimmed = q?.trim() ?? "";
    if (trimmed && askSession.claimQueryParam(trimmed)) {
      inputValue = trimmed;
      void tick().then(() => askSession.submit(trimmed));
    } else if (!trimmed) {
      askSession.clearQueryParam();
    }
  }
</script>

<svelte:head>
  <title>ask — {vaultName} — pkm</title>
</svelte:head>

<div class="ask-page">
  <div bind:this={scrollEl} class="scroll-area">
    <div class="ask-column">
      {#if turns.length === 0}
        <p class="empty-state">Enter a query packet below.</p>
      {:else}
        <AskTranscript {turns} />
      {/if}
    </div>
  </div>
  <div class="composer-shell">
    {#if managedTasks.length}
      <div class="ask-column task-column">
        <section
          class="ask-task-list"
          class:collapsed={tasksCollapsed}
          aria-label="Managed tasks"
        >
          <button
            type="button"
            class="task-list-toggle"
            aria-expanded={!tasksCollapsed}
            aria-controls="ask-managed-tasks"
            aria-label={`${tasksCollapsed ? "Expand" : "Collapse"} managed tasks`}
            onclick={() => (tasksCollapsed = !tasksCollapsed)}
          >
            <span class="task-list-caret" aria-hidden="true"
              >{tasksCollapsed ? ">" : "v"}</span
            >
            <span class="task-list-label">TASKS</span>
            <span class="task-list-count" aria-hidden="true"
              >{managedTasks.length}</span
            >
          </button>
          <div
            id="ask-managed-tasks"
            class="task-items"
            hidden={tasksCollapsed}
          >
            {#each managedTasks as task (task.id)}
              <div
                class="task-item"
                class:done={task.checked}
                class:progress={task.status === "in_progress"}
                class:cancelled={task.status === "cancelled"}
              >
                <span
                  class="task-box"
                  role="checkbox"
                  aria-checked={task.checked}
                  aria-label={task.text}
                >
                  {taskMarker(task)}
                </span>
                <span class="task-text">{task.text}</span>
              </div>
            {/each}
          </div>
        </section>
      </div>
    {/if}
    <div class="ask-column">
      <AskInput
        bind:value={inputValue}
        {vaultName}
        {busy}
        {modelLabel}
        {selectedModel}
        {modelOptions}
        onmodelchange={(model) => askSession.setModel(model)}
        onsubmit={(question) => askSession.submit(question)}
      />
    </div>
  </div>
</div>

<style>
  .ask-page {
    display: flex;
    flex-direction: column;
    height: calc(100vh - var(--topbar-height, 48px));
    height: calc(100svh - var(--topbar-height, 48px));
    height: calc(100dvh - var(--topbar-height, 48px));
    min-height: 0;
    background: var(--bg);
    overflow: hidden;
  }

  .scroll-area {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding-bottom: var(--space-4, 16px);
  }

  .scroll-area .ask-column {
    margin-top: auto;
  }

  .ask-column {
    box-sizing: border-box;
    width: var(--readable-content-width);
    max-width: none;
    margin: 0 auto;
    padding: 0;
  }

  .empty-state {
    margin-top: var(--space-6, 32px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-faint);
  }

  .composer-shell {
    position: relative;
    z-index: 1;
    flex-shrink: 0;
    width: 100%;
    box-sizing: border-box;
    border-top: 1px solid var(--border);
    background: var(--surface, var(--bg));
  }

  .composer-shell .ask-column {
    width: var(--readable-content-width);
    max-width: none;
    margin: 0 auto;
    padding: 0;
  }

  .task-column {
    border-bottom: 1px solid var(--border);
  }

  .ask-task-list {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: var(--space-3, 12px);
    align-items: start;
    padding: var(--space-3, 12px) var(--space-4, 16px);
    border-left: 2px solid var(--accent);
    color: var(--text-muted);
    font-family: var(--font-mono);
    background: transparent;
  }

  .ask-task-list.collapsed {
    align-items: center;
  }

  .task-list-toggle {
    display: inline-flex;
    min-width: 0;
    padding: 0;
    align-items: center;
    gap: var(--space-1, 4px);
    border: 0;
    background: transparent;
    color: var(--accent);
    font: inherit;
    cursor: pointer;
  }

  .task-list-toggle:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: 3px;
  }

  .task-list-caret {
    width: 1ch;
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1;
  }

  .task-list-label {
    padding-top: 3px;
    color: var(--accent);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    line-height: 1.2;
  }

  .task-list-count {
    min-width: 1.5em;
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1.2;
    text-align: right;
  }

  .task-items {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 8px);
    min-width: 0;
  }

  .task-items[hidden] {
    display: none;
  }

  .task-item {
    display: grid;
    grid-template-columns: 16px minmax(0, 1fr);
    gap: var(--space-2, 8px);
    align-items: start;
    min-width: 0;
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
    line-height: 1.35;
  }

  .task-box {
    display: inline-flex;
    width: 14px;
    height: 14px;
    margin-top: 1px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border-strong, var(--border));
    background: var(--surface);
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 700;
    line-height: 1;
  }

  .task-text {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .task-item.done {
    color: var(--text-faint);
  }

  .task-item.done .task-box {
    border-color: #4f7f5c;
    background: #d9eadc;
    color: #1f5f32;
  }

  .task-item.done .task-text {
    text-decoration: line-through;
    text-decoration-thickness: 1px;
    text-underline-offset: 3px;
  }

  .task-item.progress {
    color: var(--text);
    font-weight: 600;
  }

  .task-item.progress .task-box {
    border-color: #9b812f;
    background: #f3e7b8;
    color: #6f570a;
  }

  .task-item.cancelled .task-box {
    border-color: #9b4b4b;
    background: #ead3d3;
    color: #7f2525;
  }

  @media (max-width: 640px) {
    .ask-task-list {
      grid-template-columns: 1fr;
      gap: var(--space-2, 8px);
    }
  }
</style>
