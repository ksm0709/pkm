<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { apiClient } from "$lib/api/client.js";
  import {
    loadDataAnnotations,
    saveDataAnnotations,
    type PdfAnnotation,
    type PdfAnnotationDocument,
  } from "./annotations";
  import {
    createAreaAnnotationFromDrag,
    createTextAnnotationFromSelection,
    overlayStyleForRect,
  } from "./annotation-geometry";
  import { apiDataHref } from "$lib/data-viewer/paths";
  import {
    renderPdfIntoContainer,
    type PdfRenderCleanup,
  } from "./pdf-renderer";

  let { vault, path }: { vault: string; path: string } = $props();

  let container: HTMLDivElement;
  let loading = $state(false);
  let saving = $state(false);
  let error = $state("");
  let areaMode = $state(false);
  let annotationDoc = $state<PdfAnnotationDocument | null>(null);
  let cleanup: PdfRenderCleanup | null = null;
  let cancelled = false;
  let areaStart: {
    page: HTMLElement;
    clientX: number;
    clientY: number;
  } | null = null;

  function nowIso() {
    return new Date().toISOString();
  }

  function annotationId(prefix: string) {
    const randomId = globalThis.crypto?.randomUUID?.();
    return randomId
      ? `${prefix}-${randomId}`
      : `${prefix}-${Date.now().toString(36)}`;
  }

  function emptyAnnotationDoc(): PdfAnnotationDocument {
    return { version: 1, source_path: path, annotations: [] };
  }

  function paintAnnotationOverlays() {
    if (!container) return;
    for (const overlay of container.querySelectorAll(
      ".pdf-annotation-overlay",
    )) {
      overlay.remove();
    }
    for (const annotation of annotationDoc?.annotations ?? []) {
      for (const rect of annotation.rects) {
        const page = container.querySelector<HTMLElement>(
          `.pdf-page[data-page-number="${rect.page}"]`,
        );
        if (!page) continue;
        const overlay = document.createElement("div");
        overlay.className = `pdf-annotation-overlay ${annotation.type}`;
        overlay.dataset.annotationId = annotation.id;
        overlay.dataset.annotationType = annotation.type;
        overlay.setAttribute("style", overlayStyleForRect(rect));
        overlay.title =
          annotation.quote || annotation.comment || annotation.type;
        page.appendChild(overlay);
      }
    }
  }

  async function persistAnnotation(annotation: PdfAnnotation) {
    const current = annotationDoc ?? emptyAnnotationDoc();
    const next: PdfAnnotationDocument = {
      version: 1,
      source_path: path,
      annotations: [...current.annotations, annotation],
    };
    saving = true;
    error = "";
    try {
      annotationDoc = await saveDataAnnotations(vault, path, next);
      paintAnnotationOverlays();
    } catch (err) {
      error =
        err instanceof Error ? err.message : "Failed to save PDF annotation";
    } finally {
      saving = false;
    }
  }

  async function loadPdf() {
    if (!vault || !path || !container) return;
    loading = true;
    error = "";
    annotationDoc = null;
    cleanup?.();
    cleanup = null;

    try {
      const response = await apiClient(apiDataHref(vault, path), {
        method: "GET",
        headers: { Accept: "application/pdf, application/octet-stream, */*" },
      });
      if (!response.ok) throw new Error(`GET PDF → ${response.status}`);
      const buffer = await response.arrayBuffer();
      if (cancelled) return;
      cleanup = await renderPdfIntoContainer(container, buffer);
      if (cancelled) return;
      annotationDoc = await loadDataAnnotations(vault, path);
      paintAnnotationOverlays();
    } catch (err) {
      if (cancelled) return;
      error = err instanceof Error ? err.message : "Failed to load PDF";
    } finally {
      if (!cancelled) loading = false;
    }
  }

  function pageFromEventTarget(target: EventTarget | null) {
    return target instanceof Element
      ? target.closest<HTMLElement>(".pdf-page")
      : null;
  }

  function handlePointerDown(event: PointerEvent) {
    if (!areaMode) return;
    const page = pageFromEventTarget(event.target);
    if (!page) return;
    areaStart = { page, clientX: event.clientX, clientY: event.clientY };
    event.preventDefault();
  }

  function handlePointerUp(event: PointerEvent) {
    if (!areaMode || !areaStart) return;
    const annotation = createAreaAnnotationFromDrag({
      page: areaStart.page,
      start: areaStart,
      end: event,
      now: nowIso(),
      id: annotationId("area"),
    });
    areaStart = null;
    if (!annotation) return;
    void persistAnnotation(annotation);
  }

  function createTextAnnotation() {
    const annotation = createTextAnnotationFromSelection({
      root: container,
      selection: window.getSelection(),
      now: nowIso(),
      id: annotationId("text"),
    });
    if (!annotation) {
      error = "Select text on a single PDF page before annotating.";
      return;
    }
    void persistAnnotation(annotation);
  }

  onMount(() => {
    void loadPdf();
  });

  onDestroy(() => {
    cancelled = true;
    cleanup?.();
    cleanup = null;
  });
