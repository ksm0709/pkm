import { expect, type Page, type Route, test } from '@playwright/test';

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
  test('renders graph API data with modes, filters, and note navigation', async ({ page }) => {
    const graphRequests: string[] = [];
    await mockGraphApi(page, async (route) => {
      graphRequests.push(route.request().url());
      await json(route, graphFixture);
    });

    await page.route('**/api/v1/vault/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/v1/vaults') || url.includes(`/api/v1/vault/${vaultName}/graph`)) {
        await route.continue();
        return;
      }
      await route.fulfill({ status: 404, body: 'not found' });
    });

    await expect(page.locator('[data-testid="graph-summary"]')).toHaveText('4 nodes · 3 edges');
    expect(graphRequests.some((url) => new URL(url).pathname === `/api/v1/vault/${vaultName}/graph`)).toBe(true);

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
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Mode: Cluster/);
    await expect(page.getByText(/planning/)).toBeVisible();

    await page.getByRole('button', { name: 'Degree' }).click();
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Mode: Degree/);
    await expect(page.locator('[data-testid="graph-row"]').first()).toContainText('Project Plan');

    await page.getByLabel('Node type filter').selectOption('tag');
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]')).toContainText('#pkm');
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(0);

    await page.getByLabel('Node type filter').selectOption('all');
    await page.getByLabel('Edge type filter').selectOption('wikilink');
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(2);

    await page.getByRole('button', { name: 'List' }).click();
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Mode: List/);
    await expect(page.getByRole('table', { name: 'Graph nodes' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Open note Project Plan' })).toHaveAttribute(
      'href',
      `/${vaultName}/notes/project-plan`
    );

    await page.getByRole('button', { name: 'Radial' }).click();
    await page.getByRole('button', { name: 'Open note Project Plan' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/project-plan$`));
  });

  test('accepts edges arrays and object-like references', async ({ page }) => {
    await mockGraphApi(page, async (route) => json(route, edgesFixture));

    await page.goto(`/${vaultName}/graph`);

    await expect(page.locator('[data-testid="graph-summary"]')).toHaveText('2 nodes · 1 edge');
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(2);
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(1);
    await expect(page.getByText('Alpha Note')).toBeVisible();
  });

  test('missing graph response explains how to create the graph index', async ({ page }) => {
    await mockGraphApi(page, async (route) => route.fulfill({ status: 404, body: 'not found' }));

    await page.goto(`/${vaultName}/graph`);

    await expect(page.getByText('Graph index not found.')).toBeVisible();
    await expect(page.getByText(/pkm index/)).toBeVisible();
  });

  test('large graphs cap only the visual overview while keeping the list browsable', async ({ page }) => {
    const nodes = Array.from({ length: 86 }, (_, index) => ({
      id: `note-${String(index + 1).padStart(2, '0')}`,
      title: `Note ${index + 1}`,
      type: 'note'
    }));
    const links = nodes.slice(1).map((node, index) => ({
      source: nodes[index].id,
      target: node.id,
      type: 'wikilink'
    }));
    await mockGraphApi(page, async (route) => json(route, { nodes, links }));

    await page.goto(`/${vaultName}/graph`);

    await expect(page.locator('[data-testid="graph-summary"]')).toHaveText('86 nodes · 85 edges');
    await expect(page.locator('.cap-status')).toHaveText(/Rendering first 80 of 86/);
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(80);
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(86);
  });
});

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\\]\\]/g, '\\$&');
}
