import { test, expect } from "@playwright/test";
import {
  expectCommandPaletteFocused,
  loginAndFindSearchableNote,
  loginAndFindVault,
} from "./helpers/pkm";

test.describe("command palette and shell navigation", () => {
  test.describe.configure({ mode: "serial" });

  test("opens command palette from button and keyboard", async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await expect(
      page.getByRole("button", { name: "Open command palette" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Open command palette" }).click();
    await expectCommandPaletteFocused(page);

    await page.locator(".cmdk-input").press("Escape");
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]'),
    ).toBeHidden();

    await page.keyboard.press("Control+K");
    await expectCommandPaletteFocused(page);

    await page.locator(".cmdk-input").press("Escape");
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]'),
    ).toBeHidden();

    await page.keyboard.press("Meta+K");
    await expectCommandPaletteFocused(page);
  });

  test("sidebar app nav avoids note-list fetches and missing routes", async ({
    page,
  }) => {
    const vaultName = await loginAndFindVault(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await expect(
      page.getByRole("button", { name: "Open navigation drawer" }),
    ).toBeVisible();

    const noteListRequests: string[] = [];
    page.on("request", (request) => {
      const url = request.url();
      if (/\/api\/v1\/vault\/[^/]+\/notes(?:$|\?)/.test(url)) {
        noteListRequests.push(url);
      }
    });

    await page.getByRole("button", { name: "Open navigation drawer" }).click();

    await expect(
      page.locator('aside[aria-label="App navigation"]'),
    ).toHaveAttribute("aria-hidden", "false");
    await expect(
      page.getByRole("navigation", { name: "Vault sections" }),
    ).toBeVisible();
    for (const label of [
      "Notes",
      "Search",
      "Tags",
      "Graph",
      "Ask",
      "Logger",
      "Workflows",
      "Daily",
      "Configs",
    ]) {
      await expect(
        page.getByRole("button", { name: new RegExp(label) }),
      ).toBeVisible();
    }
    expect(noteListRequests).toEqual([]);

    await page.getByRole("button", { name: /Search/ }).click();
    await expectCommandPaletteFocused(page);
    await page.locator(".cmdk-input").press("Escape");
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]'),
    ).toBeHidden();
    await expect(page.locator(".cmdk-backdrop")).toBeHidden();
    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await expect(
      page.locator('aside[aria-label="App navigation"]'),
    ).toHaveAttribute("aria-hidden", "false");

    const tags = page.getByRole("button", { name: "Tags" });
    const graph = page.getByRole("button", { name: "Graph" });
    const vaultPath = vaultPathPattern(vaultName);
    await expect(graph).toBeVisible();

    await tags.click();
    await expect(page).toHaveURL(new RegExp(`/${vaultPath}/tags$`));

    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await page
      .locator('button[aria-label="Graph"]')
      .evaluate((el) => (el as HTMLElement).click());
    await expect(page).toHaveURL(new RegExp(`/${vaultPath}/graph$`));

    await page.getByRole("button", { name: "Open navigation drawer" }).click();
    await expect(
      page.locator('aside[aria-label="App navigation"]'),
    ).toHaveAttribute("aria-hidden", "false");
    await page.getByRole("button", { name: "Ask" }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultPath}/ask$`));
  });

  test("searches notes from the command palette using backend search results", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const { vaultName, query } = await loginAndFindSearchableNote(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState("networkidle").catch(() => {});

    await page.getByRole("button", { name: "Open command palette" }).click();
    await expectCommandPaletteFocused(page);

    const searchResponse = page.waitForResponse(
      (response) => {
        const url = new URL(response.url());
        return (
          decodeURIComponent(url.pathname) ===
            `/api/v1/vault/${vaultName}/search` &&
          url.searchParams.get("q") === query
        );
      },
      { timeout: 30_000 },
    );
    await page.locator(".cmdk-input").fill(query);
    const response = await searchResponse;
    expect(response.ok()).toBe(true);
    const payload = (await response.json()) as { results?: unknown[] };
    expect(payload.results?.length ?? 0).toBeGreaterThan(0);

    const result = page.locator('.cmdk-row[data-kind="note"]').first();
    await expect(result).toBeVisible({ timeout: 15_000 });
    await result.click();

    await expect(page).toHaveURL(
      new RegExp(`/${escapeRegExp(vaultName)}/notes/`),
    );
  });

  test("falls back to notes list when command palette search index is unavailable", async ({
    page,
  }) => {
    const vaultName = "alpha";
    const notes = [
      {
        note_id: "fallback-research-note",
        title: "Fallback Research Note",
        path: "notes/fallback-research-note.md",
        description: "Searchable note from the notes list fallback.",
        tags: ["research"],
        created_at: "2026-05-11",
        modified_at: "2026-05-11T12:00:00Z",
      },
      {
        note_id: "unrelated",
        title: "Unrelated",
        path: "notes/unrelated.md",
        description: "Different note.",
        tags: [],
        created_at: "2026-05-10",
        modified_at: "2026-05-10T12:00:00Z",
      },
    ];

    await page.route("**/api/v1/vaults", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([{ name: vaultName, path: "/tmp/alpha" }]),
      });
    });
    await page.route(`**/api/v1/vault/${vaultName}/notes`, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(notes),
      });
    });
    await page.route(`**/api/v1/vault/${vaultName}/search**`, async (route) => {
      await route.fulfill({
        status: 404,
        body: "Search index not found",
      });
    });

    await page.goto(`/${vaultName}`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.getByRole("button", { name: "Open command palette" }).click();
    await expectCommandPaletteFocused(page);

    await page.locator(".cmdk-input").fill("research");
    await expect(
      page.getByRole("option", { name: /Fallback Research Note/ }),
    ).toBeVisible();
    await expect(page.getByRole("option", { name: /Unrelated/ })).toHaveCount(
      0,
    );
  });

  test("command palette exposes every routed sidebar page", async ({
    page,
  }) => {
    const vaultName = await loginAndFindVault(page);
    const vaultPath = vaultPathPattern(vaultName);
    const navCommands = [
      { query: "notes", label: /^Open notes\b/, path: `/${vaultPath}$` },
      { query: "tags", label: /^Open tags\b/, path: `/${vaultPath}/tags$` },
      { query: "graph", label: /^Open graph\b/, path: `/${vaultPath}/graph$` },
      { query: "ask", label: /^Open ask\b/, path: `/${vaultPath}/ask$` },
      {
        query: "logger",
        label: /^Open logger\b/,
        path: `/${vaultPath}/logger$`,
      },
      {
        query: "workflow",
        label: /^Open workflows\b/,
        path: `/${vaultPath}/workflows$`,
      },
      { query: "daily", label: /^Open daily\b/, path: `/${vaultPath}/daily$` },
      {
        query: "configs",
        label: /^Open configs\b/,
        path: `/${vaultPath}/configs$`,
      },
    ];

    for (const command of navCommands) {
      await page.goto(`/${encodeURIComponent(vaultName)}`);
      await page.waitForLoadState("networkidle").catch(() => {});
      await page.getByRole("button", { name: "Open command palette" }).click();
      await expectCommandPaletteFocused(page);
      await page.locator(".cmdk-input").fill(command.query);
      await page.getByRole("option", { name: command.label }).click();
      await expect(page).toHaveURL(new RegExp(command.path));
    }
  });
});

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function vaultPathPattern(value: string) {
  const decoded = escapeRegExp(value);
  const encoded = escapeRegExp(encodeURIComponent(value));
  return decoded === encoded ? decoded : `(?:${decoded}|${encoded})`;
}
