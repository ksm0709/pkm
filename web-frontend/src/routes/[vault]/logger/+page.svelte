<script lang="ts">
  import { tick } from 'svelte';
  import { page } from '$app/stores';
  import { apiClient, apiGet } from '$lib/api/client.js';
  import {
    applyInlineSuggestion,
    detectInlineTrigger,
    fetchInlineSuggestions
  } from '$lib/inline-suggestions.js';

  interface DailyNote {
    note_id: string;
    title: string;
    body: string;
  }

  interface LogEntry {
    time: string;
    hour: string;
    text: string;
  }

  let vaultName = $derived($page.params.vault);

  let today = $state('');
  let logs = $state<LogEntry[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state('');
  let inputValue = $state('');
  let scrollEl: HTMLDivElement | null = $state(null);
  let textareaEl: HTMLTextAreaElement | null = $state(null);
  let inlineRows = $state<any[]>([]);
  let inlineActiveIndex = $state(0);
  let inlineTrigger = $state<any | null>(null);
  let inlineRequestId = 0;

  const logLinePattern = /^\s*-\s+\[(\d{2}:\d{2}(?::\d{2})?)\]\s+(.+?)\s*$/;

  function parseLogs(body: string): LogEntry[] {
    return body
      .split('\n')
      .map((line) => line.match(logLinePattern))
      .filter((match): match is RegExpMatchArray => match !== null)
      .map((match) => {
        const time = match[1];
        return {
          time,
          hour: `${time.slice(0, 2)}:00`,
          text: match[2]
        };
      });
  }

  function groupedLogs(entries: LogEntry[]) {
    const groups: { hour: string; items: LogEntry[] }[] = [];
    for (const entry of entries) {
      let group = groups[groups.length - 1];
      if (!group || group.hour !== entry.hour) {
        group = { hour: entry.hour, items: [] };
        groups.push(group);
      }
      group.items.push(entry);
    }
    return groups;
  }

  let logGroups = $derived(groupedLogs(logs));
  let inlineMenuOpen = $derived(!busy && inlineTrigger && inlineRows.length > 0);

  async function loadToday() {
    loading = true;
    error = '';
    try {
      const note = await apiGet<DailyNote>(`/api/v1/vault/${vaultName}/daily/today`);
      today = note.note_id;
      logs = parseLogs(note.body ?? '');
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to load today logs.';
    } finally {
      loading = false;
      await tick();
      scrollToBottom();
    }
  }

  function scrollToBottom() {
    if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
  }

  function autoresize() {
    if (!textareaEl) return;
    textareaEl.style.height = 'auto';
    textareaEl.style.height = `${Math.min(textareaEl.scrollHeight, 220)}px`;
  }

  async function refreshInlineSuggestions(
    currentValue = inputValue,
    cursor = textareaEl?.selectionStart ?? inputValue.length,
    currentVault = vaultName
  ) {
    const requestId = ++inlineRequestId;
    const trigger =
      detectInlineTrigger(currentValue, cursor) || detectInlineTrigger(currentValue, currentValue.length);
    inlineTrigger = trigger;
    inlineActiveIndex = 0;
    if (!trigger) {
      inlineRows = [];
      return;
    }
    try {
      const rows = await fetchInlineSuggestions(currentVault, trigger);
      if (requestId !== inlineRequestId) return;
      inlineRows = rows;
    } catch {
      if (requestId !== inlineRequestId) return;
      inlineRows = [];
    }
  }

  function completeInlineRow(row = inlineRows[inlineActiveIndex]) {
    if (!textareaEl || !inlineTrigger || !row) return;
    const result = applyInlineSuggestion(inputValue, inlineTrigger, row);
    inputValue = result.value;
    inlineRows = [];
    inlineTrigger = null;
    inlineActiveIndex = 0;
    void tick().then(() => {
      textareaEl?.focus();
      textareaEl?.setSelectionRange(result.cursor, result.cursor);
      autoresize();
    });
  }

  async function submitLog() {
    const text = inputValue.trim();
    if (!text || busy) return;
    busy = true;
    error = '';
    try {
      const response = await apiClient(`/api/v1/vault/${vaultName}/daily/today`, {
        method: 'POST',
        body: JSON.stringify({ type: 'entry', content: text })
      });
      if (!response.ok) throw new Error(`POST daily log -> ${response.status}`);
      const payload = (await response.json()) as { entry?: string };
      const [entry] = parseLogs(payload.entry ?? '');
      if (entry) logs = [...logs, entry];
      inputValue = '';
      inlineRows = [];
      inlineTrigger = null;
      if (textareaEl) textareaEl.style.height = 'auto';
      await tick();
      scrollToBottom();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to append log.';
    } finally {
      busy = false;
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (inlineMenuOpen) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        inlineActiveIndex = (inlineActiveIndex + 1) % inlineRows.length;
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        inlineActiveIndex = (inlineActiveIndex - 1 + inlineRows.length) % inlineRows.length;
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        inlineRows = [];
        inlineTrigger = null;
        inlineActiveIndex = 0;
        return;
      }
      if (event.key === 'Enter' && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        completeInlineRow();
        return;
      }
    }
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void submitLog();
    }
  }

  function handleInput() {
    if (textareaEl) inputValue = textareaEl.value;
    autoresize();
  }

  $effect(() => {
    if (!vaultName) return;
    void loadToday();
  });

  $effect(() => {
    const currentValue = inputValue;
    const currentVault = vaultName;
    const currentTextarea = textareaEl;
    if (!currentTextarea) return;
    void tick().then(() => {
      const cursor = currentTextarea.selectionStart ?? currentValue.length;
      void refreshInlineSuggestions(currentValue, cursor, currentVault);
    });
  });
