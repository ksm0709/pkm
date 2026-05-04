import { test, expect } from '@playwright/test';
import { loginAndFindVault } from './helpers/pkm';

type GraphNode = {
  id: string;
  title?: string;
  type?: 'note' | 'tag' | 'note_or_unresolved';
  description?: string;
  community?: string;
  cluster?: string;
};

type GraphPayload = {
  nodes: GraphNode[];
  links: Array<{ source: string; target: string; type?: string }>;
};

function graphPayload(): GraphPayload {
  return {
    nodes: [
      { id: 'alpha', title: 'Alpha', type: 'note', description: 'note alpha' },
      { id: 'beta', title: 'Beta', type: 'note', description: 'note beta' },
      { id: 'work', title: 'work', type: 'tag', description: 'tag work' },
      { id: 'ghost', title: 'ghost', type: 'note_or_unresolved', description: '' }
    ],
    links: [
      { source: 'alpha', target: 'beta', type: 'wikilink' },
      { source: 'alpha', target: 'work', type: 'has_tag' },
      { source: 'beta', target: 'ghost', type: 'semantic_similar' }
    ]
  };
}

test.describe('vault graph page', () => {
  test('drawer graph item is enabled and routes', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    const graph = page.locator('[role="button"][aria-label="Graph"]');
    await expect(graph).toHaveAttribute('aria-disabled', 'false');
    await graph.click();
    await expect(page).toHaveURL(new RegExp(`/${escapeRegExp(vaultName)}/graph$`));
  });

  test('CmdK graph command routes to graph page', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await page.goto(`/${encodeURIComponent(vaultName)}`);
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.getByRole('button', { name: 'Open command palette' }).click();
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]')
    ).toBeVisible();
    await page.locator('.cmdk-input').fill('graph');
    await page.getByRole('option', { name: /Open graph/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${escapeRegExp(vaultName)}/graph$`));
  });

  test('renders graph nodes and edges from /api/v1/vault/{name}/graph', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);

    await page.route('**/api/v1/vault/*/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(graphPayload())
      });
    });

    await page.route('**/api/v1/vault/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/v1/vaults') || url.includes(`/api/v1/vault/${vaultName}/graph`)) {
        await route.continue();
        return;
      }
      await route.fulfill({ status: 404, body: 'not found' });
    });

    await page.goto(`/${encodeURIComponent(vaultName)}/graph`);
    await expect(page.getByTestId('graph-summary')).toHaveText('4 nodes · 3 edges');
    await expect(page.getByTestId('graph-node')).toHaveCount(4);
    expect(await page.getByTestId('graph-edge').count()).toBeGreaterThan(0);
    await expect(page.getByText('Alpha')).toBeVisible();
    await expect(page.getByText('work')).toBeVisible();
    await expect(page.getByText('ghost')).toBeVisible();
  });

  test('supports visualization mode switches and filters', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);

    await page.route('**/api/v1/vault/*/graph', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(graphPayload())
      });
    });

    await page.goto(`/${encodeURIComponent(vaultName)}/graph`);
    await page.getByRole('button', { name: 'Cluster' }).click();
    await expect(page.getByTestId('graph-summary')).toHaveText('4 nodes · 3 edges');
    await page.getByRole('button', { name: 'List' }).click();
    await expect(page.getByTestId('graph-summary')).toHaveCount(0);
    await expect(page.getByRole('rowheader')).toHaveCount(0);
    await page.getByRole('listbox', { name: 'Node type filter' }).selectOption('tag');
    await expect(page.getByRole('article')).toHaveCount(1);

    await page.getByRole('listbox', { name: 'Edge type filter' }).selectOption('semantic_similar');
    await expect(page.getByText('3 edges')).not.toBeVisible();
    await expect(page.getByText('No matches.')).toBeVisible();
  });

  test('shows pkm index guidance when graph is missing', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await page.route('**/api/v1/vault/*/graph', (route) => route.fulfill({ status: 404, body: 'not found' }));
    await page.goto(`/${encodeURIComponent(vaultName)}/graph`);
    await expect(page.getByText(/pkm index/i)).toBeVisible();
    await expect(page.getByText(/run `pkm index`/i)).toBeVisible();
  });
});

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&');
}
