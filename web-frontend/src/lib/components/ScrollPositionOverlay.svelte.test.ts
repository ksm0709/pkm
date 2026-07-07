// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import ScrollPositionOverlay from "./ScrollPositionOverlay.svelte";

function setScrollMetrics(
  element: HTMLElement,
  metrics: { scrollTop: number; scrollHeight: number; clientHeight: number },
) {
  Object.defineProperty(element, "scrollTop", {
    configurable: true,
    writable: true,
    value: metrics.scrollTop,
  });
  Object.defineProperty(element, "scrollHeight", {
    configurable: true,
    value: metrics.scrollHeight,
  });
  Object.defineProperty(element, "clientHeight", {
    configurable: true,
    value: metrics.clientHeight,
  });
}

async function flush() {
  await Promise.resolve();
  await tick();
}

describe("ScrollPositionOverlay", () => {
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("shows scroll progress while the scroll element is moving and hides after idle", async () => {
    vi.useFakeTimers();
    const scrollElement = document.createElement("div");
    setScrollMetrics(scrollElement, {
      scrollTop: 250,
      scrollHeight: 1000,
      clientHeight: 500,
    });
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(ScrollPositionOverlay, {
      target,
      props: {
        scrollElement,
        testId: "scroll-position-overlay",
        idleMs: 500,
      },
    });

    await flush();
    scrollElement.dispatchEvent(new Event("scroll"));
    await flush();

    const overlay = target.querySelector(
      '[data-testid="scroll-position-overlay"]',
    );
    expect(overlay).not.toBeNull();
    expect(overlay?.textContent).toContain("50%");

    await vi.advanceTimersByTimeAsync(499);
    expect(
      target.querySelector('[data-testid="scroll-position-overlay"]'),
    ).not.toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    await flush();
    expect(
      target.querySelector('[data-testid="scroll-position-overlay"]'),
    ).toBeNull();

    unmount(component);
  });

  it("does not show for non-scrollable content", async () => {
    vi.useFakeTimers();
    const scrollElement = document.createElement("div");
    setScrollMetrics(scrollElement, {
      scrollTop: 0,
      scrollHeight: 400,
      clientHeight: 500,
    });
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(ScrollPositionOverlay, {
      target,
      props: { scrollElement, testId: "scroll-position-overlay" },
    });

    await flush();
    scrollElement.dispatchEvent(new Event("scroll"));
    await flush();

    expect(
      target.querySelector('[data-testid="scroll-position-overlay"]'),
    ).toBeNull();

    unmount(component);
  });

  it("combines progress with a view-specific detail label", async () => {
    vi.useFakeTimers();
    const scrollElement = document.createElement("div");
    setScrollMetrics(scrollElement, {
      scrollTop: 125,
      scrollHeight: 1000,
      clientHeight: 500,
    });
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(ScrollPositionOverlay, {
      target,
      props: {
        scrollElement,
        testId: "scroll-position-overlay",
        getDetailLabel: () => "Page 2 / 10",
      },
    });

    await flush();
    scrollElement.dispatchEvent(new Event("scroll"));
    await flush();

    const overlay = target.querySelector(
      '[data-testid="scroll-position-overlay"]',
    );
    expect(overlay).not.toBeNull();
    expect(overlay?.textContent).toContain("25% · Page 2 / 10");

    unmount(component);
  });
});
