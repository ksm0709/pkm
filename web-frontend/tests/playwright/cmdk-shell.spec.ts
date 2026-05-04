import { test, expect } from '@playwright/test';
import {
  expectCommandPaletteFocused,
  loginAndFindSearchableNote,
  loginAndFindVault
} from './helpers/pkm';

test.describe('command palette and shell navigation', () => {
  test.describe.configure({ mode: 'serial' });

  test('opens command palette from button and keyboard', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await expect(page.getByRole('button', { name: 'Open command palette' })).toBeVisible();

    await page.getByRole('button', { name: 'Open command palette' }).click();
    await expectCommandPaletteFocused(page);

    await page.locator('.cmdk-input').press('Escape');
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]')
    ).toBeHidden();

    await page.keyboard.press('Control+K');
    await expectCommandPaletteFocused(page);

    await page.locator('.cmdk-input').press('Escape');
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]')
    ).toBeHidden();

    await page.keyboard.press('Meta+K');
    await expectCommandPaletteFocused(page);
  });

  test('sidebar app nav avoids note-list fetches and missing routes', async ({
    page
  }) => {
    const vaultName = await loginAndFindVault(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await expect(page.getByRole('button', { name: 'Open navigation drawer' })).toBeVisible();

    const noteListRequests: string[] = [];
    page.on('request', (request) => {
      const url = request.url();
      if (/\/api\/v1\/vault\/[^/]+\/notes(?:$|\?)/.test(url)) {
        noteListRequests.push(url);
      }
    });

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();

    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'false'
    );
    await expect(page.getByRole('navigation', { name: 'Vault sections' })).toBeVisible();
    for (const label of ['Notes', 'Search', 'Tags', 'Graph', 'Ask', 'Logger', 'Daily']) {
      await expect(page.getByRole('button', { name: new RegExp(label) })).toBeVisible();
    }
    expect(noteListRequests).toEqual([]);

    await page.getByRole('button', { name: /Search/ }).click();
    await expectCommandPaletteFocused(page);
    await page.locator('.cmdk-input').press('Escape');
    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'false'
    );

    const before = page.url();
    const tags = page.locator('[role="button"][aria-label="Tags"]');
    const graph = page.getByRole('button', { name: 'Graph' });
    await expect(tags).toHaveAttribute('aria-disabled', 'true');
    await expect(graph).toBeVisible();

    await tags.click({ force: true });
    expect(page.url()).toBe(before);
    await tags.focus();
    await page.keyboard.press('Enter');
    expect(page.url()).toBe(before);

    await graph.click();
    const vaultPath = vaultPathPattern(vaultName);
    await expect(page).toHaveURL(new RegExp(`/${vaultPath}/graph$`));

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'false'
    );
    await page.getByRole('button', { name: 'Ask' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultPath}/ask$`));
  });

  test('searches notes from the command palette using backend search results', async ({
    page
  }) => {
    test.setTimeout(60_000);
    const { vaultName, query } = await loginAndFindSearchableNote(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.getByRole('button', { name: 'Open command palette' }).click();
    await expectCommandPaletteFocused(page);

    const searchResponse = page.waitForResponse(
      (response) => {
        const url = new URL(response.url());
        return (
          decodeURIComponent(url.pathname) === `/api/v1/vault/${vaultName}/search` &&
          url.searchParams.get('q') === query
        );
      },
      { timeout: 30_000 }
    );
    await page.locator('.cmdk-input').fill(query);
    const response = await searchResponse;
    expect(response.ok()).toBe(true);
    const payload = (await response.json()) as { results?: unknown[] };
    expect(payload.results?.length ?? 0).toBeGreaterThan(0);

    const result = page.locator('.cmdk-row[data-kind="note"]').first();
    await expect(result).toBeVisible({ timeout: 15_000 });
    await result.click();

    await expect(page).toHaveURL(new RegExp(`/${escapeRegExp(vaultName)}/notes/`));
  });
});

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function vaultPathPattern(value: string) {
  const decoded = escapeRegExp(value);
  const encoded = escapeRegExp(encodeURIComponent(value));
  return decoded === encoded ? decoded : `(?:${decoded}|${encoded})`;
}
