<script lang="ts">
  import { page } from '$app/stores';
  import { marked } from 'marked';
  import { apiClient, apiGet } from '$lib/api/client.js';
  import NeighborPanel from '$lib/components/NeighborPanel.svelte';
  import CodeMirror from '$lib/editor/CodeMirror.svelte';

  interface Note {
    note_id: string;
    title: string;
    body: string;
    frontmatter: Record<string, unknown>;
    created: string | null;
    updated: string | null;
    tags: string[];
    importance: number | null;
  }

  interface NeighborData {
    note_id: string;
    outbound: { note_id: string; title: string; type: string; description?: string }[];
    inbound: { note_id: string; title: string; type: string; description?: string }[];
    semantic: { note_id: string; title: string; type: string; description?: string; confidence?: number }[];
  }

  let note = $state<Note | null>(null);
  let neighbors = $state<NeighborData | null>(null);
  let loadingNote = $state(true);
  let loadingNeighbors = $state(true);
  let error = $state('');
  let renderedBody = $state('');
  let editMode = $state(false);
  let editorDoc = $state('');

  let vaultName = $derived($page.params.vault);
  let noteId = $derived($page.params.id);
  let loadToken = 0;
  const dailyNoteIdPattern = /^\d{4}-\d{2}-\d{2}$/;
  const taskStateOrder = ['[ ]', '[>]', '[x]', '[~]'] as const;
  type TaskState = (typeof taskStateOrder)[number];
  const taskStatePattern = /\[(?: |>|x|~)\]/g;

  function isTagNoteId(id: string) {
    return id.startsWith('tag:');
  }

  function tagNameFromNoteId(id: string) {
    return isTagNoteId(id) ? id.slice(4) : '';
  }

  function tagHref(vault: string, tag: string) {
    return `/${encodeURIComponent(vault)}/notes/${encodeURIComponent(`tag:${tag}`)}`;
  }

  function escapeMarkdownLabel(text: string) {
    return text.replace(/([\\[\]])/g, '\\$1');
  }

  function tagHue(tag: string) {
    let hash = 0;
    for (const char of tag) {
      hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
    }
    return String(hash % 360);
  }

  function hasExcludedAncestor(node: Node) {
    let current = node.parentElement;
    while (current) {
      if (['A', 'BUTTON', 'CODE', 'PRE', 'SCRIPT', 'STYLE'].includes(current.tagName)) {
        return true;
      }
      current = current.parentElement;
    }
    return false;
  }

  function taskStateKind(state: string) {
    if (state === '[>]') return 'wip';
    if (state === '[x]') return 'done';
    if (state === '[~]') return 'cancel';
    return 'todo';
  }

  function taskStateLabel(state: string) {
    if (state === '[>]') return '>';
    if (state === '[x]') return '✓';
    if (state === '[~]') return '~';
    return '';
  }

  function taskStateAriaLabel(state: string) {
    if (state === '[>]') return 'Task status in progress';
    if (state === '[x]') return 'Task status done';
    if (state === '[~]') return 'Task status canceled';
    return 'Task status todo';
  }

  function renderTaskStateButton(state: string, index: number) {
    const kind = taskStateKind(state);
    const label = taskStateLabel(state);
    const ariaLabel = taskStateAriaLabel(state);
    return `<button type="button" class="note-task-state note-task-state-${kind}" data-task-index="${index}" data-task-state="${state}" aria-label="${ariaLabel}">${label}</button>`;
  }

  function forMarkdownTextSegments(markdown: string, mapText: (segment: string) => string) {
    let inFence = false;
    let fenceMarker = '';

    return markdown
      .split('\n')
      .map((line) => {
        const trimmed = line.trimStart();
        const fence = trimmed.match(/^(```+|~~~+)/)?.[1];
        if (fence && (!inFence || fence.startsWith(fenceMarker[0]))) {
          inFence = !inFence;
          fenceMarker = inFence ? fence : '';
          return line;
        }
        if (inFence) return line;

        return line
          .split(/(`[^`]*`)/g)
          .map((segment) => {
            if (segment.startsWith('`') && segment.endsWith('`')) return segment;
            return mapText(segment);
          })
          .join('');
      })
      .join('\n');
  }

  function withTaskStateButtons(markdown: string) {
    let taskIndex = 0;

    return forMarkdownTextSegments(markdown, (segment) =>
      segment.replace(taskStatePattern, (state) => renderTaskStateButton(state, taskIndex++))
    );
  }

  function nextTaskState(state: string): TaskState {
    const index = taskStateOrder.indexOf(state as TaskState);
    return taskStateOrder[(index + 1) % taskStateOrder.length];
  }

  function replaceTaskStateByIndex(markdown: string, targetIndex: number, nextState: TaskState) {
    let taskIndex = 0;
    let didReplace = false;

    const updated = forMarkdownTextSegments(markdown, (segment) =>
      segment.replace(taskStatePattern, (state) => {
        if (taskIndex === targetIndex) {
          didReplace = true;
          taskIndex += 1;
          return nextState;
        }
        taskIndex += 1;
        return state;
      })
    );

    return didReplace ? updated : markdown;
  }

  function appendDecoratedInlineSyntax(fragment: DocumentFragment, text: string, vault: string) {
    const pattern = /(^|[^\p{L}\p{N}_/-])#([\p{L}\p{N}_][\p{L}\p{N}_/-]*)|\[([^\]\n]+)\]/gu;
    let cursor = 0;
    let match: RegExpExecArray | null;

    while ((match = pattern.exec(text))) {
      const fullMatch = match[0];
      const tagPrefix = match[1] ?? '';
      const tagName = match[2];
      const bracketText = match[3];
      const syntaxStart = match.index + (tagName ? tagPrefix.length : 0);
      const syntaxText = tagName ? `#${tagName}` : fullMatch;

      if (syntaxStart > cursor) {
        fragment.append(document.createTextNode(text.slice(cursor, syntaxStart)));
      }

      if (tagName) {
        const link = document.createElement('a');
        link.className = 'note-tag-chip';
        link.href = `/${encodeURIComponent(vault)}/notes/${encodeURIComponent(`tag:${tagName}`)}`;
        link.dataset.tag = tagName;
        link.style.setProperty('--tag-hue', tagHue(tagName));
        link.textContent = syntaxText;
        fragment.append(link);
      } else if (bracketText) {
        const highlight = document.createElement('span');
        highlight.className = 'note-bracket-highlight';
        highlight.textContent = syntaxText;
        fragment.append(highlight);
      }

      cursor = match.index + fullMatch.length;
    }

    if (cursor < text.length) {
      fragment.append(document.createTextNode(text.slice(cursor)));
    }
  }

  function decorateRenderedHtml(html: string, vault: string) {
    const template = document.createElement('template');
    template.innerHTML = html;
    const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_TEXT);
    const textNodes: Text[] = [];

    while (walker.nextNode()) {
      const node = walker.currentNode as Text;
      if (!hasExcludedAncestor(node) && /#[\p{L}\p{N}_]|\[[^\]\n]+\]/u.test(node.data)) {
        textNodes.push(node);
      }
    }

    for (const node of textNodes) {
      const fragment = document.createDocumentFragment();
      appendDecoratedInlineSyntax(fragment, node.data, vault);
      node.replaceWith(fragment);
    }

    return template.innerHTML;
  }

  function wikilinkToMarkdownLinks(markdown: string, vault: string) {
    return forMarkdownTextSegments(markdown, (segment) =>
      segment.replace(/\[\[([^\]\n]+)\]\]/g, (match, rawTarget, offset) => {
        if (segment[offset - 1] === '!') return match;

        const separatorIndex = rawTarget.indexOf('|');
        const target =
          separatorIndex >= 0
            ? rawTarget.slice(0, separatorIndex).trim()
            : rawTarget.trim();
        const label =
          separatorIndex >= 0
            ? rawTarget.slice(separatorIndex + 1).trim()
            : target;

        if (!target) return match;

        const href = `/${encodeURIComponent(vault)}/notes/${encodeURIComponent(target)}`;
        return `[${escapeMarkdownLabel(label || target)}](${href})`;
      })
    );
  }

  async function renderNoteBody(markdown: string, vault: string) {
    const markdownWithLinks = wikilinkToMarkdownLinks(markdown, vault);
    const markdownWithTaskStates = withTaskStateButtons(markdownWithLinks);
    const parsedBody = await marked.parse(markdownWithTaskStates, { async: true });
    return decorateRenderedHtml(parsedBody, vault);
  }

  async function saveTaskState(taskIndex: number, currentState: string) {
    if (!note) return;
    const updatedBody = replaceTaskStateByIndex(note.body ?? '', taskIndex, nextTaskState(currentState));
    if (updatedBody === note.body) return;

    const response = await apiClient(`/api/v1/vault/${vaultName}/notes/${note.note_id}`, {
      method: 'PUT',
      body: JSON.stringify({ body: updatedBody })
    });

    if (!response.ok) {
      throw new Error(`PUT note task state → ${response.status}`);
    }

    const updatedNote = (await response.json()) as Note;
    const body = updatedNote.body ?? updatedBody;
    note = { ...updatedNote, body };
    editorDoc = body;
    renderedBody = await renderNoteBody(body, vaultName);
  }

  function handleNoteBodyClick(event: MouseEvent) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest('button.note-task-state');
    if (!(button instanceof HTMLButtonElement)) return;

    const taskIndex = Number(button.dataset.taskIndex);
    const currentState = button.dataset.taskState ?? '[ ]';
    if (!Number.isFinite(taskIndex)) return;

    event.preventDefault();
    void saveTaskState(taskIndex, currentState);
  }

  function taskStateClickAction(node: HTMLElement) {
    node.addEventListener('click', handleNoteBodyClick);

    return {
      destroy() {
        node.removeEventListener('click', handleNoteBodyClick);
      }
    };
  }

  async function loadNote(vault: string, id: string) {
    const token = ++loadToken;
    note = null;
    neighbors = null;
    loadingNote = true;
    loadingNeighbors = true;
    error = '';
    renderedBody = '';
    editorDoc = '';
    editMode = false;

    const noteEndpoint = dailyNoteIdPattern.test(id)
      ? `/api/v1/vault/${vault}/daily/${id}`
      : `/api/v1/vault/${vault}/notes/${id}`;

    const [noteResult, neighborsResult] = await Promise.allSettled([
      loadOrCreateNote(vault, id, noteEndpoint),
      apiGet<NeighborData>(`/api/v1/vault/${vault}/notes/${id}/neighbors`)
    ]);

    if (token !== loadToken) return;

    if (noteResult.status === 'fulfilled') {
      const loadedNote = noteResult.value;
      const loadedBody = loadedNote.body ?? '';
      const nextRenderedBody = await renderNoteBody(loadedBody, vault);
      if (token !== loadToken) return;
      note = loadedNote;
      editorDoc = loadedBody;
      renderedBody = nextRenderedBody;
    } else {
      error = isTagNoteId(id) ? 'Tag note not found.' : 'Note not found.';
    }
    loadingNote = false;

    if (neighborsResult.status === 'fulfilled') {
      neighbors = neighborsResult.value;
    }
    loadingNeighbors = false;

    // Track last vault
    localStorage.setItem('pkm.lastVault', vault);
  }

  async function loadOrCreateNote(vault: string, id: string, endpoint: string) {
    try {
      return await apiGet<Note>(endpoint);
    } catch (e) {
      if (dailyNoteIdPattern.test(id) || isTagNoteId(id) || !isNotFoundError(e)) {
        throw e;
      }
      const response = await apiClient(
        `/api/v1/vault/${vault}/notes/${encodeURIComponent(id)}/ensure`,
        { method: 'POST' }
      );
      if (!response.ok) throw new Error(`POST ensure note → ${response.status}`);
      return (await response.json()) as Note;
    }
  }

  function isNotFoundError(errorValue: unknown) {
    return errorValue instanceof Error && /(?:→|->)\s*404\b|404/.test(errorValue.message);
  }

  $effect(() => {
    if (!vaultName || !noteId) return;
    void loadNote(vaultName, noteId);
  });