</script>

<section class="pdf-preview" data-testid="pdf-preview" aria-label="PDF preview">
  <div class="annotation-toolbar" aria-label="PDF annotation tools">
    <button
      type="button"
      data-testid="area-annotation-mode"
      class:active={areaMode}
      onclick={() => (areaMode = !areaMode)}
    >
      Area annotate
    </button>
    <button
      type="button"
      data-testid="text-annotation"
      onclick={createTextAnnotation}
    >
      Annotate selected text
    </button>
    {#if saving}
      <span class="saving">Saving…</span>
    {/if}
  </div>
  {#if loading}
    <p class="notice">Loading PDF…</p>
  {/if}
  {#if error}
    <p class="notice error" role="alert">{error}</p>
  {/if}
  <div
    bind:this={container}
    class="pdf-pages"
    class:area-mode={areaMode}
    data-testid="pdf-pages"
    role="application"
    aria-label="PDF pages and annotation surface"
    onpointerdown={handlePointerDown}
    onpointerup={handlePointerUp}
  ></div>
</section>

<style>
  .pdf-preview {
    box-sizing: border-box;
    width: 100%;
  }

  .annotation-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2, 8px);
    margin: 0 0 var(--space-3, 12px);
  }

  .annotation-toolbar button {
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text);
    background: var(--surface, transparent);
    cursor: pointer;
  }

  .annotation-toolbar button.active {
    border-color: var(--accent);
    color: var(--bg);
    background: var(--accent);
  }

  .saving,
  .notice {
    margin: 0 0 var(--space-3, 12px);
    color: var(--text-muted);
  }

  .saving {
    margin: 0;
    font-size: 13px;
  }

  .notice.error {
    color: #ffb4b4;
  }

  .pdf-pages {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-5, 24px);
    overflow: auto;
  }

  .pdf-pages.area-mode {
    cursor: crosshair;
  }

  .pdf-pages :global(.pdf-page) {
    flex: 0 0 auto;
    border: 1px solid var(--border);
    background: white;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.22);
  }

  .pdf-pages :global(.pdf-text-layer) {
    mix-blend-mode: multiply;
  }

  .pdf-pages :global(.pdf-text-item::selection) {
    background: rgba(255, 221, 87, 0.45);
  }

  .pdf-pages :global(.pdf-annotation-overlay) {
    box-sizing: border-box;
    z-index: 5;
    border: 2px solid rgba(255, 193, 7, 0.9);
    background: rgba(255, 235, 59, 0.22);
    pointer-events: none;
  }

  .pdf-pages :global(.pdf-annotation-overlay.text) {
    border-color: transparent;
    background: rgba(255, 235, 59, 0.42);
  }
</style>
