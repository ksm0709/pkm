import { test, expect, type Page } from "@playwright/test";
import { loginAndFindNote } from "./helpers/pkm";

type ThemeMode = "light" | "dark" | "auto-light" | "auto-dark";

test.describe("note contrast", () => {
  for (const mode of [
    "light",
    "dark",
    "auto-light",
    "auto-dark",
  ] as ThemeMode[]) {
    test(`${mode} keeps note and editor surfaces readable`, async ({
      page,
    }) => {
      await prepareTheme(page, mode);
      const { vaultName, noteId } = await loginAndFindNote(page);
      await page.goto(
        `/${encodeURIComponent(vaultName)}/notes/${encodeURIComponent(noteId)}`,
      );

      await expect(page.locator(".note-body.prose")).toBeVisible();
      await assertContrast(page, ".note-body.prose", mode);

      await page.getByRole("button", { name: "Edit" }).click();
      await expect(page.locator(".cm-editor")).toBeVisible();
      await assertContrast(page, ".note-editor", mode);
      await assertContrast(page, ".cm-editor", mode);
    });
  }
});

async function prepareTheme(page: Page, mode: ThemeMode) {
  await page.addInitScript((themeMode: ThemeMode) => {
    if (themeMode === "light" || themeMode === "dark") {
      localStorage.setItem("pkm.theme", themeMode);
      document.documentElement.dataset.theme = themeMode;
    } else {
      localStorage.removeItem("pkm.theme");
      document.documentElement.removeAttribute("data-theme");
    }
  }, mode);
  if (mode === "auto-light") await page.emulateMedia({ colorScheme: "light" });
  if (mode === "auto-dark") await page.emulateMedia({ colorScheme: "dark" });
}

async function assertContrast(page: Page, selector: string, mode: ThemeMode) {
  const metrics = await page
    .locator(selector)
    .first()
    .evaluate((el) => {
      const style = getComputedStyle(el);
      const bg = parseColor(style.backgroundColor);
      const fg = parseColor(style.color);
      const bgLum = luminance(bg);
      const fgLum = luminance(fg);
      const contrast = contrastRatio(bgLum, fgLum);
      return {
        background: style.backgroundColor,
        color: style.color,
        bgLum,
        fgLum,
        contrast,
      };

      function parseColor(value: string): [number, number, number] {
        const match = value.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!match) return [0, 0, 0];
        return [Number(match[1]), Number(match[2]), Number(match[3])];
      }

      function luminance([r, g, b]: [number, number, number]) {
        const channels = [r, g, b].map((channel) => {
          const normalized = channel / 255;
          return normalized <= 0.03928
            ? normalized / 12.92
            : Math.pow((normalized + 0.055) / 1.055, 2.4);
        });
        return (
          0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
        );
      }

      function contrastRatio(a: number, b: number) {
        const lighter = Math.max(a, b);
        const darker = Math.min(a, b);
        return (lighter + 0.05) / (darker + 0.05);
      }
    });

  expect(
    metrics.contrast,
    `${selector} ${mode} contrast`,
  ).toBeGreaterThanOrEqual(4.5);

  if (mode === "dark" || mode === "auto-dark") {
    expect(metrics.bgLum, `${selector} ${mode} dark background`).toBeLessThan(
      0.25,
    );
    expect(metrics.fgLum, `${selector} ${mode} light text`).toBeGreaterThan(
      0.55,
    );
  } else {
    expect(
      metrics.bgLum,
      `${selector} ${mode} light background`,
    ).toBeGreaterThan(0.75);
    expect(metrics.fgLum, `${selector} ${mode} dark text`).toBeLessThan(0.25);
  }
}
