// @vitest-environment jsdom
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** @type {EditorView[]} */
const views = [];

/** @type {import("vitest").Mock} */
let apiClient;

/**
 * @typedef {Window & typeof globalThis & {
 *   __pkmWikilinkFocusInstalled?: boolean,
 *   __pkmNav?: { gotoNote: import("vitest").Mock },
 *   __pkmPreview?: { show: import("vitest").Mock, hide: import("vitest").Mock }
 * }} PkmTestWindow
 */

function pkmWindow() {
  return /** @type {PkmTestWindow} */ (window);
}

beforeEach(() => {
  vi.useFakeTimers();
  apiClient = vi.fn();
  vi.stubGlobal(
    "requestAnimationFrame",
    (/** @type {FrameRequestCallback} */ callback) =>
      Number(setTimeout(() => callback(performance.now()), 0)),
  );
  vi.stubGlobal("cancelAnimationFrame", (/** @type {number} */ id) =>
    clearTimeout(id),
  );
  window.history.pushState({}, "", "/main/notes/current");
  delete pkmWindow().__pkmWikilinkFocusInstalled;
  delete pkmWindow().__pkmNav;
  delete pkmWindow().__pkmPreview;
});

afterEach(() => {
  for (const view of views.splice(0)) view.destroy();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.resetModules();
  vi.doUnmock("../api/client.js");
  document.body.innerHTML = "";
});

async function loadModule() {
  vi.resetModules();
  vi.doMock("../api/client.js", () => ({ apiClient }));
  return import("./wikilink-widget.js");
}

/**
 * @param {string} doc
 * @param {import("@codemirror/state").Extension[]} extensions
 * @param {number} [selection]
 */
function createView(doc, extensions, selection = 0) {
  const parent = document.createElement("div");
  document.body.appendChild(parent);
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc,
      selection: { anchor: selection },
      extensions,
    }),
  });
  views.push(view);
  return view;
}

async function flushMicrotasks() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("wikilink resolver", () => {
  it("batches synchronous title lookups and reuses cached note titles", async () => {
    apiClient.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ alpha: "Alpha Note", beta: "Beta Note" }),
    });
    const { wikilinkResolver } = await loadModule();

    const alpha = wikilinkResolver.resolve("main", "alpha");
    const beta = wikilinkResolver.resolve("main", "beta");
    await flushMicrotasks();

    await expect(Promise.all([alpha, beta])).resolves.toEqual([
      "Alpha Note",
      "Beta Note",
    ]);
    expect(apiClient).toHaveBeenCalledTimes(1);
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/main/notes/batch-titles",
      {
        method: "POST",
        body: JSON.stringify({ ids: ["alpha", "beta"] }),
      },
    );

    await expect(wikilinkResolver.resolve("main", "alpha")).resolves.toBe(
      "Alpha Note",
    );
    expect(apiClient).toHaveBeenCalledTimes(1);
  });

  it("invalidates title cache on focus and retries after server failures", async () => {
    apiClient
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ alpha: "Old Title" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ alpha: "Fresh Title" }),
      })
      .mockResolvedValueOnce({ ok: false, status: 500 })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ broken: "Recovered" }),
      });
    const { wikilinkResolver } = await loadModule();

    const first = wikilinkResolver.resolve("main", "alpha");
    await flushMicrotasks();
    await expect(first).resolves.toBe("Old Title");

    window.dispatchEvent(new Event("focus"));
    const fresh = wikilinkResolver.resolve("main", "alpha");
    await flushMicrotasks();
    await expect(fresh).resolves.toBe("Fresh Title");

    const broken = wikilinkResolver.resolve("main", "broken");
    await flushMicrotasks();
    await expect(broken).rejects.toThrow("batch-titles 500");

    const recovered = wikilinkResolver.resolve("main", "broken");
    await flushMicrotasks();
    await expect(recovered).resolves.toBe("Recovered");
    expect(apiClient).toHaveBeenCalledTimes(4);
  });
});

describe("wikilink widget", () => {
  it("keeps active-line wikilinks editable and renders inactive resolved links as navigation targets", async () => {
    apiClient.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ alpha: "Alpha Note" }),
    });
    const { wikilinkWidget, wikilinkWidgetTheme } = await loadModule();
    pkmWindow().__pkmNav = { gotoNote: vi.fn() };
    pkmWindow().__pkmPreview = { show: vi.fn(), hide: vi.fn() };

    const view = createView("active [[raw]]\nsee [[alpha]]\n", [
      wikilinkWidget,
      wikilinkWidgetTheme,
    ]);

    expect(view.dom.textContent).toContain("active [[raw]]");
    expect(view.dom.querySelector('[data-wikilink-id="raw"]')).toBeNull();
    expect(view.dom.querySelector(".cm-wikilink-faint")?.textContent).toBe(
      "[[alpha]]",
    );

    await flushMicrotasks();
    await vi.runOnlyPendingTimersAsync();
    await flushMicrotasks();

    const resolved = view.dom.querySelector(".cm-wikilink-resolved");
    expect(resolved?.textContent).toBe("Alpha Note");

    resolved?.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true }),
    );
    expect(pkmWindow().__pkmNav?.gotoNote).toHaveBeenCalledWith("alpha");

    resolved?.dispatchEvent(
      new MouseEvent("mouseenter", {
        bubbles: true,
        clientX: 12,
        clientY: 34,
      }),
    );
    await vi.advanceTimersByTimeAsync(199);
    expect(pkmWindow().__pkmPreview?.show).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(pkmWindow().__pkmPreview?.show).toHaveBeenCalledWith({
      id: "alpha",
      title: "Alpha Note",
      x: 12,
      y: 34,
    });

    resolved?.dispatchEvent(
      new MouseEvent("mouseleave", { bubbles: true, cancelable: true }),
    );
    expect(pkmWindow().__pkmPreview?.hide).toHaveBeenCalledTimes(1);
  });

  it("shows unresolved wikilinks as faint raw text when the batch lookup fails", async () => {
    apiClient.mockRejectedValue(new Error("daemon down"));
    const { wikilinkWidget } = await loadModule();

    const view = createView("active\nmissing [[ghost]]\n", [wikilinkWidget]);

    await flushMicrotasks();
    await vi.runOnlyPendingTimersAsync();
    await flushMicrotasks();

    const unresolved = view.dom.querySelector('[data-wikilink-id="ghost"]');
    expect(unresolved?.classList.contains("cm-wikilink-faint")).toBe(true);
    expect(unresolved?.textContent).toBe("[[ghost]]");
  });

  it("resolves wikilinks whose ids contain literal brackets", async () => {
    apiClient.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        "2026-04-14-[주식분석]-두산에너빌리티": "두산에너빌리티",
      }),
    });
    const { wikilinkWidget, wikilinkWidgetTheme } = await loadModule();

    const view = createView(
      "active\nsee [[2026-04-14-[주식분석]-두산에너빌리티]]\n",
      [wikilinkWidget, wikilinkWidgetTheme],
    );

    await flushMicrotasks();
    await vi.runOnlyPendingTimersAsync();
    await flushMicrotasks();

    const resolved = view.dom.querySelector(".cm-wikilink-resolved");
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/main/notes/batch-titles",
      {
        method: "POST",
        body: JSON.stringify({
          ids: ["2026-04-14-[주식분석]-두산에너빌리티"],
        }),
      },
    );
    expect(resolved?.textContent).toBe("두산에너빌리티");
  });
});