</script>

<svelte:head>
  <title>{note?.title ?? noteId} — pkm</title>
</svelte:head>

<div class="note-page">
  {#if loadingNote}
    <p class="status">Loading…</p>
  {:else if error}
    <div class="missing-note">
      {#if isTagNoteId(noteId)}
        <header class="tag-header">
          <div class="meta-rail">
            <span>TAG HUB</span>
            <span>{neighbors?.inbound?.length ?? 0} linked notes</span>
          </div>
        </header>
      {/if}
      <p class="status error">{error}</p>
      {#if isTagNoteId(noteId)}
        <NeighborPanel
          {vaultName}
          data={neighbors}
          loading={loadingNeighbors}
        />
      {/if}
    </div>
  {:else if note}
    <article class="note-article">
      <header class="note-header">
        <div class="meta-rail">
          <span>NOTE</span>
          <span>{note.note_id}</span>
          {#if note.updated}
            <span>updated {note.updated}</span>
          {:else if note.created}
            <span>created {note.created}</span>
          {/if}
          {#if note.importance !== null}
            <span>imp {note.importance}</span>
          {/if}
        </div>
        <div class="note-header-actions">
          <div class="mode-toggle" aria-label="Display mode">
            <button
              type="button"
              class:active={!editMode}
              onclick={() => (editMode = false)}
            >
              Read
            </button>
            <button
              type="button"
              class:active={editMode}
              onclick={() => (editMode = true)}
            >
              Edit
            </button>
          </div>
        </div>
        {#if note.tags?.length}
          <p class="note-tags">
            {#each note.tags as tag}
              <a
                class="note-tag-chip note-meta-tag-chip"
                href={tagHref(vaultName, tag)}
                data-tag={tag}
                style={`--tag-hue: ${tagHue(tag)}`}
              >#{tag}</a>
            {/each}
          </p>
        {/if}
      </header>

      {#if editMode}
        <div class="note-editor">
          <CodeMirror bind:doc={editorDoc} />
        </div>
      {:else}
        <!-- Rendered markdown body -->
        <!-- eslint-disable-next-line svelte/no-at-html-tags -->
        <div class="note-body prose" use:taskStateClickAction>{@html renderedBody}</div>
      {/if}

      <!-- Signature NeighborPanel -->
      <NeighborPanel
        {vaultName}
        data={neighbors}
        loading={loadingNeighbors}
      />
    </article>
  {/if}
</div>

<style>
  .note-page {
    width: 100%;
    max-width: var(--note-page-width, 1180px);
    margin: 0 auto;
    padding: var(--space-6, 32px) clamp(20px, 4vw, 56px) var(--space-8, 64px);
  }

  .note-article {
    width: 100%;
  }

  .missing-note {
    width: 100%;
  }

  .note-header,
  .tag-header {
    margin-bottom: var(--space-5, 24px);
    border: 0;
    padding: 0;
  }

  .meta-rail {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3, 12px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  .note-header-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: var(--space-3, 12px);
  }

  .note-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    margin: var(--space-3, 12px) 0 0;
  }

  .mode-toggle {
    display: flex;
    align-items: center;
    width: 124px;
    flex-shrink: 0;
    border: 1px solid var(--border);
  }

  .mode-toggle button {
    flex: 1;
    background: none;
    border: none;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 7px 8px;
    cursor: pointer;
  }

  .mode-toggle button + button {
    border-left: 1px solid var(--border);
  }

  .mode-toggle button.active,
  .mode-toggle button:hover {
    color: var(--bg);
    background: var(--accent);
  }

  .note-editor {
    min-height: 60vh;
    border: 1px solid var(--border);
    margin-bottom: var(--space-5, 24px);
    background: var(--surface-prose, var(--bg-elev));
  }

  .note-body {
    background: transparent;
    border: 0;
    border-top: 0;
    max-width: none;
    padding: 0;
    padding-top: 0;
    margin-bottom: var(--space-5, 24px);
    min-width: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .note-body :global(*) {
    max-width: 100%;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  /* Prose styles for rendered markdown */
  .prose :global(h1) {
    font-family: var(--font-display);
    font-size: var(--type-h1-size, 28px);
    font-weight: var(--type-h1-weight, 600);
    line-height: var(--type-h1-lh, 1.20);
    color: var(--text);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(h2) {
    font-family: var(--font-display);
    font-size: var(--type-h2-size, 20px);
    font-weight: var(--type-h2-weight, 600);
    line-height: var(--type-h2-lh, 1.30);
    color: var(--text);
    margin-top: var(--space-6, 32px);
    margin-bottom: var(--space-3, 12px);
  }

  .prose :global(h3) {
    font-family: var(--font-display);
    font-size: var(--type-h3-size, 17px);
    font-weight: var(--type-h3-weight, 600);
    line-height: var(--type-h3-lh, 1.35);
    color: var(--text);
    margin-top: var(--space-5, 24px);
    margin-bottom: var(--space-2, 8px);
  }

  .prose :global(p) {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(a) {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .note-tag-chip,
  .prose :global(a.note-tag-chip) {
    --chip-bg: hsl(var(--tag-hue) 42% 28% / 0.32);
    --chip-border: hsl(var(--tag-hue) 42% 46% / 0.68);
    --chip-text: hsl(var(--tag-hue) 58% 74%);
    display: inline-flex;
    align-items: center;
    min-height: 1.55em;
    padding: 0 0.68em;
    border: 1px solid var(--chip-border);
    border-radius: 999px;
    background: var(--chip-bg);
    color: var(--chip-text);
    font-family: var(--font-mono);
    font-size: 0.84em;
    font-weight: 600;
    line-height: 1;
    text-decoration: none;
    white-space: nowrap;
  }

  .note-meta-tag-chip {
    font-size: 12px;
  }

  .note-meta-tag-chip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .note-meta-tag-chip:hover,
  .note-meta-tag-chip:focus-visible,
  .prose :global(a.note-tag-chip:hover),
  .prose :global(a.note-tag-chip:focus-visible) {
    color: hsl(var(--tag-hue) 66% 84%);
    border-color: hsl(var(--tag-hue) 48% 54% / 0.88);
    background: hsl(var(--tag-hue) 44% 32% / 0.42);
    outline: none;
  }

  .prose :global(.note-bracket-highlight) {
    color: color-mix(in srgb, var(--accent) 76%, var(--text) 24%);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-bottom: 1px solid color-mix(in srgb, var(--accent) 38%, transparent);
    padding: 0 0.15em;
  }

  .prose :global(.note-task-state) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.28em;
    height: 1.28em;
    margin: 0 0.48em 0 0;
    padding: 0;
    border: 1px solid #6b7280;
    border-radius: 3px;
    background: #3f454d;
    color: #d7dbe0;
    font-family: var(--font-mono);
    font-size: 0.9em;
    font-weight: 800;
    line-height: 1;
    cursor: pointer;
    vertical-align: -0.12em;
  }

  .prose :global(.note-task-state:hover),
  .prose :global(.note-task-state:focus-visible) {
    outline: 2px solid color-mix(in srgb, var(--accent) 72%, transparent);
    outline-offset: 2px;
  }

  .prose :global(.note-task-state-wip) {
    border-color: #d8b84c;
    background: #f4df8b;
    color: #5d4a00;
  }

  .prose :global(.note-task-state-done) {
    border-color: #237a3b;
    background: #2f9d4c;
    color: #f5fff7;
  }

  .prose :global(.note-task-state-cancel) {
    border-color: #9c2f2f;
    background: #c94b4b;
    color: #fff5f5;
  }

  .prose :global(code) {
    font-family: var(--font-mono);
    font-size: 0.9em;
    background-color: var(--surface-raised, var(--bg));
    padding: 1px 4px;
  }

  .prose :global(pre) {
    font-family: var(--font-mono);
    font-size: 13px;
    background-color: var(--surface-raised, var(--bg));
    padding: var(--space-4, 16px);
    overflow-x: hidden;
    white-space: pre-wrap;
    margin-bottom: var(--space-4, 16px);
    border: 0;
  }

  .prose :global(pre code) {
    background: none;
    padding: 0;
  }

  .prose :global(blockquote) {
    border: 1px solid color-mix(in srgb, var(--border) 76%, transparent);
    border-left: 3px solid color-mix(in srgb, var(--accent) 38%, var(--border));
    border-radius: 6px;
    padding: var(--space-3, 12px) var(--space-4, 16px);
    margin: 0 0 var(--space-4, 16px);
    background: color-mix(in srgb, var(--surface-raised, var(--bg)) 82%, #000 18%);
    color: color-mix(in srgb, var(--text-muted) 76%, var(--text-faint) 24%);
    font-style: normal;
  }

  .prose :global(blockquote p),
  .prose :global(blockquote li) {
    color: inherit;
  }

  .prose :global(blockquote p:last-child) {
    margin-bottom: 0;
  }

  .prose :global(ul),
  .prose :global(ol) {
    padding-left: var(--space-5, 24px);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(li) {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    list-style: disc;
  }

  .prose :global(ol li) {
    list-style: decimal;
  }

  .prose :global(hr) {
    border: none;
    border-top: 1px solid var(--border);
    margin: var(--space-6, 32px) 0;
  }

  .status {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .status.error {
    color: #c0392b;
  }

  @media (max-width: 640px) {
    .mode-toggle {
      width: 100%;
    }

    .note-page {
      padding-right: var(--space-4, 16px);
      padding-left: var(--space-4, 16px);
    }
  }
</style>
