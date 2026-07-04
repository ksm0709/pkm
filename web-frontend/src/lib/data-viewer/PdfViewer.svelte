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

  const DEFAULT_ZOOM = 1.25;
  const MIN_ZOOM = 0.75;
  const MAX_ZOOM = 3;
  const ZOOM_STEP = 0.25;

  let container: HTMLDivElement;
  let loading = $state(false);
  let saving = $state(false);
  let error = $state("");
  let areaMode = $state(false);
  let selectionMenu = $state<{
    x: number;
    y: number;
    annotation: PdfAnnotation;
  } | null>(null);
  let annotationDoc = $state<PdfAnnotationDocument | null>(null);
  let pdfBytes = $state<Uint8Array | null>(null);
  let zoomScale = $state(DEFAULT_ZOOM);
  let cleanup: PdfRenderCleanup | null = null;
  let renderAbortController: AbortController | null = null;
  let renderToken = 0;
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

  function zoomLabel() {
    return `${Math.round(zoomScale * 100)}%`;
  }

  function clampZoom(value: number) {
    return Math.min(Math.max(value, MIN_ZOOM), MAX_ZOOM);
  }

  function freshPdfBuffer() {
    return pdfBytes ? pdfBytes.slice().buffer : null;
  }

  function isAbortError(error: unknown) {
    return error instanceof DOMException && error.name === "AbortError";
  }

  async function renderCurrentPdf() {
    if (!container) return;
    const buffer = freshPdfBuffer();
    if (!buffer) return;
    const token = ++renderToken;
    renderAbortController?.abort();
    const controller = new AbortController();
    renderAbortController = controller;
    hideSelectionMenu();
    areaStart = null;
    cleanup?.();
    cleanup = null;
    try {
      const nextCleanup = await renderPdfIntoContainer(container, buffer, {
        scale: zoomScale,
        signal: controller.signal,
      });
      if (cancelled || token !== renderToken || controller.signal.aborted) {
        nextCleanup();
        return;
      }
      cleanup = nextCleanup;
      paintAnnotationOverlays();
    } catch (err) {
      if (isAbortError(err) || token !== renderToken) return;
      error = err instanceof Error ? err.message : "Failed to render PDF";
    }
  }

  function setZoom(nextZoom: number) {
    const next = clampZoom(nextZoom);
    if (next === zoomScale) return;
    zoomScale = next;
    void renderCurrentPdf();
  }

  function resetZoom() {
    setZoom(DEFAULT_ZOOM);
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
    pdfBytes = null;
    annotationDoc = null;
    renderAbortController?.abort();
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
      pdfBytes = new Uint8Array(buffer);
      await renderCurrentPdf();
      if (cancelled) return;
      try {
        annotationDoc = await loadDataAnnotations(vault, path);
        if (!cancelled) paintAnnotationOverlays();
      } catch (annotationError) {
        if (cancelled) return;
        annotationDoc = emptyAnnotationDoc();
        error =
          annotationError instanceof Error
            ? annotationError.message
            : "Failed to load PDF annotations";
      }
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

  function clamp(value: number, minimum: number, maximum: number) {
    return Math.min(Math.max(value, minimum), maximum);
  }

  function rectBelongsToRenderedPage(rect: DOMRect | ClientRect) {
    if (!container) return false;
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    return Array.from(
      container.querySelectorAll<HTMLElement>(".pdf-page"),
    ).some((page) => {
      const pageRect = page.getBoundingClientRect();
      return (
        centerX >= pageRect.left &&
        centerX <= pageRect.right &&
        centerY >= pageRect.top &&
        centerY <= pageRect.bottom
      );
    });
  }

  function selectionAnchorRect() {
    if (areaMode) return null;
    const selection = window.getSelection();
    if (
      !selection ||
      selection.isCollapsed ||
      selection.rangeCount === 0 ||
      !selection.toString().trim()
    ) {
      return null;
    }
    const range = selection.getRangeAt(0);
    const rects = Array.from(range.getClientRects()).filter(
      (rect) => rect.width > 0 && rect.height > 0,
    );
    const firstPdfRect = rects.find(rectBelongsToRenderedPage);
    return firstPdfRect ?? null;
  }

  function textAnnotationFromCurrentSelection() {
    return createTextAnnotationFromSelection({
      root: container,
      selection: window.getSelection(),
      now: nowIso(),
      id: annotationId("text"),
    });
  }

  function hideSelectionMenu() {
    selectionMenu = null;
  }

  function updateSelectionMenu() {
    const rect = selectionAnchorRect();
    const annotation = rect ? textAnnotationFromCurrentSelection() : null;
    if (!rect || !annotation) {
      hideSelectionMenu();
      return;
    }
    const viewportWidth =
      window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight =
      window.innerHeight || document.documentElement.clientHeight;
    selectionMenu = {
      x: clamp(
        rect.left + rect.width / 2,
        48,
        Math.max(48, viewportWidth - 48),
      ),
      y: clamp(rect.top - 8, 40, Math.max(40, viewportHeight - 8)),
      annotation,
    };
  }

  function handleDocumentSelectionChange() {
    if (!selectionMenu) return;
    updateSelectionMenu();
  }

  function handleDocumentPointerDown(event: PointerEvent) {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest(".pdf-selection-menu")) return;
    if (event.target.closest(".pdf-pages")) return;
    hideSelectionMenu();
  }

  function handleDocumentKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") hideSelectionMenu();
  }

  function toggleAreaMode() {
    areaMode = !areaMode;
    hideSelectionMenu();
  }

  function handlePointerDown(event: PointerEvent) {
    if (!areaMode) return;
    hideSelectionMenu();
    const page = pageFromEventTarget(event.target);
    if (!page) return;
    areaStart = { page, clientX: event.clientX, clientY: event.clientY };
    event.preventDefault();
  }

  function handlePointerUp(event: PointerEvent) {
    if (!areaMode) {
      updateSelectionMenu();
      return;
    }
    if (!areaStart) return;
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
    const annotation = textAnnotationFromCurrentSelection();
    if (!annotation) {
      error = "Select text on a single PDF page before annotating.";
      hideSelectionMenu();
      return;
    }
    hideSelectionMenu();
    void persistAnnotation(annotation);
  }

  function createFloatingTextAnnotation() {
    const annotation = selectionMenu?.annotation;
    if (!annotation) {
      createTextAnnotation();
      return;
    }
    hideSelectionMenu();
    void persistAnnotation(annotation);
  }

  onMount(() => {
    document.addEventListener("selectionchange", handleDocumentSelectionChange);
    document.addEventListener("pointerdown", handleDocumentPointerDown);
    document.addEventListener("keydown", handleDocumentKeydown);
    void loadPdf();
  });

  onDestroy(() => {
    document.removeEventListener(
      "selectionchange",
      handleDocumentSelectionChange,
    );
    document.removeEventListener("pointerdown", handleDocumentPointerDown);
    document.removeEventListener("keydown", handleDocumentKeydown);
    cancelled = true;
    renderAbortController?.abort();
    cleanup?.();
    cleanup = null;
  });