</script>

<svelte:head>
  <title>Logger — {vaultName} — pkm</title>
</svelte:head>

<div class="logger-page">
  <div bind:this={scrollEl} class="logger-scroll">
    <main class="reading-column logger-column">
      {#if today}
        <span class="logger-date">{today}</span>
      {/if}

      {#if error}
        <p class="status error">{error}</p>
      {/if}

      {#if loading}
        <p class="status faint">Loading today logs…</p>
      {:else if logs.length === 0}
        <p class="status faint">No timestamped logs yet.</p>
      {:else}
        <div class="log-thread" aria-label="Today logs">
          {#each logGroups as group (group.hour)}
            <section class="hour-group" aria-label={`${group.hour} logs`}>
              <div class="hour-marker">{group.hour}</div>
              {#each group.items as entry (`${entry.time}-${entry.text}`)}
                <article class="log-message">
                  <span class="log-time">{entry.time}</span>
                  <p>{entry.text}</p>
                </article>
              {/each}
            </section>
          {/each}
        </div>
      {/if}
    </main>
  </div>

  <form
    class="logger-input reading-column"
    onsubmit={(event) => {
      event.preventDefault();
      void submitLog();
    }}
  >
    {#if inlineMenuOpen}
      <div class="inline-suggest-menu" role="listbox" aria-label="Inline suggestions">
        {#each inlineRows as row, i (`${row.kind}:${row.label}`)}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div
            class="inline-suggest-row"
            class:active={i === inlineActiveIndex}
            role="option"
            aria-selected={i === inlineActiveIndex}
            tabindex="-1"
            onmousemove={() => (inlineActiveIndex = i)}
            onmousedown={(event) => event.preventDefault()}
            onclick={() => completeInlineRow(row)}
          >
            <span class="inline-suggest-glyph" aria-hidden="true">{i === inlineActiveIndex ? '>' : ''}</span>
            <span class="inline-suggest-label">{row.label}</span>
            <span class="inline-suggest-detail">{row.detail}</span>
          </div>
        {/each}
      </div>
    {/if}
    <span class="prompt-mark" aria-hidden="true">LOG</span>
    <textarea
      bind:this={textareaEl}
      bind:value={inputValue}
      class="logger-textarea"
      placeholder={busy ? 'Saving…' : 'Add log… (⌘↵ to submit, ↵ newline)'}
      rows="1"
      disabled={busy}
      spellcheck="false"
      onkeydown={handleKeydown}
      oninput={handleInput}
    ></textarea>
    <button
      type="submit"
      class="submit-btn"
      disabled={busy || !inputValue.trim()}
      aria-label="Add log"
    >
      ⌘↵
    </button>
  </form>
</div>

<style>
  .logger-page {
    display: flex;
    flex-direction: column;
    height: calc(100vh - var(--topbar-height, 44px));
    height: calc(100svh - var(--topbar-height, 44px));
    height: calc(100dvh - var(--topbar-height, 44px));
    min-height: 0;
  }

  .logger-scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }

  .logger-column {
    padding-top: var(--space-6, 32px);
    padding-bottom: var(--space-7, 48px);
  }

  .logger-date,
  .status,
  .prompt-mark,
  .logger-textarea,
  .submit-btn {
    font-family: var(--font-mono);
  }

  .logger-date {
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  .status {
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  .status.faint {
    color: var(--text-faint);
  }

  .status.error {
    color: var(--signal-danger, #c0392b);
  }

  .log-thread {
    display: flex;
    flex-direction: column;
    gap: var(--space-6, 32px);
  }

  .hour-group {
    display: grid;
    grid-template-columns: 72px minmax(0, 1fr);
    gap: var(--space-3, 12px);
    align-items: start;
  }

  .hour-marker {
    position: sticky;
    top: var(--space-4, 16px);
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.08em;
  }

  .log-message {
    grid-column: 2;
    display: grid;
    grid-template-columns: 80px minmax(0, 1fr);
    gap: var(--space-3, 12px);
    padding: var(--space-3, 12px) 0;
    border-top: 1px solid var(--border);
  }

  .log-time {
    color: var(--accent);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    white-space: nowrap;
  }

  .log-message p {
    margin: 0;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .logger-input {
    position: relative;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    box-sizing: border-box;
    width: 100%;
    max-width: none;
    margin: 0;
    min-height: 56px;
    padding: var(--space-2, 8px) var(--space-4, 16px);
    background-color: var(--surface, var(--bg));
    border-top: 1px solid var(--border);
    border-left: 2px solid var(--accent);
  }

  .inline-suggest-menu {
    position: absolute;
    right: 0;
    bottom: calc(100% + 1px);
    left: 0;
    z-index: 5;
    max-height: min(280px, 38vh);
    overflow-y: auto;
    border-top: 1px solid var(--accent);
    border-bottom: 1px solid var(--border);
    background: var(--surface, var(--bg));
    color: var(--text);
    font-family: var(--font-mono);
    box-shadow: none;
  }

  .inline-suggest-row {
    display: grid;
    grid-template-columns: 14px minmax(120px, auto) minmax(0, 1fr);
    gap: var(--space-2, 8px);
    align-items: center;
    min-height: 34px;
    padding: 0 var(--space-4, 16px);
    border-left: 2px solid transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1.25;
  }

  .inline-suggest-row.active {
    border-left-color: var(--accent);
    background: var(--accent-bg);
    color: var(--text);
  }

  .inline-suggest-glyph,
  .inline-suggest-label {
    color: var(--accent);
  }

  .inline-suggest-label {
    font-weight: 600;
    white-space: nowrap;
  }

  .inline-suggest-detail {
    min-width: 0;
    overflow: hidden;
    color: var(--text-faint);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .prompt-mark {
    flex-shrink: 0;
    color: var(--accent);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
  }

  .logger-textarea {
    flex: 1;
    resize: none;
    min-height: 32px;
    max-height: 220px;
    color: var(--text);
    background-color: transparent;
    border: none;
    border-radius: 0;
    padding: var(--space-1, 4px) var(--space-2, 8px);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    outline: none;
    caret-color: var(--accent);
  }

  .logger-textarea::placeholder {
    color: var(--text-faint);
  }

  .submit-btn {
    flex-shrink: 0;
    color: var(--accent);
    background-color: transparent;
    border: 0;
    border-radius: var(--radius-sm, 2px);
    padding: var(--space-2, 8px) var(--space-3, 12px);
    font-size: var(--type-chrome-size, 13px);
    cursor: pointer;
  }

  .submit-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .submit-btn:not(:disabled):hover {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  @media (max-width: 640px) {
    .hour-group,
    .log-message {
      display: flex;
      flex-direction: column;
    }

    .hour-marker {
      position: static;
    }

    .prompt-mark {
      display: none;
    }

    .inline-suggest-row {
      grid-template-columns: 12px minmax(96px, auto) minmax(0, 1fr);
    }
  }
</style>
