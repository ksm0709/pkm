<script lang="ts">
  import { page } from "$app/stores";
  import { apiClient } from "$lib/api/client.js";
  import MarkdownRenderer from "$lib/components/MarkdownRenderer.svelte";
  import {
    apiDataHref,
    dataFileKind,
    rawDownloadHref,
    viewerDataHref,
    type DataFileKind,
  } from "$lib/data-viewer/paths";
  import { sanitizeRenderedHtml } from "$lib/notes/rendered-markdown.js";

  let loading = $state(false);
  let error = $state("");
  let markdown = $state("");
  let sanitizedHtml = $state("");
  let loadToken = 0;

  let vaultName = $derived($page.params.vault ?? "");
  let dataPath = $derived($page.params.path ?? "");
  let kind = $derived<DataFileKind>(dataFileKind(dataPath));
  let apiHref = $derived(apiDataHref(vaultName, dataPath));
  let downloadHref = $derived(rawDownloadHref(vaultName, dataPath));
  let canonicalViewerHref = $derived(viewerDataHref(vaultName, dataPath));
  let fileName = $derived(dataPath.split("/").pop() || dataPath || "Data file");

  $effect(() => {
    const token = ++loadToken;
    const currentKind = kind;
    const currentApiHref = apiHref;
    markdown = "";
    sanitizedHtml = "";
    error = "";

    if (!vaultName || !dataPath || currentKind === "unsupported") {
      loading = false;
      return;
    }

    loading = true;
    void apiClient(currentApiHref, {
      method: "GET",
      headers: { Accept: "text/plain, text/html, text/markdown, */*" },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`GET data file → ${response.status}`);
        }
        const text = await response.text();
        if (token !== loadToken) return;
        if (currentKind === "markdown") {
          markdown = text;
        } else {
          sanitizedHtml = sanitizeRenderedHtml(text);
        }
      })
      .catch((err) => {
        if (token !== loadToken) return;
        error = err instanceof Error ? err.message : "Failed to load data file";
      })
      .finally(() => {
        if (token === loadToken) loading = false;
      });
  });
</script>

<svelte:head>
  <title>{fileName} · PKM data viewer</title>
</svelte:head>

<main class="data-viewer">
  <header class="viewer-header">
    <p class="eyebrow">Data preview</p>
    <h1>{fileName}</h1>
    <p class="path" title={dataPath}>{dataPath}</p>
    <div class="actions">
      <a data-testid="raw-download" class="button" href={downloadHref}>Download raw</a>
      <a class="button secondary" href={canonicalViewerHref}>Viewer link</a>
    </div>
  </header>

  {#if kind === "unsupported"}
    <section class="notice" data-testid="unsupported-preview">
      <h2>Preview not supported</h2>
      <p>This data file type is available as a raw download only.</p>
    </section>
  {:else if loading}
    <section class="notice">Loading preview…</section>
  {:else if error}
    <section class="notice error" role="alert">{error}</section>
  {:else if kind === "markdown"}
    <article class="preview markdown-preview">
      <MarkdownRenderer markdown={markdown} vault={vaultName} />
    </article>
  {:else}
    <article class="preview html-preview markdown-prose">
      <!-- eslint-disable-next-line svelte/no-at-html-tags -->
      {@html sanitizedHtml}
    </article>
  {/if}
</main>

<style>
  .data-viewer {
    min-height: 100vh;
    padding: var(--space-6, 32px);
    color: var(--text);
    background: var(--bg);
  }

  .viewer-header {
    max-width: 1100px;
    margin: 0 auto var(--space-6, 32px);
    padding-bottom: var(--space-4, 16px);
    border-bottom: 1px solid var(--border);
  }

  .eyebrow {
    margin: 0 0 var(--space-2, 8px);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  h1 {
    margin: 0 0 var(--space-2, 8px);
    font-family: var(--font-display);
    font-size: var(--type-h1-size, 28px);
  }

  .path {
    margin: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    overflow-wrap: anywhere;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    margin-top: var(--space-4, 16px);
  }

  .button {
    display: inline-flex;
    align-items: center;
    min-height: 34px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--accent);
    border-radius: 999px;
    color: var(--bg);
    background: var(--accent);
    font-family: var(--font-mono);
    font-size: 13px;
    text-decoration: none;
  }

  .button.secondary {
    color: var(--accent);
    background: transparent;
  }

  .notice,
  .preview {
    max-width: 1100px;
    margin: 0 auto;
    padding: var(--space-5, 24px);
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface, transparent);
  }

  .notice.error {
    border-color: color-mix(in srgb, #ff5a5f 70%, var(--border));
    color: #ffb4b4;
  }

  .html-preview {
    overflow-wrap: anywhere;
  }

  .html-preview :global(*) {
    max-width: 100%;
  }

  .html-preview :global(script),
  .html-preview :global(style),
  .html-preview :global(iframe),
  .html-preview :global(object),
  .html-preview :global(embed) {
    display: none;
  }
</style>
