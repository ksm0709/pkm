import { expect, test, type Page, type Route } from '@playwright/test';

const vaultName = 'alpha';

const graphFixture = {
  nodes: [
    {
      id: 'project-plan',
      title: 'Project Plan',
      type: 'note',
      description: 'Project coordination summary.',
      community: 'planning',
      graph_tier: 1
    },
    {
      id: 'research-note',
      label: 'Research Note',
      type: 'note',
      community: 'planning',
      graph_tier: 2
    },
    { id: 'tag:pkm', title: '#pkm', type: 'tag', cluster: 'tags' },
    { id: 'missing-note', type: 'note_or_unresolved', cluster: 'unresolved' }
  ],
  links: [
    { source: 'project-plan', target: 'research-note', type: 'wikilink' },
    { source: 'project-plan', target: 'tag:pkm', type: 'has_tag' },
    { source: { id: 'research-note' }, target: { id: 'missing-note' }, type: 'semantic_similar' }
  ]
};

const edgesFixture = {
  nodes: [
    { id: 'alpha-note', title: 'Alpha Note', node_type: 'note' },
    { id: 'beta-note', title: 'Beta Note', node_type: 'note' }
  ],
  edges: [{ source: 'alpha-note', target: 'beta-note', edge_type: 'wikilink' }]
};

test.describe('vault graph page', () => {
  test('renders graph API data with deterministic modes, filters, and note navigation', async ({ page }) => {
    const graphRequests: string[] = [];
    await mockGraphApi(page, async (route) => {
      graphRequests.push(route.request().url());
      await json(route, graphFixture);
    });

    await page.goto(`/${vaultName}/graph`);

    await expect(page.getByText('4 nodes')).toBeVisible();
    await expect(page.getByText('3 edges')).toBeVisible();
    expect(graphRequests.some((url) => new URL(url).pathname === `/api/v1/vault/${vaultName}/graph`)).toBe(true);

    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(4);
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(3);
    await expect(page.getByText('Project Plan')).toBeVisible();
    await expect(page.getByText('#pkm')).toBeVisible();
    await expect(page.getByText('missing-note')).toBeVisible();

    await page.getByRole('button', { name: 'Cluster' }).click();
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Cluster/);
    await expect(page.getByText(/planning/)).toBeVisible();

    await page.getByRole('button', { name: 'Degree' }).click();
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Degree/);
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
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/List/);
    await expect(page.getByRole('table', { name: 'Graph nodes' })).toBeVisible();

    await page.getByLabel('Edge type filter').selectOption('all');
    await page.getByRole('button', { name: 'Radial' }).click();
    await page.getByRole('button', { name: 'Open note Project Plan' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/project-plan$`));
  });

  test('accepts edges arrays and object-like references', async ({ page }) => {
    await mockGraphApi(page, async (route) => json(route, edgesFixture));

    await page.goto(`/${vaultName}/graph`);

    await expect(page.getByText('2 nodes')).toBeVisible();
    await expect(page.getByText('1 edge')).toBeVisible();
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

    await expect(page.getByText('86 nodes')).toBeVisible();
    await expect(page.getByText(/Rendering first 80 of 86/)).toBeVisible();
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(80);
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(86);
  });
});

async function mockGraphApi(page: Page, graphHandler: (route: Route) => Promise<void>) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = decodeURIComponent(url.pathname);

    if (path === `/api/v1/vault/${vaultName}/graph`) {
      await graphHandler(route);
      return;
    }

    if (path === '/api/v1/vaults') {
      await json(route, [{ name: vaultName, path: '/tmp/alpha', is_default: true }]);
      return;
    }

    await route.fulfill({ status: 404, body: `Unhandled mock route: ${path}` });
  });
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body)
  });
}
