<script lang="ts">
  import {
    renderMarkdownHtml,
    sanitizeRenderedHtml,
  } from "$lib/notes/rendered-markdown.js";

  interface Props {
    markdown: string;
    vault: string;
    compact?: boolean;
    transformMarkdown?: (markdown: string) => string;
  }

  let { markdown, vault, compact = false, transformMarkdown }: Props = $props();
  let html = $state("");
  let root: HTMLDivElement | undefined = $state();
  let mermaidRenderRun = 0;

  $effect(() => {
    const source = markdown ?? "";
    const vaultName = vault ?? "";
    let cancelled = false;
    html = "";

    if (!source.trim()) return;

    void renderMarkdownHtml(source, vaultName, undefined, { transformMarkdown })
      .then((rendered) => {
        if (!cancelled) html = rendered;
      })
      .catch(() => {
        if (!cancelled) html = escapeHtml(source).replace(/\n/g, "<br>");
      });

    return () => {
      cancelled = true;
    };
  });

  $effect(() => {
    const container = root;
    const renderedHtml = html;
    if (!container || !renderedHtml) return;

    const runId = ++mermaidRenderRun;
    void renderMermaidBlocks(container, runId);
  });

  async function renderMermaidBlocks(container: HTMLElement, runId: number) {
    const blocks = Array.from(
      container.querySelectorAll<HTMLElement>("pre.mermaid"),
    ).filter((block) => block.dataset.mermaidRendered !== "true");
    if (blocks.length === 0) return;

    try {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({ securityLevel: "strict", startOnLoad: false });

      await Promise.all(
        blocks.map(async (block, index) => {
          const source = block.textContent ?? "";
          const id = `pkm-mermaid-${runId}-${index}`;
          try {
            const { svg } = await mermaid.render(id, source);
            if (runId !== mermaidRenderRun) return;

            const rendered = document.createElement("div");
            rendered.className = "mermaid-rendered";
            rendered.innerHTML = sanitizeRenderedHtml(svg);
            block.after(rendered);
            block.dataset.mermaidRendered = "true";
            block.hidden = true;
          } catch (error) {
            if (runId !== mermaidRenderRun) return;
            block.classList.add("mermaid-error");
            block.title =
              error instanceof Error ? error.message : "Mermaid render failed";
          }
        }),
      );
    } catch {
      for (const block of blocks) {
        block.classList.add("mermaid-error");
        block.title = "Mermaid renderer unavailable";
      }
    }
  }

  function escapeHtml(value: string) {
    return value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
</script>

<div bind:this={root} class="markdown-prose" class:compact>
  <!-- eslint-disable-next-line svelte/no-at-html-tags -->
  {@html html}
</div>

<style>
  .markdown-prose {
    min-width: 0;
    color: var(--text);
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .markdown-prose :global(*) {
    max-width: 100%;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .markdown-prose :global(h1),
  .markdown-prose :global(h2),
  .markdown-prose :global(h3) {
    font-family: var(--font-display);
    color: var(--text);
    font-weight: 600;
  }

  .markdown-prose :global(h1) {
    margin: 0 0 var(--space-4, 16px);
    font-size: var(--type-h1-size, 28px);
    line-height: var(--type-h1-lh, 1.2);
  }

  .markdown-prose :global(h2) {
    margin: var(--space-6, 32px) 0 var(--space-3, 12px);
    font-size: var(--type-h2-size, 20px);
    line-height: var(--type-h2-lh, 1.3);
  }

  .markdown-prose :global(h3) {
    margin: var(--space-5, 24px) 0 var(--space-2, 8px);
    font-size: var(--type-h3-size, 17px);
    line-height: var(--type-h3-lh, 1.35);
  }

  .markdown-prose :global(p),
  .markdown-prose :global(li) {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
    color: var(--text);
  }

  .markdown-prose :global(p),
  .markdown-prose :global(ul),
  .markdown-prose :global(ol),
  .markdown-prose :global(pre),
  .markdown-prose :global(blockquote) {
    margin: 0 0 var(--space-4, 16px);
  }

  .markdown-prose :global(ul),
  .markdown-prose :global(ol) {
    padding-left: 1.4rem;
  }

  .markdown-prose :global(a) {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .markdown-prose :global(code) {
    padding: 1px 4px;
    background: var(--surface-raised, var(--bg));
    font-family: var(--font-mono);
    font-size: 0.9em;
  }

  .markdown-prose :global(pre) {
    overflow-x: hidden;
    padding: var(--space-4, 16px);
    background: var(--surface-raised, var(--bg));
    white-space: pre-wrap;
  }

  .markdown-prose :global(pre code) {
    padding: 0;
    background: none;
  }

  .markdown-prose :global(blockquote) {
    border: 1px solid color-mix(in srgb, var(--border) 76%, transparent);
    border-left: 3px solid color-mix(in srgb, var(--accent) 38%, var(--border));
    border-radius: 6px;
    padding: var(--space-3, 12px) var(--space-4, 16px);
    background: color-mix(
      in srgb,
      var(--surface-raised, var(--bg)) 82%,
      #000 18%
    );
    color: var(--text-muted);
  }

  .markdown-prose :global(blockquote p),
  .markdown-prose :global(blockquote li) {
    color: inherit;
  }

  .markdown-prose :global(a.note-tag-chip) {
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

  .markdown-prose :global(.note-relation-chip) {
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

  .markdown-prose :global(.note-bracket-highlight) {
    padding: 0 0.15em;
    border-bottom: 1px solid color-mix(in srgb, var(--accent) 38%, transparent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: color-mix(in srgb, var(--accent) 76%, var(--text) 24%);
  }

  .markdown-prose.compact :global(h1),
  .markdown-prose.compact :global(h2),
  .markdown-prose.compact :global(h3) {
    margin-top: var(--space-3, 12px);
    margin-bottom: var(--space-2, 8px);
  }

  .markdown-prose.compact :global(h1) {
    font-size: 20px;
  }

  .markdown-prose.compact :global(h2) {
    font-size: 17px;
  }

  .markdown-prose.compact :global(h3) {
    font-size: 15px;
  }

  .markdown-prose.compact :global(p),
  .markdown-prose.compact :global(li) {
    color: var(--text-muted);
    font-size: 13px;
    line-height: 1.6;
  }

  .markdown-prose.compact :global(p),
  .markdown-prose.compact :global(ul),
  .markdown-prose.compact :global(ol),
  .markdown-prose.compact :global(pre),
  .markdown-prose.compact :global(blockquote) {
    margin-bottom: var(--space-3, 12px);
  }

  :global([data-theme="light"]) .markdown-prose :global(a.note-tag-chip) {
    --chip-bg: hsl(var(--tag-hue) 72% 92% / 0.88);
    --chip-border: hsl(var(--tag-hue) 48% 43% / 0.58);
    --chip-text: hsl(var(--tag-hue) 58% 26%);
  }

  :global([data-theme="light"]) .markdown-prose :global(.note-relation-chip) {
    border-color: color-mix(in srgb, var(--accent) 48%, var(--border));
    background: color-mix(in srgb, var(--accent) 11%, #fff);
    color: color-mix(in srgb, var(--accent) 70%, #111827 30%);
    box-shadow: inset 0 -1px 0 color-mix(in srgb, #000 8%, transparent);
  }
</style>
