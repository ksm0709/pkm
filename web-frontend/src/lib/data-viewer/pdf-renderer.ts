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

export async function renderPdfIntoContainer(
  container: HTMLElement,
  data: ArrayBuffer,
  options: PdfRenderOptions = {},
): Promise<PdfRenderCleanup> {
  installPdfJsCollectionPolyfills();
  const [{ default: workerSrc }, pdfjs] = await Promise.all([
    import("pdfjs-dist/legacy/build/pdf.worker.mjs?url"),
    import("pdfjs-dist/legacy/build/pdf.mjs"),
  ]);
  setWorkerSrc(pdfjs, workerSrc);

  clearElement(container);
  const loadingTask = pdfjs.getDocument({ data });
  const pdf = await loadingTask.promise;
  const scale = options.scale ?? 1.25;
  const renderTasks: Array<{ cancel: () => void }> = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const viewport = page.getViewport({ scale });
    const pageElement = document.createElement("section");
    pageElement.className = "pdf-page";
    pageElement.dataset.pageNumber = String(pageNumber);
    pageElement.style.position = "relative";
    pageElement.style.width = `${viewport.width}px`;
    pageElement.style.height = `${viewport.height}px`;

    const canvas = document.createElement("canvas");
    canvas.className = "pdf-page-canvas";
    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);
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

    container.appendChild(pageElement);

    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context is not available");
    const renderTask = page.render({
      canvas,
      canvasContext: context,
      viewport,
    });
    renderTasks.push(renderTask);
    await renderTask.promise;

    const textContent = await page.getTextContent();
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

  return () => {
    for (const task of renderTasks) task.cancel();
    void (pdf as { destroy?: () => Promise<void> | void }).destroy?.();
    clearElement(container);
  };
}
