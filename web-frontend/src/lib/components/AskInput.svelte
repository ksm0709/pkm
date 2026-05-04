<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { apiGet } from '$lib/api/client.js';
  import {
    applyInlineSuggestion,
    detectInlineTrigger,
    fetchInlineSuggestions
  } from '$lib/inline-suggestions.js';

  interface Props {
    vaultName: string;
    value?: string;
    busy?: boolean;
    modelLabel?: string;
    onsubmit: (text: string) => void;
  }

  let {
    vaultName,
    value = $bindable(''),
    busy = false,
    modelLabel = 'auto',
    onsubmit
  }: Props = $props();

  type SlashKind = 'session' | 'skill' | 'workflow';

  type SlashItem = {
    kind: SlashKind;
    command: string;
    label: string;
    hint: string;
    keywords: string[];
  };

  type WorkflowSummary = {
    id: string;
    title?: string;
    snippet?: string;
    pre_hook?: string | null;
    post_hook?: string | null;
  };

  let textareaEl: HTMLTextAreaElement | null = $state(null);
  let workflows = $state<WorkflowSummary[]>([]);
  let slashActiveIndex = $state(0);
  let slashCompleting = $state(false);
  let slashCompletedValue = $state('');
  let inlineRows = $state<any[]>([]);
  let inlineActiveIndex = $state(0);
  let inlineTrigger = $state<any | null>(null);
  let inlineRequestId = 0;

  const staticSlashItems: SlashItem[] = [
    {
      kind: 'session',
      command: '/new',
      label: 'New session',
      hint: 'clear cached ask context',
      keywords: ['clear', 'reset', 'fresh', 'context', 'history', 'cache']
    },
    {
      kind: 'skill',
      command: '/pkm',
      label: 'PKM skill',
      hint: 'tiny-agent skill',
      keywords: ['notes', 'daily', 'search', 'tags', 'wikilinks', 'zettelkasten']
    },
    {
      kind: 'skill',
      command: '/pkm:diagnosis',
      label: 'PKM diagnosis workflow',
      hint: 'tiny-agent skill',
      keywords: ['diagnosis', 'compliance', 'session', 'audit']
    }
  ];

  let slashQuery = $derived(value.startsWith('/') ? value.slice(1).trim() : '');
  let slashRows = $derived(buildSlashRows(slashQuery, workflows));
  let slashMenuOpen = $derived(
    value.startsWith('/') &&
      !slashCompleting &&
      value !== slashCompletedValue &&
      !busy &&
      slashRows.length > 0
  );
  let inlineMenuOpen = $derived(!busy && inlineTrigger && inlineRows.length > 0);

  onMount(() => {
    void loadWorkflows();
  });

  $effect(() => {
    const currentValue = value;
    const currentVault = vaultName;
    const currentTextarea = textareaEl;
    if (!currentTextarea) return;
    void tick().then(() => {
      const cursor = currentTextarea.selectionStart ?? currentValue.length;
      void refreshInlineSuggestions(currentValue, cursor, currentVault);
    });
  });

  async function loadWorkflows() {
    try {
      workflows = await apiGet<WorkflowSummary[]>(`/api/v1/vault/${vaultName}/workflows`);
    } catch {
      workflows = [];
    }
  }

  function workflowSlashItems(items: WorkflowSummary[]): SlashItem[] {
    return items.map((workflow) => ({
      kind: 'workflow' as const,
      command: `/workflow ${workflow.id}`,
      label: workflow.title || workflow.id,
      hint: workflow.snippet || 'workflow',
      keywords: [
        workflow.id,
        workflow.title ?? '',
        workflow.snippet ?? '',
        workflow.pre_hook ?? '',
        workflow.post_hook ?? ''
      ].filter(Boolean)
    }));
  }

  function normalize(text: string) {
    return text.toLowerCase().replace(/[_/-]+/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function scoreSlashItem(item: SlashItem, query: string, index: number) {
    if (!query) return index;
    const q = normalize(query);
    const fields = [
      item.command,
      item.command.slice(1),
      item.label,
      item.hint,
      ...item.keywords
    ].map(normalize);
    let best = Number.POSITIVE_INFINITY;
    for (const field of fields) {
      if (!field) continue;
      if (field === q) best = Math.min(best, 0);
      else if (field.startsWith(q)) best = Math.min(best, 10);
      else {
        const includesAt = field.indexOf(q);
        if (includesAt >= 0) best = Math.min(best, 30 + includesAt);
      }
    }
    const terms = q.split(' ').filter(Boolean);
    if (terms.length > 1 && fields.some((field) => terms.every((term) => field.includes(term)))) {
      best = Math.min(best, 50);
    }
    return best + index / 100;
  }

  function buildSlashRows(query: string, workflowList: WorkflowSummary[]) {
    const all = [...staticSlashItems, ...workflowSlashItems(workflowList)];
    return all
      .map((item, index) => ({ item, score: scoreSlashItem(item, query, index) }))
      .filter((entry) => Number.isFinite(entry.score))
      .sort((a, b) => a.score - b.score || a.item.command.localeCompare(b.item.command))
      .slice(0, 12)
      .map((entry) => entry.item);
  }

  function resetTextareaHeight() {
    if (textareaEl) textareaEl.style.height = 'auto';
  }

  function completeSlashItem(item: SlashItem) {
    value = item.command;
    slashCompleting = true;
    slashCompletedValue = item.command;
    slashActiveIndex = 0;
    void tick().then(() => {
      textareaEl?.focus();
      textareaEl?.setSelectionRange(value.length, value.length);
      autoresize();
    });
  }

  function submitText(text: string) {
    if (!text || busy) return;
    onsubmit(text);
    value = '';
    slashCompleting = false;
    slashCompletedValue = '';
    slashActiveIndex = 0;
    resetTextareaHeight();
  }

  async function refreshInlineSuggestions(
    currentValue = value,
    cursor = textareaEl?.selectionStart ?? value.length,
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
    const result = applyInlineSuggestion(value, inlineTrigger, row);
    value = result.value;
    inlineRows = [];
    inlineTrigger = null;
    inlineActiveIndex = 0;
    void tick().then(() => {
      textareaEl?.focus();
      textareaEl?.setSelectionRange(result.cursor, result.cursor);
      autoresize();
    });
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

    if (slashMenuOpen) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        slashActiveIndex = (slashActiveIndex + 1) % slashRows.length;
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        slashActiveIndex = (slashActiveIndex - 1 + slashRows.length) % slashRows.length;
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        value = '';
        slashCompleting = false;
        slashCompletedValue = '';
        slashActiveIndex = 0;
        resetTextareaHeight();
        return;
      }
      if (event.key === 'Enter' && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        const item = slashRows[slashActiveIndex];
        if (item) completeSlashItem(item);
        return;
      }
    }

    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submitText(value.trim());
    }
    // Plain Enter inserts newline (default textarea behavior)
  }

  function autoresize() {
    if (!textareaEl) return;
    textareaEl.style.height = 'auto';
    textareaEl.style.height = `${Math.min(textareaEl.scrollHeight, 240)}px`;
    if (!value.startsWith('/')) {
      slashCompleting = false;
      slashCompletedValue = '';
      slashActiveIndex = 0;
    } else if (value !== slashCompletedValue) {
      slashCompleting = false;
      slashActiveIndex = 0;
    } else if (!slashCompleting) {
      slashActiveIndex = 0;
    }
  }

  function handleInput() {
    if (textareaEl) value = textareaEl.value;
    autoresize();
  }
