import type { Page } from "@playwright/test";

/**
 * Inject `data-theme` onto <html> before any page script runs so the SPA
 * picks the correct theme even on cold-load. Resolves the theme from the
 * Playwright project's `colorScheme` use-option via the project name.
 */
export async function applyTheme(
  page: Page,
  theme: "light" | "dark",
): Promise<void> {
  await page.addInitScript((mode: string) => {
    document.documentElement.dataset.theme = mode;
  }, theme);
}

/**
 * Derive theme from project name (chromium-light → light, chromium-dark → dark).
 * Falls back to 'light' for unknown projects.
 */
export function themeFromProject(projectName: string): "light" | "dark" {
  return projectName.includes("dark") ? "dark" : "light";
}