</script>

<section class="pdf-preview" data-testid="pdf-preview" aria-label="PDF preview">
  <div class="annotation-toolbar" aria-label="PDF annotation tools">
    <div class="zoom-toolbar" aria-label="PDF zoom controls">
      <button
        type="button"
        data-testid="pdf-zoom-out"
        disabled={zoomScale <= MIN_ZOOM}
        onclick={() => setZoom(zoomScale - ZOOM_STEP)}
        aria-label="Zoom out"
      >
        −
      </button>
      <span class="zoom-label" data-testid="pdf-zoom-label">{zoomLabel()}</span>
      <button
        type="button"
        data-testid="pdf-zoom-in"
        disabled={zoomScale >= MAX_ZOOM}
        onclick={() => setZoom(zoomScale + ZOOM_STEP)}
        aria-label="Zoom in"
      >
        +
      </button>
      <button
        type="button"
        data-testid="pdf-zoom-reset"
        disabled={zoomScale === DEFAULT_ZOOM}
        onclick={resetZoom}
        aria-label="Reset zoom"
      >
        Reset
      </button>
    </div>
    <button
      type="button"
      data-testid="area-annotation-mode"
      class:active={areaMode}
      onclick={toggleAreaMode}
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
    tabindex="-1"
    aria-label="PDF pages and annotation surface"
    onpointerdown={handlePointerDown}
    onpointerup={handlePointerUp}
  ></div>
  {#if selectionMenu}
    <button
      type="button"
      class="pdf-selection-menu"
      data-testid="floating-text-annotation"
      style:left={`${selectionMenu.x}px`}
      style:top={`${selectionMenu.y}px`}
      onpointerdown={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onclick={(event) => {
        event.stopPropagation();
        createFloatingTextAnnotation();
      }}
    >
      Annotate
    </button>
  {/if}
</section>

<style>
  .pdf-preview {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    min-height: 0;
  }

  .annotation-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2, 8px);
    margin: 0 0 var(--space-3, 12px);
  }

  .zoom-toolbar {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1, 4px);
    padding-right: var(--space-2, 8px);
    border-right: 1px solid var(--border);
  }

  .zoom-label {
    min-width: 46px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 13px;
    text-align: center;
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

  .annotation-toolbar button:disabled {
    cursor: not-allowed;
    opacity: 0.45;
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
    flex: 1 1 auto;
    flex-direction: column;
    align-items: center;
    gap: var(--space-5, 24px);
    min-height: 0;
    padding: var(--space-4, 16px);
    overflow: auto;
  }

  .pdf-selection-menu {
    position: fixed;
    z-index: 50;
    transform: translate(-50%, -100%);
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--accent);
    border-radius: 999px;
    color: var(--bg);
    background: var(--accent);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.3);
    cursor: pointer;
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
