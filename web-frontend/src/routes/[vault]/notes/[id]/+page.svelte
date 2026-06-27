<script lang="ts">
  import { onDestroy, onMount, untrack } from "svelte";
  import { page } from "$app/stores";
  import { apiClient, apiGet } from "$lib/api/client.js";
  import MarkdownRenderer from "$lib/components/MarkdownRenderer.svelte";
  import NeighborPanel from "$lib/components/NeighborPanel.svelte";
  import CodeMirror from "$lib/editor/CodeMirror.svelte";
  import { tagHue } from "$lib/notes/rendered-markdown.js";
  import { graphKeyNav } from "$lib/navigation/graph-keynav.svelte";
  import { rememberVault } from "$lib/vault/remembered-vault";

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
    outbound: {
      note_id: string;
      title: string;
      type: string;
      description?: string;
    }[];
    inbound: {
      note_id: string;
      title: string;
      type: string;
      description?: string;
    }[];
    semantic: {
      note_id: string;
      title: string;
      type: string;
      description?: string;
      confidence?: number;
    }[];
  }

  let note = $state<Note | null>(null);
  let neighbors = $state<NeighborData | null>(null);
  let loadingNote = $state(true);
  let loadingNeighbors = $state(true);
  let error = $state("");
  let editMode = $state(false);
  let editorDoc = $state("");
  let savedDoc = $state("");
  let editorMode = $state<"vim" | "plain">("vim");
  let saving = $state(false);
  let saveError = $state("");
  let saveStatus = $state("");

  let vaultName = $derived($page.params.vault);
  let noteId = $derived($page.params.id);
  let editorDirty = $derived(editorDoc !== savedDoc);
  let loadToken = 0;
  const dailyNoteIdPattern = /^\d{4}-\d{2}-\d{2}$/;
  const taskStateOrder = ["[ ]", "[>]", "[x]", "[~]"] as const;
  type TaskState = (typeof taskStateOrder)[number];
  const taskStatePattern = /\[(?: |>|x|~)\]/g;

  function isTagNoteId(id: string) {
    return id.startsWith("tag:");
  }

  function tagNameFromNoteId(id: string) {
    return isTagNoteId(id) ? id.slice(4) : "";
  }

  function tagHref(vault: string, tag: string) {
    return `/${encodeURIComponent(vault)}/notes/${encodeURIComponent(`tag:${tag}`)}`;
  }

  function taskStateKind(state: string) {
    if (state === "[>]") return "wip";
    if (state === "[x]") return "done";
    if (state === "[~]") return "cancel";
    return "todo";
  }

  function taskStateLabel(state: string) {
    if (state === "[>]") return ">";
    if (state === "[x]") return "✓";
    if (state === "[~]") return "~";
    return "";
  }

  function taskStateAriaLabel(state: string) {
    if (state === "[>]") return "Task status in progress";
    if (state === "[x]") return "Task status done";
    if (state === "[~]") return "Task status canceled";
    return "Task status todo";
  }

  function renderTaskStateButton(state: string, index: number) {
    const kind = taskStateKind(state);
    const label = taskStateLabel(state);
    const ariaLabel = taskStateAriaLabel(state);
    return `<button type="button" class="note-task-state note-task-state-${kind}" data-task-index="${index}" data-task-state="${state}" aria-label="${ariaLabel}">${label}</button>`;
  }

  function forMarkdownTextSegments(
    markdown: string,
    mapText: (segment: string) => string,
  ) {
    let inFence = false;
    let fenceMarker = "";

    return markdown
      .split("\n")
      .map((line) => {
        const trimmed = line.trimStart();
        const fence = trimmed.match(/^(```+|~~~+)/)?.[1];
        if (fence && (!inFence || fence.startsWith(fenceMarker[0]))) {
          inFence = !inFence;
          fenceMarker = inFence ? fence : "";
          return line;
        }
        if (inFence) return line;

        return line
          .split(/(`[^`]*`)/g)
          .map((segment) => {
            if (segment.startsWith("`") && segment.endsWith("`"))
              return segment;
            return mapText(segment);
          })
          .join("");
      })
      .join("\n");
  }

  function withTaskStateButtons(markdown: string) {
    let taskIndex = 0;

    return forMarkdownTextSegments(markdown, (segment) =>
      segment.replace(taskStatePattern, (state) =>
        renderTaskStateButton(state, taskIndex++),
      ),
    );
  }

  function nextTaskState(state: string): TaskState {
    const index = taskStateOrder.indexOf(state as TaskState);
    return taskStateOrder[(index + 1) % taskStateOrder.length];
  }

  function replaceTaskStateByIndex(
    markdown: string,
    targetIndex: number,
    nextState: TaskState,
  ) {
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
      }),
    );

    return didReplace ? updated : markdown;
  }

  async function saveTaskState(taskIndex: number, currentState: string) {
    if (!note) return;
    const updatedBody = replaceTaskStateByIndex(
      note.body ?? "",
      taskIndex,
      nextTaskState(currentState),
    );
    if (updatedBody === note.body) return;

    const response = await apiClient(
      `/api/v1/vault/${vaultName}/notes/${note.note_id}`,
      {
        method: "PUT",
        body: JSON.stringify({ body: updatedBody }),
      },
    );

    if (!response.ok) {
      throw new Error(`PUT note task state → ${response.status}`);
    }

    const updatedNote = (await response.json()) as Note;
    const body = updatedNote.body ?? updatedBody;
    note = { ...updatedNote, body };
    editorDoc = body;
    savedDoc = body;
  }

  function handleNoteBodyClick(event: MouseEvent) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("button.note-task-state");
    if (!(button instanceof HTMLButtonElement)) return;

    const taskIndex = Number(button.dataset.taskIndex);
    const currentState = button.dataset.taskState ?? "[ ]";
    if (!Number.isFinite(taskIndex)) return;

    event.preventDefault();
    void saveTaskState(taskIndex, currentState);
  }

  function taskStateClickAction(node: HTMLElement) {
    node.addEventListener("click", handleNoteBodyClick);

    return {
      destroy() {
        node.removeEventListener("click", handleNoteBodyClick);
      },
    };
  }

  interface SelectedAnnotation {
    quote: string;
    range: Range;
    key: string;
  }

  interface AnnotateMenu {
    x: number;
    y: number;
    quote: string;
    selectionKey: string;
  }

  let annotateMenu = $state<AnnotateMenu | null>(null);
  let annotateDialog = $state<{ quote: string } | null>(null);
  let annotationText = $state("");
  let annotationAddToLog = $state(false);
  let annotationSaving = $state(false);
  let annotationError = $state("");
  let longPressTimer: ReturnType<typeof setTimeout> | null = null;
  let noteBodyElement = $state<HTMLElement | null>(null);
  let annotateMenuInteracting = false;
  const annotateMenuOffset = 10;
  const annotateMenuEdgeInset = 8;
  const annotateMenuEstimatedWidth = 160;
  const annotateMenuEstimatedHeight = 40;

  function selectedAnnotationInside(
    container: HTMLElement,
  ): SelectedAnnotation | null {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      return null;
    }
    const range = selection.getRangeAt(0);
    if (!container.contains(range.commonAncestorContainer)) return null;
    const quote = selection.toString().trim();
    if (!quote) return null;
    return {
      quote,
      range,
      key: `${quote}\u0000${range.startOffset}\u0000${range.endOffset}`,
    };
  }

  function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
  }

  function rectHasLayout(rect: DOMRect) {
    return rect.width > 0 || rect.height > 0;
  }

  function positionForSelection(
    range: Range,
    fallback: { x: number; y: number },
  ) {
    const measuredRange = range as Range & {
      getBoundingClientRect?: () => DOMRect;
    };
    const rect = measuredRange.getBoundingClientRect?.();
    if (!rect || !rectHasLayout(rect)) {
      return {
        x: Math.round(fallback.x),
        y: Math.round(fallback.y),
      };
    }

    const halfWidth = annotateMenuEstimatedWidth / 2;
    const viewportWidth =
      window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight =
      window.innerHeight || document.documentElement.clientHeight;
    const x = rect.left + rect.width / 2;
    const y = rect.bottom + annotateMenuOffset;

    return {
      x: Math.round(
        clamp(
          x,
          annotateMenuEdgeInset + halfWidth,
          viewportWidth - annotateMenuEdgeInset - halfWidth,
        ),
      ),
      y: Math.round(
        clamp(
          y,
          annotateMenuEdgeInset,
          viewportHeight - annotateMenuEdgeInset - annotateMenuEstimatedHeight,
        ),
      ),
    };
  }

  function showAnnotateMenu(
    selected: SelectedAnnotation,
    fallback: { x: number; y: number },
  ) {
    const position = positionForSelection(selected.range, fallback);
    annotateMenu = {
      ...position,
      quote: selected.quote,
      selectionKey: selected.key,
    };
  }

  function handleNoteBodyContextMenu(event: MouseEvent) {
    const noteBodyEl = event.currentTarget as HTMLElement;
    const selected = selectedAnnotationInside(noteBodyEl);
    if (!selected) return;
    event.preventDefault();
    showAnnotateMenu(selected, { x: event.clientX, y: event.clientY });
  }

  function clearLongPressTimer() {
    if (longPressTimer !== null) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
    }
  }

  function dismissAnnotateMenu() {
    clearLongPressTimer();
    annotateMenu = null;
  }

  function handleNoteBodyPointerDown(event: PointerEvent) {
    if (event.pointerType !== "touch") return;
    const noteBodyEl = event.currentTarget as HTMLElement;
    const fallback = { x: event.clientX, y: event.clientY };
    clearLongPressTimer();
    longPressTimer = setTimeout(() => {
      const selected = selectedAnnotationInside(noteBodyEl);
      if (selected) {
        showAnnotateMenu(selected, fallback);
      }
      longPressTimer = null;
    }, 600);
  }

  function openAnnotateDialog() {
    if (!annotateMenu) return;
    annotateDialog = { quote: annotateMenu.quote };
    annotationText = "";
    annotationAddToLog = false;
    annotationError = "";
    annotateMenu = null;
  }

  function closeAnnotateDialog() {
    annotateDialog = null;
    annotationText = "";
    annotationAddToLog = false;
    annotationError = "";
    annotationSaving = false;
  }

  function resetAnnotationState() {
    clearLongPressTimer();
    annotateMenu = null;
    closeAnnotateDialog();
  }

  function listContinuation(value: string) {
    return value
      .split(/\r?\n/)
      .map((line) => line.trimEnd())
      .join("\n    ");
  }

  function appendAnnotationToBody(body: string, quote: string, text: string) {
    const wrappedQuote = `“${quote.replace(/\s+/g, " ").trim()}”`;
    const entry = `- ${wrappedQuote}\n  - ${listContinuation(text)}`;
    const existing = (body ?? "").replace(/\s+$/, "");
    if (/^## Annotations\b/m.test(existing)) {
      return `${existing}\n${entry}\n`;
    }
    const separator = existing.length > 0 ? "\n\n" : "";
    return `${existing}${separator}## Annotations\n${entry}\n`;
  }

  function isCurrentAnnotationTarget(
    targetVault: string,
    targetNoteId: string,
  ) {
    return (
      vaultName === targetVault &&
      noteId === targetNoteId &&
      note?.note_id === targetNoteId
    );
  }

  async function saveAnnotation() {
    if (!note || !annotateDialog || annotationSaving) return;
    const quote = annotateDialog.quote;
    const text = annotationText.trim();
    if (!text) {
      annotationError = "Annotation text is required.";
      return;
    }
    annotationSaving = true;
    annotationError = "";
    const shouldLog = annotationAddToLog;
    const targetVault = vaultName;
    const targetNoteId = note.note_id;
    const encodedNoteId = encodeURIComponent(targetNoteId);
    const updatedBody = appendAnnotationToBody(note.body ?? "", quote, text);

    try {
      const response = await apiClient(
        `/api/v1/vault/${targetVault}/notes/${encodedNoteId}`,
        {
          method: "PUT",
          body: JSON.stringify({ body: updatedBody }),
        },
      );

      if (!response.ok) {
        throw new Error(`PUT annotation -> ${response.status}`);
      }

      const updatedNote = (await response.json()) as Note;
      if (!isCurrentAnnotationTarget(targetVault, targetNoteId)) return;
      const body = updatedNote.body ?? updatedBody;

      if (shouldLog) {
        const logResponse = await apiClient(
          `/api/v1/vault/${targetVault}/daily/today`,
          {
            method: "POST",
            body: JSON.stringify({
              type: "entry",
              content: `Annotated [[${targetNoteId}]]: “${quote.replace(/\s+/g, " ").trim()}” — ${text}`,
            }),
          },
        );
        if (!logResponse.ok) {
          throw new Error(`POST daily log -> ${logResponse.status}`);
        }
      }

      if (!isCurrentAnnotationTarget(targetVault, targetNoteId)) return;
      note = { ...updatedNote, body };
      editorDoc = body;
      savedDoc = body;
      closeAnnotateDialog();
    } catch (e) {
      if (!isCurrentAnnotationTarget(targetVault, targetNoteId)) return;
      annotationError =
        e instanceof Error ? e.message : "Failed to save annotation.";
    } finally {
      if (isCurrentAnnotationTarget(targetVault, targetNoteId)) {
        annotationSaving = false;
      }
    }
  }

  async function loadNote(vault: string, id: string) {
    const token = ++loadToken;
    note = null;
    neighbors = null;
    loadingNote = true;
    loadingNeighbors = true;
    error = "";
    editorDoc = "";
    savedDoc = "";
    saveError = "";
    saveStatus = "";
    editMode = false;
    resetAnnotationState();
    graphKeyNav.clearCurrentNoteNavigationContext();

    const noteEndpoint = dailyNoteIdPattern.test(id)
      ? `/api/v1/vault/${vault}/daily/${id}`
      : `/api/v1/vault/${vault}/notes/${id}`;

    const [noteResult, neighborsResult] = await Promise.allSettled([
      loadOrCreateNote(vault, id, noteEndpoint),
      apiGet<NeighborData>(`/api/v1/vault/${vault}/notes/${id}/neighbors`),
    ]);

    if (token !== loadToken) return;

    let loadedNote: Note | null = null;
    if (noteResult.status === "fulfilled") {
      loadedNote = noteResult.value;
      const loadedBody = loadedNote.body ?? "";
      if (token !== loadToken) return;
      note = loadedNote;
      editorDoc = loadedBody;
      savedDoc = loadedBody;
    } else {
      error = isTagNoteId(id) ? "Tag note not found." : "Note not found.";
    }
    loadingNote = false;

    if (neighborsResult.status === "fulfilled") {
      neighbors = neighborsResult.value;
    }
    loadingNeighbors = false;

    if (loadedNote && neighborsResult.status === "fulfilled") {
      graphKeyNav.setCurrentNoteNavigationContext(
        vault,
        loadedNote.note_id,
        neighborsResult.value.semantic ?? [],
      );
    } else {
      graphKeyNav.clearCurrentNoteNavigationContext(vault, id);
    }

    rememberVault(vault);
  }

  async function loadOrCreateNote(vault: string, id: string, endpoint: string) {
    try {
      return await apiGet<Note>(endpoint);
    } catch (e) {
      if (
        dailyNoteIdPattern.test(id) ||
        isTagNoteId(id) ||
        !isNotFoundError(e)
      ) {
        throw e;
      }
      const response = await apiClient(
        `/api/v1/vault/${vault}/notes/${encodeURIComponent(id)}/ensure`,
        { method: "POST" },
      );
      if (!response.ok)
        throw new Error(`POST ensure note → ${response.status}`);
      return (await response.json()) as Note;
    }
  }

  function isNotFoundError(errorValue: unknown) {
    return (
      errorValue instanceof Error &&
      /(?:→|->)\s*404\b|404/.test(errorValue.message)
    );
  }

  async function saveNoteBody() {
    if (!note || saving || !editorDirty) return;
    saving = true;
    saveError = "";
    saveStatus = "Saving";

    try {
      const response = await apiClient(
        `/api/v1/vault/${vaultName}/notes/${encodeURIComponent(note.note_id)}`,
        {
          method: "PUT",
          body: JSON.stringify({ body: editorDoc }),
        },
      );
      if (!response.ok) throw new Error(`PUT note body -> ${response.status}`);

      const updatedNote = (await response.json()) as Note;
      const body = updatedNote.body ?? editorDoc;
      note = { ...updatedNote, body };
      editorDoc = body;
      savedDoc = body;
      saveStatus = "Saved";
    } catch (e) {
      saveError = e instanceof Error ? e.message : "Failed to save note.";
      saveStatus = "Unsaved";
    } finally {
      saving = false;
    }
  }

  $effect(() => {
    if (!vaultName || !noteId) return;
    untrack(() => {
      void loadNote(vaultName, noteId);
    });
  });

  onMount(() => {
    const handleSelectionChange = () => {
      if (!annotateMenu || annotateMenuInteracting || !noteBodyElement) return;
      const selected = selectedAnnotationInside(noteBodyElement);
      if (!selected || selected.key !== annotateMenu.selectionKey) {
        annotateMenu = null;
      }
    };

    const handleGlobalPointerDown = (event: PointerEvent) => {
      const target = event.target;
      const isInsideMenu =
        target instanceof Element && Boolean(target.closest(".annotate-menu"));
      if (isInsideMenu) {
        annotateMenuInteracting = true;
        window.setTimeout(() => {
          annotateMenuInteracting = false;
        }, 250);
        return;
      }
      if (annotateMenu) annotateMenu = null;
    };

    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismissAnnotateMenu();
    };

    document.addEventListener("selectionchange", handleSelectionChange);
    document.addEventListener("pointerdown", handleGlobalPointerDown, true);
    document.addEventListener("keydown", handleGlobalKeyDown);
    window.addEventListener("scroll", dismissAnnotateMenu, true);
    window.addEventListener("wheel", dismissAnnotateMenu, { passive: true });
    window.addEventListener("touchmove", dismissAnnotateMenu, {
      passive: true,
    });

    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
      document.removeEventListener(
        "pointerdown",
        handleGlobalPointerDown,
        true,
      );
      document.removeEventListener("keydown", handleGlobalKeyDown);
      window.removeEventListener("scroll", dismissAnnotateMenu, true);
      window.removeEventListener("wheel", dismissAnnotateMenu);
      window.removeEventListener("touchmove", dismissAnnotateMenu);
    };
  });

  onDestroy(() => {
    resetAnnotationState();
    graphKeyNav.clearCurrentNoteNavigationContext(vaultName, noteId);
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
                style={`--tag-hue: ${tagHue(tag)}`}>#{tag}</a
              >
            {/each}
          </p>
        {/if}
      </header>

      {#if editMode}
        <div class="editor-toolbar" aria-label="Editor controls">
          <div class="editor-mode-toggle" aria-label="Editor mode">
            <button
              type="button"
              class:active={editorMode === "vim"}
              aria-pressed={editorMode === "vim"}
              onclick={() => (editorMode = "vim")}
            >
              Vim
            </button>
            <button
              type="button"
              class:active={editorMode === "plain"}
              aria-pressed={editorMode === "plain"}
              onclick={() => (editorMode = "plain")}
            >
              Plain
            </button>
          </div>
          <span
            class:error={!!saveError}
            class="editor-save-status"
            aria-live="polite"
          >
            {saveError ||
              (saving
                ? "Saving"
                : editorDirty
                  ? "Unsaved"
                  : saveStatus || "Saved")}
          </span>
          <button
            type="button"
            class="save-note-button"
            aria-label="Save note"
            disabled={!editorDirty || saving}
            onclick={() => void saveNoteBody()}
          >
            Save
          </button>
        </div>
        <div class="note-editor">
          {#key editorMode}
            <CodeMirror
              bind:doc={editorDoc}
              vimMode={editorMode === "vim"}
              onSave={saveNoteBody}
            />
          {/key}
        </div>
      {:else}
        <!-- Rendered markdown body -->
        <div
          bind:this={noteBodyElement}
          class="note-body prose"
          role="region"
          aria-label="Note body"
          use:taskStateClickAction
          oncontextmenu={handleNoteBodyContextMenu}
          onpointerdown={handleNoteBodyPointerDown}
          onpointerup={clearLongPressTimer}
          onpointercancel={clearLongPressTimer}
          onpointerleave={clearLongPressTimer}
        >
          <MarkdownRenderer
            markdown={note.body ?? ""}
            vault={vaultName}
            transformMarkdown={withTaskStateButtons}
          />
        </div>
      {/if}

      {#if annotateMenu}
        <div
          class="annotate-menu"
          style="left:{annotateMenu.x}px;top:{annotateMenu.y}px;"
        >
          <button
            type="button"
            aria-label="Annotate selection"
            onclick={openAnnotateDialog}
          >
            Annotate
          </button>
        </div>
      {/if}

      {#if annotateDialog}
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Annotate selection"
          class="annotate-dialog"
        >
          <p class="annotate-quote">“{annotateDialog.quote}”</p>
          <label class="annotate-field">
            <span>Annotation</span>
            <textarea
              aria-label="Annotation text"
              bind:value={annotationText}
              disabled={annotationSaving}
            ></textarea>
          </label>
          {#if annotationError}
            <p class="annotate-error" aria-live="polite">{annotationError}</p>
          {/if}
          <label class="annotate-checkbox">
            <input
              type="checkbox"
              aria-label="Add annotation to daily log"
              bind:checked={annotationAddToLog}
              disabled={annotationSaving}
            />
            <span>Add to daily log</span>
          </label>
          <div class="annotate-actions">
            <button
              type="button"
              onclick={closeAnnotateDialog}
              aria-label="Cancel annotation"
              disabled={annotationSaving}
            >
              Cancel
            </button>
            <button
              type="button"
              aria-label="Save annotation"
              onclick={() => void saveAnnotation()}
              disabled={annotationSaving}
            >
              {annotationSaving ? "Saving" : "Save"}
            </button>
          </div>
        </div>
      {/if}

      <!-- Signature NeighborPanel -->
      <NeighborPanel {vaultName} data={neighbors} loading={loadingNeighbors} />
    </article>
  {/if}
</div>

<style>
  .note-page {
    width: var(--page-content-width);
    max-width: none;
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
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

  .editor-toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-3, 12px);
    margin-bottom: var(--space-2, 8px);
    font-family: var(--font-mono);
  }

  .editor-mode-toggle {
    display: flex;
    border: 1px solid var(--border);
  }

  .editor-mode-toggle button,
  .save-note-button {
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    background: transparent;
    border: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .editor-mode-toggle button + button {
    border-left: 1px solid var(--border);
  }

  .editor-mode-toggle button.active,
  .editor-mode-toggle button:hover,
  .save-note-button:not(:disabled):hover {
    color: var(--bg);
    background: var(--accent);
  }

  .editor-save-status {
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .editor-save-status.error {
    color: var(--signal-danger, #c0392b);
  }

  .save-note-button {
    margin-left: auto;
    border: 1px solid var(--border);
  }

  .save-note-button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
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

  .annotate-menu {
    position: fixed;
    z-index: 40;
    transform: translateX(-50%);
    border: 1px solid color-mix(in srgb, var(--accent) 72%, var(--border));
    border-radius: 999px;
    background: var(--accent);
    --annotate-action-text: #090b0d;
    box-shadow:
      0 12px 30px color-mix(in srgb, #000 35%, transparent),
      0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
  }

  .annotate-menu button {
    min-height: 36px;
    padding: 0 var(--space-4, 16px);
    border: 0;
    border-radius: 999px;
    background: var(--accent);
    color: var(--annotate-action-text);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .annotate-actions button {
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    border: 0;
    background: transparent;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .annotate-menu button:hover,
  .annotate-menu button:focus-visible {
    color: var(--annotate-action-text);
    background: var(--accent);
    outline: 2px solid color-mix(in srgb, var(--accent) 54%, transparent);
    outline-offset: 3px;
    box-shadow: inset 0 0 0 999px color-mix(in srgb, #fff 12%, transparent);
  }

  .annotate-actions button:hover,
  .annotate-actions button:focus-visible {
    color: var(--bg);
    background: var(--accent);
    outline: none;
  }

  .annotate-dialog {
    position: fixed;
    z-index: 50;
    right: var(--space-6, 32px);
    bottom: var(--space-6, 32px);
    width: min(420px, calc(100vw - 32px));
    border: 1px solid var(--border);
    padding: var(--space-4, 16px);
    background: var(--surface-raised, var(--bg));
    box-shadow: 0 18px 46px color-mix(in srgb, #000 42%, transparent);
  }

  .annotate-quote {
    margin: 0 0 var(--space-3, 12px);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
  }

  .annotate-field,
  .annotate-checkbox {
    display: grid;
    gap: var(--space-2, 8px);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .annotate-field textarea {
    min-height: 96px;
    resize: vertical;
    border: 1px solid var(--border);
    padding: var(--space-3, 12px);
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
    text-transform: none;
    letter-spacing: normal;
  }

  .annotate-field textarea:disabled,
  .annotate-checkbox input:disabled,
  .annotate-actions button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .annotate-error {
    margin: var(--space-2, 8px) 0 0;
    color: var(--signal-danger, #c0392b);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
  }

  .annotate-checkbox {
    grid-template-columns: auto 1fr;
    align-items: center;
    margin-top: var(--space-3, 12px);
  }

  .annotate-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2, 8px);
    margin-top: var(--space-4, 16px);
  }

  /* Prose styles for rendered markdown */
  .prose :global(h1) {
    font-family: var(--font-display);
    font-size: var(--type-h1-size, 28px);
    font-weight: var(--type-h1-weight, 600);
    line-height: var(--type-h1-lh, 1.2);
    color: var(--text);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(h2) {
    font-family: var(--font-display);
    font-size: var(--type-h2-size, 20px);
    font-weight: var(--type-h2-weight, 600);
    line-height: var(--type-h2-lh, 1.3);
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
    line-height: var(--type-body-lh, 1.7);
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

  :global([data-theme="light"]) .note-tag-chip,
  :global([data-theme="light"]) .prose :global(a.note-tag-chip) {
    --chip-bg: hsl(var(--tag-hue) 72% 92% / 0.88);
    --chip-border: hsl(var(--tag-hue) 48% 43% / 0.58);
    --chip-text: hsl(var(--tag-hue) 58% 26%);
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

  :global([data-theme="light"]) .note-meta-tag-chip:hover,
  :global([data-theme="light"]) .note-meta-tag-chip:focus-visible,
  :global([data-theme="light"]) .prose :global(a.note-tag-chip:hover),
  :global([data-theme="light"]) .prose :global(a.note-tag-chip:focus-visible) {
    color: hsl(var(--tag-hue) 62% 20%);
    border-color: hsl(var(--tag-hue) 52% 35% / 0.76);
    background: hsl(var(--tag-hue) 76% 87% / 0.95);
  }

  .prose :global(.note-relation-chip) {
    display: inline-flex;
    align-items: center;
    min-height: 1.45em;
    padding: 0 0.52em;
    border: 1px solid color-mix(in srgb, var(--accent) 48%, var(--border));
    border-radius: 2px;
    background: color-mix(
      in srgb,
      var(--accent) 14%,
      var(--surface-raised, var(--bg))
    );
    color: color-mix(in srgb, var(--accent) 72%, var(--text) 28%);
    font-family: var(--font-mono);
    font-size: 0.8em;
    font-weight: 750;
    line-height: 1;
    white-space: nowrap;
    vertical-align: 0.08em;
    box-shadow: inset 0 -1px 0 color-mix(in srgb, #000 18%, transparent);
  }

  :global([data-theme="light"]) .prose :global(.note-relation-chip) {
    border-color: color-mix(in srgb, var(--accent) 48%, var(--border));
    background: color-mix(in srgb, var(--accent) 11%, #fff);
    color: color-mix(in srgb, var(--accent) 70%, #111827 30%);
    box-shadow: inset 0 -1px 0 color-mix(in srgb, #000 8%, transparent);
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
    --callout-bg: color-mix(
      in srgb,
      var(--surface-raised, var(--bg)) 82%,
      #000 18%
    );
    --callout-text: color-mix(
      in srgb,
      var(--text-muted) 76%,
      var(--text-faint) 24%
    );
    border: 1px solid color-mix(in srgb, var(--border) 76%, transparent);
    border-left: 3px solid color-mix(in srgb, var(--accent) 38%, var(--border));
    border-radius: 6px;
    padding: var(--space-3, 12px) var(--space-4, 16px);
    margin: 0 0 var(--space-4, 16px);
    background: var(--callout-bg);
    color: var(--callout-text);
    font-style: normal;
  }

  :global([data-theme="light"]) .prose :global(blockquote) {
    --callout-bg: color-mix(
      in srgb,
      var(--surface-raised, var(--bg)) 88%,
      var(--accent) 12%
    );
    --callout-text: color-mix(in srgb, var(--text-muted) 76%, var(--text) 24%);
  }

  .prose :global(blockquote p),
  .prose :global(blockquote li) {
    color: inherit;
  }

  @media (prefers-color-scheme: light) {
    :global(:root:not([data-theme="dark"])) .note-tag-chip,
    :global(:root:not([data-theme="dark"])) .prose :global(a.note-tag-chip) {
      --chip-bg: hsl(var(--tag-hue) 72% 92% / 0.88);
      --chip-border: hsl(var(--tag-hue) 48% 43% / 0.58);
      --chip-text: hsl(var(--tag-hue) 58% 26%);
    }

    :global(:root:not([data-theme="dark"])) .note-meta-tag-chip:hover,
    :global(:root:not([data-theme="dark"])) .note-meta-tag-chip:focus-visible,
    :global(:root:not([data-theme="dark"]))
      .prose
      :global(a.note-tag-chip:hover),
    :global(:root:not([data-theme="dark"]))
      .prose
      :global(a.note-tag-chip:focus-visible) {
      color: hsl(var(--tag-hue) 62% 20%);
      border-color: hsl(var(--tag-hue) 52% 35% / 0.76);
      background: hsl(var(--tag-hue) 76% 87% / 0.95);
    }

    :global(:root:not([data-theme="dark"])) .prose :global(blockquote) {
      --callout-bg: color-mix(
        in srgb,
        var(--surface-raised, var(--bg)) 88%,
        var(--accent) 12%
      );
      --callout-text: color-mix(
        in srgb,
        var(--text-muted) 76%,
        var(--text) 24%
      );
    }

    :global(:root:not([data-theme="dark"]))
      .prose
      :global(.note-relation-chip) {
      border-color: color-mix(in srgb, var(--accent) 48%, var(--border));
      background: color-mix(in srgb, var(--accent) 11%, #fff);
      color: color-mix(in srgb, var(--accent) 70%, #111827 30%);
      box-shadow: inset 0 -1px 0 color-mix(in srgb, #000 8%, transparent);
    }
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
    line-height: var(--type-body-lh, 1.7);
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
