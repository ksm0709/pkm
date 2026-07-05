<script lang="ts">
  import { flushSync, onDestroy, onMount, tick } from "svelte";
  import { apiClient } from "$lib/api/client.js";
  import {
    loadDataAnnotations,
    saveDataAnnotations,
    type PdfAnnotation,
    type PdfAnnotationDocument,
  } from "./annotations";
  import {
    createTextAnnotationFromSelection,
    overlayStyleForRect,
  } from "./annotation-geometry";
  import { apiDataHref } from "$lib/data-viewer/paths";
  import {
    renderPdfIntoContainer,
    type PdfRenderCleanup,
  } from "./pdf-renderer";

  let { vault, path }: { vault: string; path: string } = $props();

  const DEFAULT_ZOOM = 1;
  const MIN_ZOOM = 0.75;
  const MAX_ZOOM = 3;
  const ZOOM_STEP = 0.25;

  type AnnotationMenuAnchor = { x: number; y: number };

  let container: HTMLDivElement;
  let loading = $state(false);
  let saving = $state(false);
  let error = $state("");
  let annotationsPanelOpen = $state(false);
  let draftAnnotation = $state<PdfAnnotation | null>(null);
  let activeAnnotationSnapshot = $state<PdfAnnotation | null>(null);
  let lastDraftSignature: string | null = null;
  let annotationMenu = $state<{
    x: number;
    y: number;
    annotationId: string;
  } | null>(null);
  let annotationDraftComment = $state("");
  let annotationDoc = $state<PdfAnnotationDocument | null>(null);
  let pdfBytes = $state<Uint8Array | null>(null);
  let zoomScale = $state(DEFAULT_ZOOM);
  let cleanup: PdfRenderCleanup | null = null;
  let renderAbortController: AbortController | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let resizeTimer: ReturnType<typeof setTimeout> | null = null;
  let selectionFrame: number | null = null;
  let renderToken = 0;
  let cancelled = false;

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

  function annotationCount() {
    return annotationDoc?.annotations.length ?? 0;
  }

  function annotationPageLabel(annotation: PdfAnnotation) {
    const pages = Array.from(
      new Set(annotation.rects.map((rect) => rect.page).filter(Boolean)),
    ).sort((a, b) => a - b);
    if (!pages.length) return "Page ?";
    return pages.length === 1
      ? `Page ${pages[0]}`
      : `Pages ${pages[0]}-${pages[pages.length - 1]}`;
  }

  function annotationKindLabel(annotation: PdfAnnotation) {
    return annotation.type === "text" ? "Text" : "Area";
  }

  function annotationTimeLabel(annotation: PdfAnnotation) {
    const raw = annotation.updated_at || annotation.created_at;
    if (!raw) return "";
    return raw.replace("T", " ").replace(/\.\d+Z$/, "Z");
  }

  function annotationSignature(annotation: PdfAnnotation) {
    return JSON.stringify({
      quote: annotation.quote ?? "",
      rects: annotation.rects,
    });
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
        overlay.dataset.annotationRects = JSON.stringify(annotation.rects);
        overlay.dataset.annotationQuote = annotation.quote ?? "";
        overlay.dataset.annotationComment = annotation.comment ?? "";
        overlay.dataset.annotationCreatedAt = annotation.created_at;
        overlay.dataset.annotationUpdatedAt = annotation.updated_at;
        overlay.dataset.testid = "pdf-annotation-overlay";
        overlay.tabIndex = 0;
        overlay.setAttribute("role", "button");
        overlay.setAttribute(
          "aria-label",
          `Edit ${annotation.type} PDF annotation`,
        );
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
    hideAnnotationMenu();
    cleanup?.();
    cleanup = null;
    try {
      const nextCleanup = await renderPdfIntoContainer(container, buffer, {
        scale: zoomScale,
        fitToContainer: true,
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

  async function persistAnnotationDocument(
    document: PdfAnnotationDocument,
    fallbackError: string,
    options: { closeMenuOnSuccess?: boolean } = {},
  ) {
    saving = true;
    error = "";
    try {
      const savedDocument = await saveDataAnnotations(vault, path, document);
      annotationDoc = savedDocument;
      paintAnnotationOverlays();
      if (options.closeMenuOnSuccess ?? true) hideAnnotationMenu();
      return savedDocument;
    } catch (err) {
      error = err instanceof Error ? err.message : fallbackError;
      return null;
    } finally {
      saving = false;
    }
  }

  async function persistAnnotation(
    annotation: PdfAnnotation,
    options: { openMenuAt?: AnnotationMenuAnchor } = {},
  ) {
    const current = annotationDoc ?? emptyAnnotationDoc();
    const next: PdfAnnotationDocument = {
      version: 1,
      source_path: path,
      annotations: [...current.annotations, annotation],
    };
    const savedDocument = await persistAnnotationDocument(
      next,
      "Failed to save PDF annotation",
      { closeMenuOnSuccess: !options.openMenuAt },
    );
    const savedAnnotation = savedDocument?.annotations.find(
      (candidate) => candidate.id === annotation.id,
    );
    if (savedAnnotation && options.openMenuAt) {
      openAnnotationMenuForAnnotation(savedAnnotation, options.openMenuAt);
    }
  }

  function selectedAnnotation() {
    const id = annotationMenu?.annotationId;
    if (!id) return null;
    if (draftAnnotation?.id === id) return draftAnnotation;
    if (activeAnnotationSnapshot?.id === id) return activeAnnotationSnapshot;
    return (
      annotationDoc?.annotations.find((annotation) => annotation.id === id) ??
      null
    );
  }

  function selectedAnnotationIsDraft() {
    return Boolean(
      draftAnnotation && annotationMenu?.annotationId === draftAnnotation.id,
    );
  }

  function saveSelectedAnnotationComment() {
    const selected = selectedAnnotation();
    if (!selected) return;
    const current = annotationDoc ?? emptyAnnotationDoc();
    const updated = {
      ...selected,
      comment: annotationDraftComment,
      updated_at: nowIso(),
    };
    const next: PdfAnnotationDocument = {
      version: 1,
      source_path: path,
      annotations: selectedAnnotationIsDraft()
        ? [...current.annotations, updated]
        : current.annotations.map((annotation) =>
            annotation.id === selected.id ? updated : annotation,
          ),
    };
    void persistAnnotationDocument(next, "Failed to save PDF annotation");
  }

  function deleteAnnotation(annotation: PdfAnnotation) {
    if (draftAnnotation?.id === annotation.id) {
      hideAnnotationMenu();
      return;
    }
    const current = annotationDoc ?? emptyAnnotationDoc();
    const next: PdfAnnotationDocument = {
      version: 1,
      source_path: path,
      annotations: current.annotations.filter(
        (candidate) => candidate.id !== annotation.id,
      ),
    };
    void persistAnnotationDocument(next, "Failed to delete PDF annotation");
  }

  function deleteSelectedAnnotation() {
    const selected = selectedAnnotation();
    if (!selected) return;
    deleteAnnotation(selected);
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
      loading = false;
      await tick();
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
    if (annotationMenu) return null;
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
    lastDraftSignature = null;
  }

  function hideAnnotationMenu() {
    annotationMenu = null;
    annotationDraftComment = "";
    draftAnnotation = null;
    activeAnnotationSnapshot = null;
    lastDraftSignature = null;
  }

  function overlayFromTarget(target: EventTarget | null) {
    return target instanceof Element
      ? target.closest<HTMLElement>(".pdf-annotation-overlay")
      : null;
  }

  function annotationMenuPosition(anchor: AnnotationMenuAnchor) {
    const viewportWidth =
      window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight =
      window.innerHeight || document.documentElement.clientHeight;
    return {
      x: clamp(anchor.x, 72, Math.max(72, viewportWidth - 72)),
      y: clamp(anchor.y, 72, Math.max(72, viewportHeight - 8)),
    };
  }

  function openAnnotationMenuForAnnotation(
    annotation: PdfAnnotation,
    anchor: AnnotationMenuAnchor,
  ) {
    const position = annotationMenuPosition(anchor);
    hideSelectionMenu();
    activeAnnotationSnapshot = annotation;
    annotationDraftComment = annotation.comment ?? "";
    annotationMenu = {
      annotationId: annotation.id,
      x: position.x,
      y: position.y,
    };
    flushSync();
  }

  function annotationFromElement(element: HTMLElement): PdfAnnotation | null {
    const id = element.dataset.annotationId;
    const type = element.dataset.annotationType;
    const createdAt = element.dataset.annotationCreatedAt;
    const updatedAt = element.dataset.annotationUpdatedAt;
    if (
      !id ||
      (type !== "text" && type !== "area") ||
      !createdAt ||
      !updatedAt
    ) {
      return null;
    }
    try {
      const rects = JSON.parse(element.dataset.annotationRects ?? "[]");
      if (!Array.isArray(rects) || rects.length === 0) return null;
      return {
        id,
        type,
        rects,
        quote: element.dataset.annotationQuote || undefined,
        comment: element.dataset.annotationComment ?? "",
        created_at: createdAt,
        updated_at: updatedAt,
      };
    } catch {
      return null;
    }
  }

  function openAnnotationMenuFromOverlay(overlay: HTMLElement) {
    const annotationId = overlay.dataset.annotationId;
    const annotation =
      annotationDoc?.annotations.find(
        (candidate) => candidate.id === annotationId,
      ) ?? annotationFromElement(overlay);
    if (!annotation) return;
    const rect = overlay.getBoundingClientRect();
    openAnnotationMenuForAnnotation(annotation, {
      x: rect.left + rect.width / 2,
      y: rect.bottom + 8,
    });
  }

  function requestFrame(callback: () => void) {
    return (window.requestAnimationFrame ?? window.setTimeout)(callback);
  }

  function cancelFrame(frame: number) {
    (window.cancelAnimationFrame ?? window.clearTimeout)(frame);
  }

  function updateSelectionMenu() {
    const rect = selectionAnchorRect();
    const annotation = rect ? textAnnotationFromCurrentSelection() : null;
    if (!rect || !annotation) {
      lastDraftSignature = null;
      return;
    }
    const signature = annotationSignature(annotation);
    if (signature === lastDraftSignature) return;
    lastDraftSignature = signature;
    draftAnnotation = annotation;
    annotationsPanelOpen = false;
    openAnnotationMenuForAnnotation(annotation, {
      x: rect.left + rect.width / 2,
      y: rect.bottom + 8,
    });
  }

  function scheduleSelectionMenuUpdate() {
    if (selectionFrame !== null) cancelFrame(selectionFrame);
    selectionFrame = requestFrame(() => {
      selectionFrame = null;
      updateSelectionMenu();
    });
  }

  function handleDocumentSelectionChange() {
    scheduleSelectionMenuUpdate();
  }

  function handleDocumentPointerDown(event: PointerEvent) {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest(".annotation-toolbar")) return;
    if (event.target.closest(".pdf-annotations-panel")) return;
    if (event.target.closest(".pdf-annotation-menu")) return;
    if (event.target.closest(".pdf-annotation-overlay")) return;
    if (event.target.closest(".pdf-pages")) {
      hideAnnotationMenu();
      return;
    }
    hideSelectionMenu();
    hideAnnotationMenu();
  }

  function handleDocumentKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      hideSelectionMenu();
      hideAnnotationMenu();
      annotationsPanelOpen = false;
    }
  }

  function clearResizeTimer() {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = null;
  }

  function toggleAnnotationsPanel() {
    const nextOpen = !annotationsPanelOpen;
    annotationsPanelOpen = nextOpen;
    if (nextOpen) {
      clearResizeTimer();
      hideAnnotationMenu();
      return;
    }
    scheduleResizeRender();
  }

  function handlePointerDown(event: PointerEvent) {
    if (overlayFromTarget(event.target)) {
      event.stopPropagation();
    }
  }

  function handlePointerUp(event: PointerEvent) {
    if (overlayFromTarget(event.target)) return;
    updateSelectionMenu();
  }

  function handlePdfPagesClick(event: MouseEvent) {
    const overlay = overlayFromTarget(event.target);
    if (!overlay) return;
    event.preventDefault();
    event.stopPropagation();
    openAnnotationMenuFromOverlay(overlay);
  }

  function handlePdfPagesKeydown(event: KeyboardEvent) {
    const overlay = overlayFromTarget(event.target);
    if (!overlay) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    event.stopPropagation();
    openAnnotationMenuFromOverlay(overlay);
  }

  function openAnnotationMenuFromCard(
    annotation: PdfAnnotation,
    target: HTMLElement,
  ) {
    const rect = target.getBoundingClientRect();
    openAnnotationMenuForAnnotation(annotation, {
      x: rect.left + rect.width / 2,
      y: rect.bottom + 8,
    });
  }

  function handleAnnotationCardAction(
    action: HTMLButtonElement,
    event: MouseEvent | PointerEvent,
  ) {
    const annotationId = action.dataset.annotationId;
    const annotation =
      annotationDoc?.annotations.find(
        (candidate) => candidate.id === annotationId,
      ) ?? annotationFromElement(action);
    if (!annotation) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    if (action.dataset.annotationAction === "edit") {
      openAnnotationMenuFromCard(annotation, action);
      return;
    }
    if (action.dataset.annotationAction === "delete") {
      deleteAnnotation(annotation);
    }
  }

  function handleAnnotationCardPointerDown(event: PointerEvent) {
    if (event.currentTarget instanceof HTMLButtonElement) {
      handleAnnotationCardAction(event.currentTarget, event);
    }
  }

  function handleDocumentAnnotationCardPointerDown(event: PointerEvent) {
    const action =
      event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>(
            ".pdf-annotations-panel button[data-annotation-id]",
          )
        : null;
    if (!action) return;
    handleAnnotationCardAction(action, event);
  }

  function handleDocumentAnnotationCardClick(event: MouseEvent) {
    const action =
      event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>(
            ".pdf-annotations-panel button[data-annotation-id]",
          )
        : null;
    if (!action) return;
    handleAnnotationCardAction(action, event);
  }

  function scheduleResizeRender() {
    if (!pdfBytes || annotationMenu || annotationsPanelOpen) return;
    clearResizeTimer();
    resizeTimer = setTimeout(() => {
      resizeTimer = null;
      if (!pdfBytes || annotationMenu || annotationsPanelOpen) return;
      void renderCurrentPdf();
    }, 80);
  }

  onMount(() => {
    document.addEventListener("selectionchange", handleDocumentSelectionChange);
    document.addEventListener(
      "pointerdown",
      handleDocumentAnnotationCardPointerDown,
      true,
    );
    document.addEventListener("pointerdown", handleDocumentPointerDown);
    document.addEventListener("click", handleDocumentAnnotationCardClick);
    document.addEventListener("keydown", handleDocumentKeydown);
    window.addEventListener("resize", scheduleResizeRender);
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(scheduleResizeRender);
      if (container) resizeObserver.observe(container);
    }
    void loadPdf();
  });

  onDestroy(() => {
    document.removeEventListener(
      "selectionchange",
      handleDocumentSelectionChange,
    );
    document.removeEventListener(
      "pointerdown",
      handleDocumentAnnotationCardPointerDown,
      true,
    );
    document.removeEventListener("pointerdown", handleDocumentPointerDown);
    document.removeEventListener("click", handleDocumentAnnotationCardClick);
    document.removeEventListener("keydown", handleDocumentKeydown);
    window.removeEventListener("resize", scheduleResizeRender);
    resizeObserver?.disconnect();
    resizeObserver = null;
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = null;
    if (selectionFrame !== null) cancelFrame(selectionFrame);
    selectionFrame = null;
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
      data-testid="pdf-annotations-toggle"
      class:active={annotationsPanelOpen}
      onclick={toggleAnnotationsPanel}
      aria-expanded={annotationsPanelOpen}
    >
      Annotations ({annotationCount()})
    </button>
    {#if saving}
      <span class="saving">Saving…</span>
    {/if}
  </div>
  {#if annotationsPanelOpen}
    <div
      class="pdf-annotations-panel"
      data-testid="pdf-annotations-panel"
      role="region"
      aria-label="PDF annotations"
      onpointerdown={(event) => event.stopPropagation()}
    >
      {#if annotationCount() === 0}
        <p class="annotations-empty" data-testid="pdf-annotations-empty">
          No annotations yet. Drag PDF text to add one.
        </p>
      {:else}
        <div class="annotation-card-list">
          {#each annotationDoc?.annotations ?? [] as annotation (annotation.id)}
            <article class="annotation-card" data-testid="pdf-annotation-card">
              <div class="annotation-card-meta">
                <span>{annotationKindLabel(annotation)}</span>
                <span>{annotationPageLabel(annotation)}</span>
                {#if annotationTimeLabel(annotation)}
                  <span>{annotationTimeLabel(annotation)}</span>
                {/if}
              </div>
              {#if annotation.quote}
                <blockquote>{annotation.quote}</blockquote>
              {/if}
              {#if annotation.comment}
                <p>{annotation.comment}</p>
              {:else}
                <p class="annotation-card-muted">No comment</p>
              {/if}
              <div class="annotation-card-actions">
                <button
                  type="button"
                  data-testid="pdf-annotation-card-edit"
                  data-annotation-id={annotation.id}
                  data-annotation-type={annotation.type}
                  data-annotation-rects={JSON.stringify(annotation.rects)}
                  data-annotation-quote={annotation.quote ?? ""}
                  data-annotation-comment={annotation.comment ?? ""}
                  data-annotation-created-at={annotation.created_at}
                  data-annotation-updated-at={annotation.updated_at}
                  data-annotation-action="edit"
                  onpointerdown={handleAnnotationCardPointerDown}
                >
                  Edit
                </button>
                <button
                  type="button"
                  class="danger"
                  data-testid="pdf-annotation-card-delete"
                  data-annotation-id={annotation.id}
                  data-annotation-type={annotation.type}
                  data-annotation-rects={JSON.stringify(annotation.rects)}
                  data-annotation-quote={annotation.quote ?? ""}
                  data-annotation-comment={annotation.comment ?? ""}
                  data-annotation-created-at={annotation.created_at}
                  data-annotation-updated-at={annotation.updated_at}
                  data-annotation-action="delete"
                  onpointerdown={handleAnnotationCardPointerDown}
                >
                  Delete
                </button>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
  {#if loading}
    <p class="notice">Loading PDF…</p>
  {/if}
  {#if error}
    <p class="notice error" role="alert">{error}</p>
  {/if}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    bind:this={container}
    class="pdf-pages"
    data-testid="pdf-pages"
    role="application"
    tabindex="-1"
    aria-label="PDF pages and annotation surface"
    onpointerdown={handlePointerDown}
    onpointerup={handlePointerUp}
    onclick={handlePdfPagesClick}
    onkeydown={handlePdfPagesKeydown}
  ></div>
  {#if annotationMenu}
    <div
      class="pdf-annotation-menu"
      data-testid="pdf-annotation-menu"
      style:left={`${annotationMenu.x}px`}
      style:top={`${annotationMenu.y}px`}
      role="dialog"
      tabindex="-1"
      aria-label="PDF annotation actions"
      onpointerdown={(event) => event.stopPropagation()}
    >
      <label>
        Comment
        <textarea
          data-testid="pdf-annotation-comment"
          bind:value={annotationDraftComment}
          rows="3"
        ></textarea>
      </label>
      <div class="annotation-menu-actions">
        <button
          type="button"
          data-testid="pdf-annotation-save"
          onclick={saveSelectedAnnotationComment}
        >
          Save
        </button>
        <button
          type="button"
          class="danger"
          data-testid="pdf-annotation-delete"
          onclick={deleteSelectedAnnotation}
        >
          Delete
        </button>
        <button
          type="button"
          data-testid="pdf-annotation-cancel"
          onclick={hideAnnotationMenu}
        >
          Cancel
        </button>
      </div>
    </div>
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

  .pdf-annotations-panel {
    display: block;
    max-height: min(360px, 45vh);
    margin: 0 0 var(--space-3, 12px);
    padding: var(--space-3, 12px);
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface, var(--bg));
  }

  .annotation-card-list {
    display: grid;
    gap: var(--space-3, 12px);
  }

  .annotation-card {
    display: grid;
    gap: var(--space-2, 8px);
    padding: var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
  }

  .annotation-card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    color: var(--text-muted);
    font-size: 12px;
  }

  .annotation-card blockquote,
  .annotation-card p {
    margin: 0;
  }

  .annotation-card blockquote {
    padding-left: var(--space-2, 8px);
    border-left: 3px solid rgba(255, 235, 59, 0.7);
    color: var(--text);
  }

  .annotation-card-muted,
  .annotations-empty {
    color: var(--text-muted);
  }

  .annotation-card-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
  }

  .annotation-card-actions button {
    min-height: 28px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text);
    background: var(--surface, transparent);
    cursor: pointer;
  }

  .annotation-card-actions button.danger {
    border-color: color-mix(in srgb, #ff5a5f 70%, var(--border));
    color: #ffb4b4;
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
    align-items: flex-start;
    gap: var(--space-5, 24px);
    min-height: 0;
    padding: var(--space-4, 16px);
    overflow: auto;
  }

  .pdf-annotation-menu {
    position: fixed;
    z-index: 50;
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.3);
  }

  .pdf-annotation-menu {
    box-sizing: border-box;
    transform: translate(-50%, 0);
    width: min(320px, calc(100vw - 32px));
    padding: var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text);
    background: var(--surface, var(--bg));
  }

  .pdf-annotation-menu label {
    display: grid;
    gap: var(--space-2, 8px);
    color: var(--text-muted);
    font-size: 13px;
  }

  .pdf-annotation-menu textarea {
    box-sizing: border-box;
    width: 100%;
    resize: vertical;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: var(--space-2, 8px);
    color: var(--text);
    background: var(--bg);
    font: inherit;
  }

  .annotation-menu-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    margin-top: var(--space-3, 12px);
  }

  .annotation-menu-actions button {
    min-height: 30px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text);
    background: var(--bg);
    cursor: pointer;
  }

  .annotation-menu-actions button.danger {
    border-color: color-mix(in srgb, #ff5a5f 70%, var(--border));
    color: #ffb4b4;
  }

  .pdf-pages :global(.pdf-page) {
    flex: 0 0 auto;
    margin-inline: auto;
    outline: 1px solid var(--border);
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
    pointer-events: auto;
    cursor: pointer;
  }

  .pdf-pages :global(.pdf-annotation-overlay:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .pdf-pages :global(.pdf-annotation-overlay.text) {
    border-color: transparent;
    background: rgba(255, 235, 59, 0.42);
  }
</style>
