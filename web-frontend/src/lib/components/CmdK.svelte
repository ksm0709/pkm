<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { apiClient, apiGet } from "$lib/api/client.js";
  import { cmdkCoreCommandShortcuts } from "$lib/navigation/cmdk-command-shortcuts";
  import { appNavPages } from "$lib/navigation/app-nav";
  import { rememberVault } from "$lib/vault/remembered-vault";

  interface Props {
    vaultName: string;
    openToken?: number;
    searchOpenToken?: number;
  }

  let { vaultName, openToken = 0, searchOpenToken = 0 }: Props = $props();

  type Theme = "light" | "dark" | "auto";
  type PaletteMode = "commands" | "search" | "vaults";

  type CommandRow = {
    kind: "command";
    id: string;
    label: string;
    hint?: string;
    shortcut: string;
    run: () => void | Promise<void>;
  };

  type NoteRow = {
    kind: "note";
    id: string;
    label: string;
    hint?: string;
    note_id: string;
  };

  type Row = CommandRow | NoteRow;

  interface SearchResult {
    note_id: string;
    title: string;
    snippet?: string;
    score?: number;
  }

  interface SearchResponse {
    results: SearchResult[];
    query: string;
    count: number;
  }

  interface NoteListItem {
    note_id: string;
    title?: string;
    path?: string;
    description?: string | null;
    tags?: string[];
  }

  interface TagSearchNote {
    note_id: string;
    title: string;
    tags: string[];
    path: string;
  }

  interface TagSearchResponse {
    pattern: string;
    mode: string;
    results: TagSearchNote[];
    count: number;
  }

  interface VaultResponseItem {
    name?: string;
  }

  let open = $state(false);
  let query = $state("");
  let mode = $state<PaletteMode>("commands");
  let activeIndex = $state(0);
  let inputEl: HTMLInputElement | null = $state(null);

  let notes = $state<SearchResult[]>([]);
  let tagNotes = $state<TagSearchNote[]>([]);
  let vaultsList = $state<string[]>([]);
  let indexing = $state(false);
  let indexProgressMessage = $state("");
  let indexError = $state("");

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let lastQuery = "";
  const coreCommand = Object.fromEntries(
    cmdkCoreCommandShortcuts.map((command) => [command.id, command]),
  );

  function dispatchTheme(theme: Theme) {
    window.dispatchEvent(
      new CustomEvent("pkm:theme-change", { detail: { theme } }),
    );
  }

  function readStoredTheme(): Theme {
    try {
      const stored = localStorage.getItem("pkm.theme");
      if (stored === "light" || stored === "dark" || stored === "auto") {
        return stored;
      }
    } catch {
      // ignore
    }
    return "auto";
  }

  function nextTheme(curr: Theme): Theme {
    if (curr === "light") return "dark";
    if (curr === "dark") return "auto";
    return "light";
  }

  async function createDailySubnote() {
    const title =
      typeof window !== "undefined" ? window.prompt("Subnote title") : null;
    if (!title) return;

    const response = await apiClient(`/api/v1/vault/${vaultName}/daily/today`, {
      method: "POST",
      body: JSON.stringify({ type: "subnote", title, content: "" }),
    });
    if (!response.ok) throw new Error(`POST daily/today -> ${response.status}`);
    const payload = (await response.json()) as { note_id?: string };
    if (payload.note_id) {
      await goto(`/${vaultName}/notes/${payload.note_id}`);
    }
  }

  async function indexVault() {
    indexing = true;
    indexError = "";
    indexProgressMessage = "Building search index and graph…";
    try {
      const response = await apiClient(
        `/api/v1/vault/${encodeURIComponent(vaultName)}/index`,
        { method: "POST" },
      );
      if (!response.ok) throw new Error(`POST index -> ${response.status}`);
      const payload = (await response.json().catch(() => ({}))) as {
        count?: number;
      };
      indexProgressMessage =
        typeof payload.count === "number"
          ? `Indexed ${payload.count} notes. Opening graph…`
          : "Index complete. Opening graph…";
      indexing = false;
      close({ force: true });
      await goto(`/${vaultName}/graph`);
    } catch (error) {
      indexError =
        error instanceof Error ? error.message : "Failed to index vault.";
      throw error;
    } finally {
      indexing = false;
    }
  }

  async function loadVaults() {
    if (vaultsList.length > 0) return;
    try {
      const v =
        await apiGet<Array<string | VaultResponseItem>>("/api/v1/vaults");
      vaultsList = Array.isArray(v)
        ? v
            .map((item) => (typeof item === "string" ? item : item.name))
            .filter((name): name is string => !!name)
        : [];
    } catch {
      vaultsList = [];
    }
  }

  function staticCommands(): CommandRow[] {
    const navCommands: CommandRow[] = appNavPages.map((item) => ({
      kind: "command",
      id: `nav:${item.id}`,
      label: item.commandLabel,
      hint: item.commandHint,
      shortcut: item.commandShortcut,
      run: () => goto(item.href(vaultName)),
    }));

    const list: CommandRow[] = [
      {
        kind: "command",
        id: "cmd:jump",
        label: coreCommand["cmd:jump"].label,
        hint: coreCommand["cmd:jump"].hint,
        shortcut: coreCommand["cmd:jump"].shortcut,
        run: () => {
          open = true;
          mode = "search";
          query = "";
          activeIndex = 0;
          notes = [];
          tagNotes = [];
          lastQuery = "";
          inputEl?.focus();
        },
      },
      {
        kind: "command",
        id: "cmd:daily",
        label: coreCommand["cmd:daily"].label,
        hint: coreCommand["cmd:daily"].hint,
        shortcut: coreCommand["cmd:daily"].shortcut,
        run: () =>
          goto(`/${vaultName}/notes/${new Date().toISOString().slice(0, 10)}`),
      },
      {
        kind: "command",
        id: "cmd:daily-subnote",
        label: coreCommand["cmd:daily-subnote"].label,
        hint: coreCommand["cmd:daily-subnote"].hint,
        shortcut: coreCommand["cmd:daily-subnote"].shortcut,
        run: createDailySubnote,
      },
      {
        kind: "command",
        id: "cmd:index-vault",
        label: coreCommand["cmd:index-vault"].label,
        hint: coreCommand["cmd:index-vault"].hint,
        shortcut: coreCommand["cmd:index-vault"].shortcut,
        run: indexVault,
      },
      {
        kind: "command",
        id: "cmd:ask",
        label: coreCommand["cmd:ask"].label,
        hint: coreCommand["cmd:ask"].hint,
        shortcut: coreCommand["cmd:ask"].shortcut,
        run: () => {
          const q = query.trim();
          const target = q
            ? `/${vaultName}/ask?q=${encodeURIComponent(q)}`
            : `/${vaultName}/ask`;
          return goto(target);
        },
      },
      ...navCommands,
      {
        kind: "command",
        id: "cmd:switch",
        label: coreCommand["cmd:switch"].label,
        hint: coreCommand["cmd:switch"].hint,
        shortcut: coreCommand["cmd:switch"].shortcut,
        run: async () => {
          open = true;
          await loadVaults();
          mode = "vaults";
          query = "";
          activeIndex = 0;
          inputEl?.focus();
        },
      },
      {
        kind: "command",
        id: "cmd:theme",
        label: coreCommand["cmd:theme"].label,
        hint: coreCommand["cmd:theme"].hint,
        shortcut: coreCommand["cmd:theme"].shortcut,
        run: () => {
          const t = nextTheme(readStoredTheme());
          dispatchTheme(t);
        },
      },
    ];
    return list;
  }

  function vaultSwitchRows(): CommandRow[] {
    return vaultsList
      .filter((v) => v.toLowerCase().includes(query.trim().toLowerCase()))
      .map((v) => ({
        kind: "command" as const,
        id: `vault:${v}`,
        label: v,
        hint: v === vaultName ? "current vault" : "vault",
        shortcut: "",
        run: () => {
          if (v === vaultName) {
            inputEl?.focus();
            return;
          }
          rememberVault(v);
          return goto(`/${v}/logger`);
        },
      }));
  }

  function commandsForQuery(q: string): CommandRow[] {
    const all = staticCommands();
    if (!q) return all;
    const lower = q.toLowerCase();
    return all.filter(
      (c) =>
        c.id === "cmd:ask" ||
        c.label.toLowerCase().includes(lower) ||
        (c.hint?.toLowerCase().includes(lower) ?? false),
    );
  }

  let rows = $derived<Row[]>(buildRows(query, notes, tagNotes, mode));

  function buildRows(
    q: string,
    notesList: SearchResult[],
    tagNotesList: TagSearchNote[],
    currentMode: PaletteMode,
  ): Row[] {
    const trimmed = q.trim();
    if (currentMode === "vaults") {
      return vaultSwitchRows();
    }

    if (currentMode === "commands") {
      if (!trimmed) return staticCommands();
      return commandsForQuery(trimmed);
    }

    if (!trimmed) {
      return [];
    }

    if (currentMode === "search" && trimmed.startsWith("#")) {
      return tagNotesList.map((n) => ({
        kind: "note" as const,
        id: `tagnote:${n.note_id}`,
        label: n.title || n.note_id,
        hint: n.tags?.length ? n.tags.map((t) => `#${t}`).join(" ") : undefined,
        note_id: n.note_id,
      }));
    }

    if (currentMode === "search") {
      return notesList.map((n) => ({
        kind: "note" as const,
        id: `note:${n.note_id}`,
        label: n.title || n.note_id,
        hint: n.snippet,
        note_id: n.note_id,
      }));
    }

    return [];
  }

  async function runSearch(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 2) {
      notes = [];
      tagNotes = [];
      return;
    }

    if (trimmed.startsWith("#")) {
      const pattern = trimmed.slice(1);
      if (!pattern) {
        notes = [];
        tagNotes = [];
        return;
      }
      try {
        const data = await apiGet<TagSearchResponse>(
          `/api/v1/vault/${vaultName}/tags/search?pattern=${encodeURIComponent(pattern)}`,
        );
        tagNotes = data.results ?? [];
      } catch {
        tagNotes = [];
      }
      notes = [];
      return;
    }

    try {
      const data = await apiGet<SearchResponse>(
        `/api/v1/vault/${vaultName}/search?q=${encodeURIComponent(trimmed)}`,
      );
      notes = data.results ?? [];
    } catch {
      notes = await searchNotesListFallback(trimmed);
    }
    tagNotes = [];
  }

  async function searchNotesListFallback(q: string): Promise<SearchResult[]> {
    const lower = q.toLowerCase();
    try {
      const list = await apiGet<NoteListItem[]>(
        `/api/v1/vault/${vaultName}/notes`,
      );
      return list
        .filter((note) =>
          [
            note.note_id,
            note.title ?? "",
            note.path ?? "",
            note.description ?? "",
            ...(note.tags ?? []),
          ].some((value) => value.toLowerCase().includes(lower)),
        )
        .slice(0, 10)
        .map((note) => ({
          note_id: note.note_id,
          title: note.title || note.note_id,
          snippet: note.description || note.path || "note",
          score: 0,
        }));
    } catch {
      return [];
    }
  }

  function scheduleSearch(q: string) {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      if (q === lastQuery) return;
      lastQuery = q;
      void runSearch(q);
    }, 100);
  }

  function onInput(e: Event) {
    const target = e.target as HTMLInputElement;
    query = target.value;
    activeIndex = 0;
    if (mode !== "search") return;
    scheduleSearch(query);
  }

  function openPalette(initialMode: "commands" | "search" = "commands") {
    open = true;
    query = "";
    mode = initialMode;
    activeIndex = 0;
    notes = [];
    tagNotes = [];
    lastQuery = "";
    // Pre-fetch vault list so vault switch is instant
    void loadVaults();
    requestAnimationFrame(() => inputEl?.focus());
  }

  function close(options: { force?: boolean } = {}) {
    if (indexing && !options.force) return;
    open = false;
    mode = "commands";
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
  }

  async function execute(row: Row) {
    if (row.kind === "command") {
      try {
        await row.run();
      } catch {
        return;
      }
      // Most commands navigate; some (theme) keep palette open. Close by default
      // unless the command opens an in-palette chooser or selects the current vault.
      if (
        row.id !== "cmd:jump" &&
        row.id !== "cmd:switch" &&
        row.id !== `vault:${vaultName}`
      ) {
        close({ force: row.id === "cmd:index-vault" });
      }
      return;
    }
    if (row.kind === "note") {
      await goto(`/${vaultName}/notes/${row.note_id}`);
      close();
    }
  }

  function executeCommandById(id: string) {
    const row = staticCommands().find((command) => command.id === id);
    if (row) void execute(row);
  }

  function onKeydown(event: KeyboardEvent) {
    function consume() {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    }

    function eventStartedInEditor() {
      const target = event.target;
      if (!(target instanceof Element)) return false;
      return Boolean(
        target.closest(
          'input, textarea, select, [contenteditable="true"], .cm-editor',
        ),
      );
    }

    // Global ⌘K toggle
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      if (!open && eventStartedInEditor()) return;
      consume();
      if (open) close();
      else openPalette();
      return;
    }

    if (
      (event.metaKey || event.ctrlKey) &&
      (event.key === "/" || event.code === "Slash")
    ) {
      if (!open && eventStartedInEditor()) return;
      consume();
      if (open && mode === "search") close();
      else openPalette("search");
      return;
    }

    if (!open) return;

    if (indexing) {
      consume();
      return;
    }

    if (event.key === "Escape") {
      consume();
      close();
      return;
    }

    if (event.key === "ArrowDown") {
      consume();
      if (rows.length === 0) return;
      activeIndex = (activeIndex + 1) % rows.length;
      return;
    }

    if (event.key === "ArrowUp") {
      consume();
      if (rows.length === 0) return;
      activeIndex = (activeIndex - 1 + rows.length) % rows.length;
      return;
    }

    if (event.key === "Enter") {
      consume();
      const row = rows[activeIndex];
      if (row) void execute(row);
    }
  }

  function onBackdropClick(event: MouseEvent) {
    if (indexing) return;
    if (event.target === event.currentTarget) close();
  }

  $effect(() => {
    if (openToken > 0) openPalette();
  });

  $effect(() => {
    if (searchOpenToken > 0) openPalette("search");
  });

  onMount(() => {
    const handler = () => openPalette();
    const searchHandler = () => openPalette("search");
    const shortcutHandler = (event: Event & { detail?: { id?: string } }) => {
      const id = event.detail?.id;
      if (id) executeCommandById(id);
    };
    window.addEventListener("pkm:open-command-palette", handler);
    window.addEventListener("pkm:open-note-search", searchHandler);
    window.addEventListener("pkm:run-command-shortcut", shortcutHandler);
    return () => {
      window.removeEventListener("pkm:open-command-palette", handler);
      window.removeEventListener("pkm:open-note-search", searchHandler);
      window.removeEventListener("pkm:run-command-shortcut", shortcutHandler);
    };
  });
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="cmdk-backdrop" onclick={onBackdropClick}>
    <div
      class="cmdk-modal cmdk command-palette"
      data-cmdk
      role="dialog"
      aria-label="Command palette"
      aria-modal="true"
    >
      <div class="console-label">
        {mode === "vaults"
          ? "VAULT SWITCHER"
          : mode === "search"
            ? "NOTE SEARCH"
            : "COMMAND CONSOLE"}
      </div>
      <input
        bind:this={inputEl}
        class="cmdk-input"
        type="text"
        placeholder={mode === "vaults"
          ? "Choose vault…"
          : mode === "search"
            ? "Search notes or #tag…"
            : "Run command…"}
        value={query}
        oninput={onInput}
        autocomplete="off"
        spellcheck="false"
      />
      <ul class="cmdk-list" role="listbox">
        {#each rows as row, i (row.id)}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <li
            class="cmdk-row"
            class:active={i === activeIndex}
            data-kind={row.kind}
            data-note-id={row.kind === "note" ? row.note_id : undefined}
            role="option"
            aria-selected={i === activeIndex}
            onmousemove={() => (activeIndex = i)}
            onclick={() => execute(row)}
          >
            <span class="row-glyph" aria-hidden="true">
              {i === activeIndex ? "→" : ""}
            </span>
            <span class="row-label">{row.label}</span>
            {#if row.hint}
              <span class="row-hint">{row.hint}</span>
            {/if}
          </li>
        {/each}
        {#if rows.length === 0}
          <li class="cmdk-empty">No matches.</li>
        {/if}
      </ul>
      {#if indexError}
        <p class="cmdk-status error" role="status">{indexError}</p>
      {/if}
    </div>
  </div>
{/if}

{#if indexing}
  <div
    class="indexing-blocker"
    role="alertdialog"
    aria-label="Indexing vault"
    aria-modal="true"
  >
    <div class="indexing-popup">
      <span class="indexing-label">Indexing vault</span>
      <progress class="indexing-progress" aria-label="Indexing progress"
      ></progress>
      <p>{indexProgressMessage}</p>
    </div>
  </div>
{/if}

<style>
  .cmdk-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(9, 11, 13, 0.72);
    z-index: 1000;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 12vh;
  }

  .cmdk-modal {
    width: min(var(--palette-width, 560px), var(--modal-available-width));
    max-height: var(--palette-max-height, 60vh);
    background-color: var(--surface, var(--bg));
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-top-color: var(--accent);
    animation: cmdk-in var(--dur-fast, 120ms) var(--ease-out);
  }

  .console-label {
    min-height: 28px;
    display: flex;
    align-items: center;
    padding: 0 var(--space-4, 16px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
    border-bottom: 1px solid var(--border);
  }

  .cmdk-input {
    width: 100%;
    box-sizing: border-box;
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    color: var(--text);
    background-color: var(--surface-raised, var(--bg));
    border: none;
    border-bottom: 1px solid var(--accent);
    border-radius: 0;
    padding: var(--space-3, 12px) var(--space-4, 16px) var(--space-3, 12px)
      var(--space-5, 24px);
    outline: none;
    caret-color: var(--accent);
  }

  .cmdk-input::placeholder {
    color: var(--text-faint);
  }

  .cmdk-list {
    list-style: none;
    margin: 0;
    padding: var(--space-1, 4px) 0;
    overflow-y: auto;
    flex: 1;
  }

  .cmdk-row {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    min-height: 38px;
    padding: 0 var(--space-4, 16px) 0 var(--space-5, 24px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: var(--type-chrome-lh, 1.2);
    color: var(--text);
    cursor: pointer;
    border-left: 2px solid transparent;
    transition:
      background-color var(--dur-fast, 120ms) var(--ease-out),
      border-color var(--dur-fast, 120ms) var(--ease-out),
      color var(--dur-fast, 120ms) var(--ease-out);
  }

  .cmdk-row.active {
    background-color: var(--accent-bg);
    border-left-color: var(--accent);
  }

  .row-glyph {
    width: 12px;
    color: var(--accent);
    flex-shrink: 0;
  }

  .row-label {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .row-hint {
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    flex-shrink: 0;
    margin-left: var(--space-3, 12px);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 240px;
  }

  .cmdk-empty {
    padding: var(--space-3, 12px) var(--space-4, 16px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-faint);
  }

  .cmdk-status {
    margin: 0;
    padding: var(--space-3, 12px) var(--space-4, 16px);
    border-top: 1px solid var(--border);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
  }

  .cmdk-status.error {
    color: var(--signal-danger, #ff6b5f);
  }

  .indexing-blocker {
    position: fixed;
    inset: 0;
    z-index: 1200;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4, 16px);
    background: rgba(9, 11, 13, 0.78);
  }

  .indexing-popup {
    width: min(420px, var(--modal-available-width, calc(100vw - 32px)));
    padding: var(--space-5, 24px);
    border: 1px solid var(--border);
    border-top: 2px solid var(--accent);
    background: var(--surface, var(--bg));
    color: var(--text);
    font-family: var(--font-mono);
  }

  .indexing-label {
    display: block;
    margin-bottom: var(--space-3, 12px);
    color: var(--accent);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .indexing-progress {
    width: 100%;
    height: 8px;
    accent-color: var(--accent);
  }

  .indexing-popup p {
    margin: var(--space-3, 12px) 0 0;
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  @keyframes cmdk-in {
    from {
      opacity: 0;
      transform: translateY(-4px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .cmdk-modal {
      animation: none;
    }

    .cmdk-row {
      transition: none;
    }
  }
</style>
