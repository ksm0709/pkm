<script lang="ts">
  import { flushSync, onDestroy, onMount, tick } from "svelte";
  import { apiClient } from "$lib/api/client.js";
  import ScrollPositionOverlay from "$lib/components/ScrollPositionOverlay.svelte";
  import {
    clampFloatingPosition,
    floatingSizeForViewport,
    floatingTopLeftFromAnchor,
    viewportSize,
  } from "$lib/ui/floating-position";
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
  import { apiDataHref, viewerDataHref } from "$lib/data-viewer/paths";
  import {
    renderPdfIntoContainer,
    type PdfRenderCleanup,
  } from "./pdf-renderer";

  let { vault, path }: { vault: string; path: string } = $props();

  const DEFAULT_ZOOM = 1;
  const MIN_ZOOM = 0.75;
  const MAX_ZOOM = 3;
  const ZOOM_STEP = 0.25;
  const RESIZE_EPSILON_PX = 2;
  const ANNOTATION_MENU_EDGE_INSET = 8;
  const ANNOTATION_MENU_MAX_SIZE = { width: 320, height: 260 };

  type AnnotationMenuAnchor = { x: number; y: number };
  type FloatingDragState = { offsetX: number; offsetY: number };

  let container = $state<HTMLDivElement | null>(null);
  let loading = $state(false);
  let saving = $state(false);
  let error = $state("");
  let annotationsPanelOpen = $state(false);
  let draftAnnotation = $state<PdfAnnotation | null>(null);
  let activeAnnotationSnapshot = $state<PdfAnnotation | null>(null);
  let lastDraftSignature: string | null = null;
  let selectionAction = $state<{
    x: number;
    y: number;
    annotation: PdfAnnotation;
  } | null>(null);
  let annotationMenu = $state<{
    x: number;
    y: number;
    annotationId: string;
  } | null>(null);
  let annotationMenuDrag = $state<FloatingDragState | null>(null);
  let annotationDraftComment = $state("");
  let annotationAddToLog = $state(false);
  let annotationDoc = $state<PdfAnnotationDocument | null>(null);
  let pdfBytes = $state<Uint8Array | null>(null);
  let pdfPageCount = $state(0);
  let zoomScale = $state(DEFAULT_ZOOM);
  let cleanup: PdfRenderCleanup | null = null;
  let renderAbortController: AbortController | null = null;
  let resizeObserver: ResizeObserver | null = null;
  let resizeTimer: ReturnType<typeof setTimeout> | null = null;
  let selectionFrame: number | null = null;
  let renderingPdf = false;
  let pendingResizeAfterRender = false;
  let pendingZoomAfterRender = false;
  let initialRenderComplete = $state(false);
  let renderedZoomScale = DEFAULT_ZOOM;
  let optimisticZoomActive = false;
  let renderToken = 0;
  let cancelled = false;
  let lastObservedContainerSize: { width: number; height: number } | null =
    null;

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

  function currentPdfPageLabel() {
    if (!container || pdfPageCount <= 0) return null;
    const pages = Array.from(
      container.querySelectorAll<HTMLElement>(".pdf-page[data-page-number]"),
    );
    if (!pages.length) return `Page 1 / ${pdfPageCount}`;

    const scrollRect = container.getBoundingClientRect();
    const centerY = scrollRect.top + scrollRect.height / 2;
    let bestPage = 1;
    let bestDistance = Number.POSITIVE_INFINITY;

    for (const page of pages) {
      const pageNumber = Number(page.dataset.pageNumber ?? "");
      if (!Number.isFinite(pageNumber) || pageNumber <= 0) continue;
      const rect = page.getBoundingClientRect();
      if (rect.height > 0 && centerY >= rect.top && centerY <= rect.bottom) {
        bestPage = pageNumber;
        bestDistance = 0;
        break;
      }
      const pageCenter = rect.top + rect.height / 2;
      const distance = Math.abs(centerY - pageCenter);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestPage = pageNumber;
      }
    }

    if (!Number.isFinite(bestDistance)) {
      const maxScroll = Math.max(
        container.scrollHeight - container.clientHeight,
        1,
      );
      bestPage =
        Math.round((container.scrollTop / maxScroll) * (pdfPageCount - 1)) + 1;
    }

    const clampedPage = clamp(bestPage, 1, pdfPageCount);
    return `Page ${clampedPage} / ${pdfPageCount}`;
  }

  function clampZoom(value: number) {
    return Math.min(Math.max(value, MIN_ZOOM), MAX_ZOOM);
  }

  function freshPdfBuffer() {
    return pdfBytes ? pdfBytes.slice().buffer : null;
  }

  function numericStylePx(element: HTMLElement, property: "width" | "height") {
    const parsed = Number.parseFloat(element.style[property]);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
    const rect = element.getBoundingClientRect();
    return property === "width" ? rect.width : rect.height;
  }

  function scrollProgressSnapshot() {
    if (!container) return null;
    const maxScroll = container.scrollHeight - container.clientHeight;
    if (maxScroll <= 0 || container.scrollTop <= 0) return null;
    return container.scrollTop / maxScroll;
  }

  function restoreScrollProgress(ratio: number | null) {
    if (!container || ratio === null) return;
    const maxScroll = container.scrollHeight - container.clientHeight;
    if (maxScroll <= 0) return;
    container.scrollTop = ratio * maxScroll;
  }

  function clearOptimisticZoomPreview() {
    if (!container || !optimisticZoomActive) return;
    for (const page of container.querySelectorAll<HTMLElement>(".pdf-page")) {
      const baseWidth = page.dataset.optimisticZoomBaseWidth;
      const baseHeight = page.dataset.optimisticZoomBaseHeight;
      if (baseWidth) page.style.width = `${baseWidth}px`;
      if (baseHeight) page.style.height = `${baseHeight}px`;
      delete page.dataset.optimisticZoomBaseWidth;
      delete page.dataset.optimisticZoomBaseHeight;
      page.classList.remove("pdf-optimistic-zoom");
      for (const child of page.querySelectorAll<HTMLElement>(
        ".pdf-page-canvas, .pdf-annotation-overlay",
      )) {
        child.style.transform = child.dataset.optimisticZoomTransform ?? "";
        child.style.transformOrigin =
          child.dataset.optimisticZoomTransformOrigin ?? "";
        delete child.dataset.optimisticZoomTransform;
        delete child.dataset.optimisticZoomTransformOrigin;
      }
    }
    optimisticZoomActive = false;
  }

  function applyOptimisticZoomPreview() {
    if (!container || !initialRenderComplete) return;
    const pages = Array.from(
      container.querySelectorAll<HTMLElement>(".pdf-page"),
    );
    if (!pages.length) return;
    const ratio = zoomScale / renderedZoomScale;
    const scrollRatio = scrollProgressSnapshot();
    if (!Number.isFinite(ratio) || Math.abs(ratio - 1) < 0.001) {
      clearOptimisticZoomPreview();
      restoreScrollProgress(scrollRatio);
      return;
    }

    for (const page of pages) {
      if (!page.dataset.optimisticZoomBaseWidth) {
        page.dataset.optimisticZoomBaseWidth = String(
          numericStylePx(page, "width"),
        );
        page.dataset.optimisticZoomBaseHeight = String(
          numericStylePx(page, "height"),
        );
      }
      const baseWidth = Number.parseFloat(
        page.dataset.optimisticZoomBaseWidth ?? "0",
      );
      const baseHeight = Number.parseFloat(
        page.dataset.optimisticZoomBaseHeight ?? "0",
      );
      if (baseWidth > 0) page.style.width = `${baseWidth * ratio}px`;
      if (baseHeight > 0) page.style.height = `${baseHeight * ratio}px`;
      page.classList.add("pdf-optimistic-zoom");
      for (const child of page.querySelectorAll<HTMLElement>(
        ".pdf-page-canvas, .pdf-annotation-overlay",
      )) {
        if (child.dataset.optimisticZoomTransform === undefined) {
          child.dataset.optimisticZoomTransform = child.style.transform;
          child.dataset.optimisticZoomTransformOrigin =
            child.style.transformOrigin;
        }
        child.style.transform = `scale(${ratio})`;
        child.style.transformOrigin = "0 0";
      }
    }
    optimisticZoomActive = true;
    restoreScrollProgress(scrollRatio);
  }

  function isAbortError(error: unknown) {
    return error instanceof DOMException && error.name === "AbortError";
  }

  function queueResizeRenderAfterCurrentRender() {
    pendingResizeAfterRender = true;
  }

  function queueZoomRenderAfterCurrentRender() {
    pendingZoomAfterRender = true;
  }

  function revealInitialRender(token: number, controller: AbortController) {
    if (
      token === renderToken &&
      !cancelled &&
      !controller.signal.aborted &&
      !initialRenderComplete
    ) {
      initialRenderComplete = true;
      loading = false;
    }
  }

  async function renderCurrentPdf(
    reason: "initial" | "zoom" | "resize" = "zoom",
  ) {
    if (!container) return;
    const buffer = freshPdfBuffer();
    if (!buffer) return;
    if (renderingPdf) {
      if (reason === "zoom") {
        queueZoomRenderAfterCurrentRender();
        renderAbortController?.abort();
      }
      if (reason === "resize" && initialRenderComplete) {
        queueResizeRenderAfterCurrentRender();
      }
      return;
    }
    const token = ++renderToken;
    const renderZoomScale = zoomScale;
    renderingPdf = true;
    renderAbortController?.abort();
    const controller = new AbortController();
    renderAbortController = controller;
    hideSelectionMenu();
    hideAnnotationMenu();
    const previousCleanup = cleanup;
    try {
      const nextCleanup = await renderPdfIntoContainer(container, buffer, {
        scale: zoomScale,
        fitToContainer: true,
        signal: controller.signal,
        preservePagesOnAbort: true,
        onDocumentLoaded: ({ pageCount }) => {
          if (
            token === renderToken &&
            !cancelled &&
            !controller.signal.aborted
          ) {
            pdfPageCount = pageCount;
          }
        },
        onFirstPageRendered: () => {
          if (reason === "initial") revealInitialRender(token, controller);
        },
      });
      if (cancelled || token !== renderToken || controller.signal.aborted) {
        nextCleanup();
        return;
      }
      cleanup = nextCleanup;
      previousCleanup?.();
      renderedZoomScale = renderZoomScale;
      optimisticZoomActive = false;
      if (reason === "initial") revealInitialRender(token, controller);
      paintAnnotationOverlays();
    } catch (err) {
      if (isAbortError(err) || token !== renderToken) return;
      clearOptimisticZoomPreview();
      error = err instanceof Error ? err.message : "Failed to render PDF";
    } finally {
      if (token === renderToken) {
        renderingPdf = false;
        const shouldRenderPendingZoom = pendingZoomAfterRender;
        const shouldRenderPendingResize = pendingResizeAfterRender;
        pendingZoomAfterRender = false;
        pendingResizeAfterRender = false;
        if (
          shouldRenderPendingZoom &&
          !cancelled &&
          initialRenderComplete &&
          pdfBytes
        ) {
          void renderCurrentPdf("zoom");
        } else if (
          shouldRenderPendingResize &&
          !cancelled &&
          initialRenderComplete &&
          pdfBytes &&
          !annotationMenu &&
          !annotationsPanelOpen
        ) {
          scheduleResizeRender();
        }
      }
    }
  }

  function setZoom(nextZoom: number) {
    const next = clampZoom(nextZoom);
    if (next === zoomScale) return;
    zoomScale = next;
    applyOptimisticZoomPreview();
    void renderCurrentPdf("zoom");
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

  function pdfAnnotationDailyLogContent(
    annotation: PdfAnnotation,
    comment: string,
  ) {
    const source = `[${path}](${viewerDataHref(vault, path)})`;
    const quote = (annotation.quote || annotationPageLabel(annotation))
      .replace(/\s+/g, " ")
      .trim();
    return `Annotated ${source}: “${quote}” — ${comment.trim()}`;
  }

  async function postAnnotationDailyLog(
    annotation: PdfAnnotation,
    comment: string,
  ) {
    const response = await apiClient(
      `/api/v1/vault/${encodeURIComponent(vault)}/daily/today`,
      {
        method: "POST",
        body: JSON.stringify({
          type: "entry",
          content: pdfAnnotationDailyLogContent(annotation, comment),
        }),
      },
    );
    if (!response.ok) throw new Error(`POST daily log -> ${response.status}`);
  }

  async function saveSelectedAnnotationComment() {
    const selected = selectedAnnotation();
    if (!selected) return;
    const current = annotationDoc ?? emptyAnnotationDoc();
    const comment = annotationDraftComment;
    const shouldLog = selectedAnnotationIsDraft() && annotationAddToLog;
    const updated = {
      ...selected,
      comment,
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
    const savedDocument = await persistAnnotationDocument(
      next,
      "Failed to save PDF annotation",
      { closeMenuOnSuccess: !shouldLog },
    );
    if (!savedDocument) return;
    if (!shouldLog) return;
    saving = true;
    error = "";
    try {
      await postAnnotationDailyLog(updated, comment);
      hideAnnotationMenu();
    } catch (err) {
      error = err instanceof Error ? err.message : "Failed to add daily log";
    } finally {
      saving = false;
    }
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
    pdfPageCount = 0;
    annotationDoc = null;
    initialRenderComplete = false;
    pendingResizeAfterRender = false;
    pendingZoomAfterRender = false;
    clearOptimisticZoomPreview();
    renderedZoomScale = zoomScale;
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
      await tick();
      await renderCurrentPdf("initial");
      if (cancelled) return;
      initialRenderComplete = true;
      loading = false;
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
    if (!container) return null;
    return createTextAnnotationFromSelection({
      root: container,
      selection: window.getSelection(),
      now: nowIso(),
      id: annotationId("text"),
    });
  }

  function hideSelectionMenu() {
    selectionAction = null;
    lastDraftSignature = null;
  }

  function hideAnnotationMenu() {
    annotationMenu = null;
    annotationMenuDrag = null;
    annotationDraftComment = "";
    annotationAddToLog = false;
    draftAnnotation = null;
    activeAnnotationSnapshot = null;
    lastDraftSignature = null;
  }

  function overlayFromTarget(target: EventTarget | null) {
    return target instanceof Element
      ? target.closest<HTMLElement>(".pdf-annotation-overlay")
      : null;
  }

  function annotationMenuSize() {
    return floatingSizeForViewport(
      ANNOTATION_MENU_MAX_SIZE,
      viewportSize(),
      ANNOTATION_MENU_EDGE_INSET,
    );
  }

  function annotationMenuPosition(anchor: AnnotationMenuAnchor) {
    return floatingTopLeftFromAnchor(
      anchor,
      annotationMenuSize(),
      viewportSize(),
      ANNOTATION_MENU_EDGE_INSET,
    );
  }

  function openAnnotationMenuForAnnotation(
    annotation: PdfAnnotation,
    anchor: AnnotationMenuAnchor,
  ) {
    const position = annotationMenuPosition(anchor);
    hideSelectionMenu();
    activeAnnotationSnapshot = annotation;
    annotationDraftComment = annotation.comment ?? "";
    annotationAddToLog = false;
    annotationMenu = {
      annotationId: annotation.id,
      x: position.x,
      y: position.y,
    };
    flushSync();
  }

  function startAnnotationMenuDrag(event: PointerEvent) {
    if (!annotationMenu) return;
    const menu = (event.currentTarget as HTMLElement).closest<HTMLElement>(
      ".pdf-annotation-menu",
    );
    const rect = menu?.getBoundingClientRect();
    const currentLeft = rect && rect.width > 0 ? rect.left : annotationMenu.x;
    const currentTop = rect && rect.height > 0 ? rect.top : annotationMenu.y;
    annotationMenuDrag = {
      offsetX: event.clientX - currentLeft,
      offsetY: event.clientY - currentTop,
    };
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function dragAnnotationMenu(event: PointerEvent) {
    if (!annotationMenu || !annotationMenuDrag) return;
    const position = clampFloatingPosition(
      {
        x: event.clientX - annotationMenuDrag.offsetX,
        y: event.clientY - annotationMenuDrag.offsetY,
      },
      annotationMenuSize(),
      viewportSize(),
      ANNOTATION_MENU_EDGE_INSET,
    );
    annotationMenu = { ...annotationMenu, ...position };
  }

  function endAnnotationMenuDrag() {
    annotationMenuDrag = null;
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
      hideSelectionMenu();
      return;
    }
    const signature = annotationSignature(annotation);
    if (signature === lastDraftSignature) return;
    lastDraftSignature = signature;
    annotationsPanelOpen = false;
    selectionAction = {
      annotation,
      x: rect.left + rect.width / 2,
      y: rect.bottom + 8,
    };
  }

  function openSelectionAnnotationDraft() {
    if (!selectionAction) return;
    const { annotation, x, y } = selectionAction;
    draftAnnotation = annotation;
    openAnnotationMenuForAnnotation(annotation, { x, y });
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
    if (event.target.closest(".pdf-selection-action")) return;
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

  function observedSizeFromEntry(entry: ResizeObserverEntry | undefined) {
    const rect = entry?.contentRect;
    const width = rect?.width ?? container?.clientWidth ?? 0;
    const height = rect?.height ?? container?.clientHeight ?? 0;
    if (width <= 0 || height <= 0) return null;
    return { width, height };
  }

  function containerSizeChanged(
    previous: { width: number; height: number },
    next: { width: number; height: number },
  ) {
    return (
      Math.abs(previous.width - next.width) >= RESIZE_EPSILON_PX ||
      Math.abs(previous.height - next.height) >= RESIZE_EPSILON_PX
    );
  }

  function handleContainerResize(entries: ResizeObserverEntry[]) {
    const nextSize = observedSizeFromEntry(entries[0]);
    if (!nextSize) return;
    if (!lastObservedContainerSize) {
      lastObservedContainerSize = nextSize;
      return;
    }
    if (!containerSizeChanged(lastObservedContainerSize, nextSize)) return;
    lastObservedContainerSize = nextSize;
    scheduleResizeRender();
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
    if (renderingPdf) {
      if (initialRenderComplete) queueResizeRenderAfterCurrentRender();
      return;
    }
    clearResizeTimer();
    resizeTimer = setTimeout(() => {
      resizeTimer = null;
      if (!pdfBytes || annotationMenu || annotationsPanelOpen) return;
      if (renderingPdf) {
        if (initialRenderComplete) queueResizeRenderAfterCurrentRender();
        return;
      }
      void renderCurrentPdf("resize");
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
      resizeObserver = new ResizeObserver(handleContainerResize);
      if (container) resizeObserver.observe(container);
    }
    void loadPdf();
  });

  onDestroy(() => {
    if (typeof document !== "undefined") {
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
    }
    if (typeof window !== "undefined") {
      window.removeEventListener("resize", scheduleResizeRender);
    }
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
        disabled={loading || zoomScale <= MIN_ZOOM}
        onclick={() => setZoom(zoomScale - ZOOM_STEP)}
        aria-label="Zoom out"
      >
        −
      </button>
      <span class="zoom-label" data-testid="pdf-zoom-label">{zoomLabel()}</span>
      <button
        type="button"
        data-testid="pdf-zoom-in"
        disabled={loading || zoomScale >= MAX_ZOOM}
        onclick={() => setZoom(zoomScale + ZOOM_STEP)}
        aria-label="Zoom in"
      >
        +
      </button>
      <button
        type="button"
        data-testid="pdf-zoom-reset"
        disabled={loading || zoomScale === DEFAULT_ZOOM}
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
    <p class="notice pdf-loading-overlay" data-testid="pdf-loading">
      Loading PDF…
    </p>
  {/if}
  {#if error}
    <p class="notice error" role="alert">{error}</p>
  {/if}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    bind:this={container}
    class="pdf-pages"
    class:initial-rendering={loading && !initialRenderComplete}
    data-testid="pdf-pages"
    role="application"
    tabindex="-1"
    aria-label="PDF pages and annotation surface"
    onpointerdown={handlePointerDown}
    onpointerup={handlePointerUp}
    onclick={handlePdfPagesClick}
    onkeydown={handlePdfPagesKeydown}
  ></div>
  {#if initialRenderComplete}
    <ScrollPositionOverlay
      scrollElement={container}
      testId="pdf-scroll-position-overlay"
      getDetailLabel={currentPdfPageLabel}
    />
  {/if}
  {#if selectionAction && !annotationMenu}
    <button
      type="button"
      class="pdf-selection-action"
      data-testid="floating-text-annotation"
      style:left={`${selectionAction.x}px`}
      style:top={`${selectionAction.y}px`}
      onpointerdown={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onclick={openSelectionAnnotationDraft}
    >
      Annotate
    </button>
  {/if}
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
      <div
        class="pdf-annotation-menu-header"
        data-testid="pdf-annotation-menu-header"
        role="group"
        aria-label="Draggable PDF annotation header"
        onpointerdown={startAnnotationMenuDrag}
        onpointermove={dragAnnotationMenu}
        onpointerup={endAnnotationMenuDrag}
        onpointercancel={endAnnotationMenuDrag}
      >
        PDF annotation
      </div>
      <label class="pdf-annotation-field">
        Comment
        <textarea
          data-testid="pdf-annotation-comment"
          bind:value={annotationDraftComment}
          rows="3"
          disabled={saving}
        ></textarea>
      </label>
      <label class="pdf-annotation-checkbox">
        <input
          type="checkbox"
          aria-label="Add annotation to daily log"
          bind:checked={annotationAddToLog}
          disabled={saving}
        />
        <span>Add to daily log</span>
      </label>
      <div class="annotation-menu-actions">
        <button
          type="button"
          data-testid="pdf-annotation-save"
          onclick={() => void saveSelectedAnnotationComment()}
          disabled={saving}
        >
          {saving ? "Saving" : "Save"}
        </button>
        <button
          type="button"
          class="danger"
          data-testid="pdf-annotation-delete"
          onclick={deleteSelectedAnnotation}
          disabled={saving}
        >
          Delete
        </button>
        <button
          type="button"
          data-testid="pdf-annotation-cancel"
          onclick={hideAnnotationMenu}
          disabled={saving}
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
    position: relative;
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
    box-sizing: border-box;
    display: block;
    flex: 0 0 auto;
    position: relative;
    z-index: 2;
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

  .pdf-loading-overlay {
    position: absolute;
    z-index: 20;
    top: calc(32px + var(--space-3, 12px));
    right: var(--space-4, 16px);
    margin: 0;
    padding: var(--space-2, 8px) var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 999px;
    background: color-mix(in srgb, var(--surface, var(--bg)) 92%, transparent);
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.25);
    pointer-events: none;
  }

  .notice.error {
    color: #ffb4b4;
  }

  .pdf-pages {
    display: flex;
    flex: 1 1 0;
    position: relative;
    z-index: 1;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-5, 24px);
    min-height: 0;
    padding: var(--space-4, 16px);
    overflow: auto;
  }

  .pdf-pages.initial-rendering {
    visibility: hidden;
  }

  .pdf-annotation-menu {
    position: fixed;
    z-index: 50;
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.3);
  }

  .pdf-selection-action {
    position: fixed;
    z-index: 45;
    transform: translate(-50%, 0);
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--accent);
    border-radius: 999px;
    color: var(--bg);
    background: var(--accent);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.24);
    cursor: pointer;
  }

  .pdf-annotation-menu {
    box-sizing: border-box;
    width: min(320px, calc(100vw - 32px));
    max-height: min(420px, calc(100vh - 32px));
    overflow: auto;
    padding: var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text);
    background: var(--surface, var(--bg));
  }

  .pdf-annotation-menu-header {
    margin: calc(var(--space-1, 4px) * -1) 0 var(--space-2, 8px);
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: grab;
    touch-action: none;
    user-select: none;
  }

  .pdf-annotation-menu label {
    display: grid;
    gap: var(--space-2, 8px);
    color: var(--text-muted);
    font-size: 13px;
  }

  .pdf-annotation-checkbox {
    grid-template-columns: auto 1fr;
    align-items: center;
    margin-top: var(--space-3, 12px);
  }

  .pdf-annotation-menu textarea:disabled,
  .pdf-annotation-checkbox input:disabled,
  .annotation-menu-actions button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
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
