export type PdfRenderCleanup = () => void;

declare global {
  interface Map<K, V> {
    getOrInsertComputed?(key: K, callback: (key: K) => V): V;
    getOrInsert?(key: K, value: V): V;
  }

  interface WeakMap<K extends WeakKey, V> {
    getOrInsertComputed?(key: K, callback: (key: K) => V): V;
    getOrInsert?(key: K, value: V): V;
  }
}

function installPdfJsCollectionPolyfills() {
  if (!Map.prototype.getOrInsertComputed) {
    Object.defineProperty(Map.prototype, "getOrInsertComputed", {
      configurable: true,
      writable: true,
      value: function getOrInsertComputed<K, V>(
        this: Map<K, V>,
        key: K,
        callback: (key: K) => V,
      ) {
        if (this.has(key)) return this.get(key) as V;
        const value = callback(key);
        this.set(key, value);
        return value;
      },
    });
  }
  if (!Map.prototype.getOrInsert) {
    Object.defineProperty(Map.prototype, "getOrInsert", {
      configurable: true,
      writable: true,
      value: function getOrInsert<K, V>(this: Map<K, V>, key: K, value: V) {
        if (this.has(key)) return this.get(key) as V;
        this.set(key, value);
        return value;
      },
    });
  }
  if (!WeakMap.prototype.getOrInsertComputed) {
    Object.defineProperty(WeakMap.prototype, "getOrInsertComputed", {
      configurable: true,
      writable: true,
      value: function getOrInsertComputed<K extends WeakKey, V>(
        this: WeakMap<K, V>,
        key: K,
        callback: (key: K) => V,
      ) {
        if (this.has(key)) return this.get(key) as V;
        const value = callback(key);
        this.set(key, value);
        return value;
      },
    });
  }
  if (!WeakMap.prototype.getOrInsert) {
    Object.defineProperty(WeakMap.prototype, "getOrInsert", {
      configurable: true,
      writable: true,
      value: function getOrInsert<K extends WeakKey, V>(
        this: WeakMap<K, V>,
        key: K,
        value: V,
      ) {
        if (this.has(key)) return this.get(key) as V;
        this.set(key, value);
        return value;
      },
    });
  }
}

export interface PdfRenderOptions {
  scale?: number;
  fitToContainer?: boolean;
  outputScale?: number;
  maxOutputScale?: number;
  signal?: AbortSignal;
  onFirstPageRendered?: () => void;
}

function setWorkerSrc(
  pdfjs: { GlobalWorkerOptions: { workerSrc: string } },
  workerSrc: string,
) {
  if (pdfjs.GlobalWorkerOptions.workerSrc !== workerSrc) {
    pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
  }
}

function clearElement(element: HTMLElement) {
  while (element.firstChild) element.firstChild.remove();
}

function abortError() {
  return new DOMException("PDF render aborted", "AbortError");
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) throw abortError();
}

function resolvedOutputScale(options: PdfRenderOptions) {
  const maxOutputScale = options.maxOutputScale ?? 3;
  const rawScale =
    options.outputScale ??
    (typeof window === "undefined" ? 1 : window.devicePixelRatio || 1);
  return Math.min(Math.max(rawScale, 1), maxOutputScale);
}

