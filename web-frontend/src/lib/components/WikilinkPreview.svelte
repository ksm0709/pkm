<script lang="ts">
  /**
   * WikilinkPreview — slice 4 / F4-2.
   *
   * Hairline-bordered popover anchored at (x, y). Shown by the wikilink
   * widget on a 200ms hover delay; hidden on mouseleave.
   *
   * Wiring contract: the +layout.svelte mounts this component once per
   * vault route and exposes `window.__pkmPreview = { show(state), hide() }`.
   * The wikilink widget calls those methods. We keep the bus on `window`
   * (not a Svelte store) so the editor module — which lives outside the
   * component tree and may be shared across editor instances — can invoke
   * it without a Svelte import.
   *
   * Body is fetched lazily via GET /api/v1/vault/{vault}/notes/{id}.
   */
  import { onMount, onDestroy } from 'svelte';
  import { apiGet } from '$lib/api/client.js';

  interface Props {
    vault: string;
  }

  let { vault }: Props = $props();

  let visible = $state(false);
  let id = $state('');
  let title = $state('');
  let body = $state('');
  let x = $state(0);
  let y = $state(0);
  let loading = $state(false);

  /** @type {Map<string, string>} per-vault body cache */
  const bodyCache = new Map<string, string>();

  function bodyKey(v: string, i: string) {
    return `${v}::${i}`;
  }

  async function loadBody(theId: string) {
    const key = bodyKey(vault, theId);
    if (bodyCache.has(key)) {
      body = bodyCache.get(key) ?? '';
      return;
    }
    loading = true;
    try {
      const data = await apiGet<{ body?: string; title?: string }>(
        `/api/v1/vault/${encodeURIComponent(vault)}/notes/${encodeURIComponent(theId)}`
      );
      const snippet = (data.body ?? '').slice(0, 600);
      bodyCache.set(key, snippet);
      body = snippet;
      if (data.title && !title) title = data.title;
    } catch {
      body = '';
    } finally {
      loading = false;
    }
  }

  function handleShow(state: { id: string; title: string; x: number; y: number }) {
    id = state.id;
    title = state.title || state.id;
    body = '';
    // Clamp coords inside viewport (popover is 360 wide).
    const margin = 8;
    const popW = 360;
    const popH = 220;
    let nx = state.x + 12;
    let ny = state.y + 12;
    if (typeof window !== 'undefined') {
      if (nx + popW > window.innerWidth - margin) {
        nx = Math.max(margin, window.innerWidth - popW - margin);
      }
      if (ny + popH > window.innerHeight - margin) {
        ny = Math.max(margin, state.y - popH - 12);
      }
    }
    x = nx;
    y = ny;
    visible = true;
    void loadBody(state.id);
  }

  function handleHide() {
    visible = false;
  }

  onMount(() => {
    (window as any).__pkmPreview = {
      show: handleShow,
      hide: handleHide
    };
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      try {
        delete (window as any).__pkmPreview;
      } catch {
        (window as any).__pkmPreview = undefined;
      }
    }
  });
</script>

{#if visible}
  <div class="wl-preview" style="left: {x}px; top: {y}px;" role="tooltip">
    <div class="wl-title">{title}</div>
    <div class="wl-body" class:loading>
      {#if loading && !body}
        Loading…
      {:else if body}
        {body}
      {:else}
        <span class="wl-empty">(empty)</span>
      {/if}
    </div>
  </div>
{/if}

<style>
  .wl-preview {
    position: fixed;
    z-index: 1000;
    width: 360px;
    background: var(--bg-base);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 12px 14px;
    pointer-events: none;
  }

  .wl-title {
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 6px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .wl-body {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 6;
    line-clamp: 6;
    -webkit-box-orient: vertical;
    overflow: hidden;
    white-space: pre-wrap;
  }

  .wl-body.loading {
    font-style: italic;
    color: var(--text-faint);
  }

  .wl-empty {
    font-style: italic;
    color: var(--text-faint);
  }
</style>