</script>

<form
  class="ask-input"
  onsubmit={(e) => {
    e.preventDefault();
    submitText(value.trim());
  }}
>
  {#if slashMenuOpen}
    <div class="ask-slash-menu" role="listbox" aria-label="Slash commands">
      {#each slashRows as item, i (`${item.kind}:${item.command}`)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div
          class="slash-row"
          class:active={i === slashActiveIndex}
          role="option"
          aria-selected={i === slashActiveIndex}
          tabindex="-1"
          onmousemove={() => (slashActiveIndex = i)}
          onmousedown={(event) => event.preventDefault()}
          onclick={() => completeSlashItem(item)}
        >
          <span class="slash-glyph" aria-hidden="true">{i === slashActiveIndex ? '>' : ''}</span>
          <span class="slash-command">{item.command}</span>
          <span class="slash-kind">{item.kind}</span>
          <span class="slash-label">{item.label}</span>
          <span class="slash-hint">{item.hint}</span>
        </div>
      {/each}
    </div>
  {/if}
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
  <span class="prompt-mark" aria-hidden="true">ASK</span>
  <span class="model-label">model {modelLabel}</span>
  <textarea
    bind:this={textareaEl}
    bind:value
    class="ask-textarea"
    placeholder={busy ? 'Streaming…' : 'Ask… (⌘↵ to submit, ↵ newline)'}
    rows="1"
    onkeydown={handleKeydown}
    oninput={handleInput}
    disabled={busy}
    spellcheck="false"
  ></textarea>
  <button
    type="submit"
    class="submit-btn"
    disabled={busy || !value.trim()}
    aria-label="Submit"
  >
    ⌘↵
  </button>
</form>

<style>
  .ask-input {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    min-height: 56px;
    padding: var(--space-3, 12px) var(--space-4, 16px) var(--space-2, 8px);
    background-color: transparent;
    border-left: 2px solid var(--accent);
  }

  .ask-slash-menu {
    position: absolute;
    right: 0;
    bottom: calc(100% + 1px);
    left: 0;
    z-index: 4;
    max-height: min(320px, 42vh);
    overflow-y: auto;
    border-top: 1px solid var(--accent);
    border-bottom: 1px solid var(--border);
    background: var(--surface, var(--bg));
    color: var(--text);
    font-family: var(--font-mono);
    box-shadow: 0 -10px 28px rgba(0, 0, 0, 0.12);
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

  .slash-row {
    display: grid;
    grid-template-columns: 14px minmax(112px, auto) auto minmax(120px, 1fr) minmax(0, 1fr);
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

  .slash-row.active {
    border-left-color: var(--accent);
    background: var(--accent-bg);
    color: var(--text);
  }

  .slash-glyph,
  .slash-command,
  .slash-kind {
    color: var(--accent);
  }

  .slash-command {
    font-weight: 600;
    white-space: nowrap;
  }

  .slash-kind {
    border: 1px solid var(--border);
    padding: 1px var(--space-1, 4px);
    color: var(--text-faint);
    font-size: 10px;
    line-height: 1.2;
    text-transform: uppercase;
  }

  .slash-label,
  .slash-hint {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .slash-hint {
    color: var(--text-faint);
  }

  .prompt-mark {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    color: var(--accent);
    flex-shrink: 0;
  }

  .model-label {
    position: absolute;
    top: 3px;
    left: var(--space-4, 16px);
    max-width: min(42ch, calc(100% - 96px));
    overflow: hidden;
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: 10px;
    line-height: 1.2;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ask-textarea {
    flex: 1;
    resize: none;
    min-height: 32px;
    max-height: 240px;
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    background-color: transparent;
    border: none;
    border-radius: 0;
    padding: var(--space-1, 4px) var(--space-2, 8px);
    outline: none;
    caret-color: var(--accent);
  }

  .ask-textarea::placeholder {
    color: var(--text-faint);
  }

  .submit-btn {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--accent);
    background-color: transparent;
    border: 0;
    border-radius: var(--radius-sm, 2px);
    padding: var(--space-2, 8px) var(--space-3, 12px);
    cursor: pointer;
    flex-shrink: 0;
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
    .prompt-mark {
      display: none;
    }

    .slash-row {
      grid-template-columns: 12px minmax(96px, auto) auto minmax(0, 1fr);
    }

    .slash-hint {
      display: none;
    }

    .inline-suggest-row {
      grid-template-columns: 12px minmax(96px, auto) minmax(0, 1fr);
    }
  }
</style>