function cssPixels(value: string) {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function containerContentSize(container: HTMLElement) {
  const style = window.getComputedStyle(container);
  const width =
    container.clientWidth -
    cssPixels(style.paddingLeft) -
    cssPixels(style.paddingRight);
  const height =
    container.clientHeight -
    cssPixels(style.paddingTop) -
    cssPixels(style.paddingBottom);
  if (width <= 0 || height <= 0) return null;
  return { width, height };
}

function fitScaleForContainer(
  container: HTMLElement,
  pages: Array<{ width: number; height: number }>,
) {
  const size = containerContentSize(container);
  if (!size || !pages.length) return 1;
  const ratios = pages
    .map((page) => Math.min(size.width / page.width, size.height / page.height))
    .filter((ratio) => Number.isFinite(ratio) && ratio > 0);
  if (!ratios.length) return 1;
  return Math.min(...ratios);
}

export async function renderPdfIntoContainer(
  container: HTMLElement,
  data: ArrayBuffer,
  options: PdfRenderOptions = {},
): Promise<PdfRenderCleanup> {
  const signal = options.signal;
  installPdfJsCollectionPolyfills();
  const [{ default: workerSrc }, pdfjs] = await Promise.all([
    import("pdfjs-dist/legacy/build/pdf.worker.mjs?url"),
    import("pdfjs-dist/legacy/build/pdf.mjs"),
  ]);
  setWorkerSrc(pdfjs, workerSrc);

  throwIfAborted(signal);
  clearElement(container);
  const loadingTask = pdfjs.getDocument({ data: data.slice(0) });
  let pdf: any = null;
  const zoomScale = options.scale ?? 1.25;
  const outputScale = resolvedOutputScale(options);
  const renderTasks: Array<{ cancel: () => void }> = [];
  const pageElements: HTMLElement[] = [];
  let firstPageRendered = false;

  function cleanupOwnedRender() {
    for (const task of renderTasks) task.cancel();
    void pdf?.destroy?.();
    for (const pageElement of pageElements) pageElement.remove();
  }

  try {
    pdf = await loadingTask.promise;
    throwIfAborted(signal);

    const pageRecords = [];
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      throwIfAborted(signal);
      const page = await pdf.getPage(pageNumber);
      throwIfAborted(signal);
      const naturalViewport = page.getViewport({ scale: 1 });
      pageRecords.push({ pageNumber, page, naturalViewport });
    }
    const fitScale = options.fitToContainer
      ? fitScaleForContainer(
          container,
          pageRecords.map(({ naturalViewport }) => naturalViewport),
        )
      : 1;
    const scale = fitScale * zoomScale;

    for (const { pageNumber, page } of pageRecords) {
      throwIfAborted(signal);
      const viewport = page.getViewport({ scale });
      const pageElement = document.createElement("section");
      pageElement.className = "pdf-page";
      pageElement.dataset.pageNumber = String(pageNumber);
      pageElement.style.position = "relative";
      pageElement.style.width = `${viewport.width}px`;
      pageElement.style.height = `${viewport.height}px`;

      const canvas = document.createElement("canvas");
      canvas.className = "pdf-page-canvas";
      canvas.width = Math.ceil(viewport.width * outputScale);
      canvas.height = Math.ceil(viewport.height * outputScale);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      pageElement.appendChild(canvas);

      const textLayer = document.createElement("div");
      textLayer.className = "pdf-text-layer";
      textLayer.style.position = "absolute";
      textLayer.style.inset = "0";
      textLayer.style.overflow = "hidden";
      textLayer.style.lineHeight = "1";
      pageElement.appendChild(textLayer);

      throwIfAborted(signal);
      container.appendChild(pageElement);
      pageElements.push(pageElement);

      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas 2D context is not available");
      const renderTask = page.render({
        canvas,
        canvasContext: context,
        viewport,
        transform: [outputScale, 0, 0, outputScale, 0, 0],
      });
      renderTasks.push(renderTask);
      await renderTask.promise;
      throwIfAborted(signal);
      if (!firstPageRendered) {
        firstPageRendered = true;
        options.onFirstPageRendered?.();
      }

      const textContent = await page.getTextContent();
      throwIfAborted(signal);
      for (const item of textContent.items) {
        if (!("str" in item) || !item.str) continue;
        const transform = pdfjs.Util.transform(
          viewport.transform,
          item.transform,
        );
        const span = document.createElement("span");
        span.className = "pdf-text-item";
        span.textContent = item.str;
        span.style.position = "absolute";
        span.style.left = `${transform[4]}px`;
        span.style.top = `${transform[5] - Math.abs(transform[3])}px`;
        span.style.fontSize = `${Math.abs(transform[3])}px`;
        span.style.transformOrigin = "0 0";
        span.style.whiteSpace = "pre";
        span.style.color = "transparent";
        span.style.userSelect = "text";
        span.dataset.pageNumber = String(pageNumber);
        textLayer.appendChild(span);
      }
    }

    return cleanupOwnedRender;
  } catch (error) {
    cleanupOwnedRender();
    throw error;
  }
}
