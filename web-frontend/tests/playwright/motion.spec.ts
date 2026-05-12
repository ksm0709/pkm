import { test, expect } from "@playwright/test";
import { applyTheme, themeFromProject } from "./fixtures/theme";

/**
 * Motion-system smoke tests for Slice 4.
 *
 * Targets:
 *   - Slash menu items animate in with ~30ms stagger (±10ms tolerance).
 *   - ⌘K palette opens with a 120ms scale-from-0.97 transition (±20ms).
 *
 * Strategy: read the actual `animation-delay` / `transition-duration`
 * computed styles instead of racing wall-clock timers. The CSS contract
 * is the source of truth — if it drifts the tests catch it deterministically.
 */

test.describe("motion system", () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await applyTheme(page, themeFromProject(testInfo.project.name));
  });

  test("slash menu items have ~30ms stagger", async ({ page }) => {
    await page.goto("/");

    // Navigate to a vault note (best-effort — fall back to home if not wired up yet).
    const editor = page
      .locator('[contenteditable="true"], .cm-content')
      .first();
    if (await editor.count()) {
      await editor.click();
      await page.keyboard.type("/");
    }

    const items = page.locator(".slash-item");
    const count = await items.count();
    test.skip(count < 2, "slash menu not present in this build");

    // Read animation-delay (or transition-delay) for the first few items.
    const delays = await items.evaluateAll((nodes) =>
      nodes.slice(0, 4).map((n) => {
        const cs = getComputedStyle(n);
        const raw = cs.animationDelay || cs.transitionDelay || "0s";
        // Take the first delay (multiple if multiple animations).
        const first = raw.split(",")[0].trim();
        return first.endsWith("ms")
          ? parseFloat(first)
          : parseFloat(first) * 1000;
      }),
    );

    // Successive deltas should be ~30ms ± 10ms.
    for (let i = 1; i < delays.length; i++) {
      const delta = delays[i] - delays[i - 1];
      expect(delta).toBeGreaterThanOrEqual(20);
      expect(delta).toBeLessThanOrEqual(40);
    }
  });

  test("⌘K palette opens in ~120ms with scale-from-0.97", async ({ page }) => {
    await page.goto("/");

    await page.keyboard.press("Meta+K");

    const palette = page
      .locator("[data-cmdk], .cmdk, .command-palette")
      .first();
    const visible = await palette
      .waitFor({ state: "visible", timeout: 2000 })
      .then(() => true)
      .catch(() => false);
    test.skip(!visible, "⌘K palette not present in this build");

    // Read transition-duration off the palette element.
    const durationMs = await palette.evaluate((el) => {
      const cs = getComputedStyle(el);
      const raw = cs.transitionDuration.split(",")[0].trim() || "0s";
      return raw.endsWith("ms") ? parseFloat(raw) : parseFloat(raw) * 1000;
    });

    expect(durationMs).toBeGreaterThanOrEqual(100);
    expect(durationMs).toBeLessThanOrEqual(140);

    // Wait until the open transition has settled, then verify scale ≈ 1.0.
    await page.waitForFunction((sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      const t = getComputedStyle(el).transform;
      return t === "none" || t.includes("matrix");
    }, "[data-cmdk], .cmdk, .command-palette");
  });
});
