import { expect, type Page, type Route, test } from '@playwright/test';
import { loginAndFindVault } from './helpers/pkm';

type GraphNode = {
  id: string;
  title?: string;
  label?: string;
  type?: 'note' | 'tag' | 'note_or_unresolved';
  description?: string;
  community?: string;
  cluster?: string;
};

type GraphLink = {
  source: string | { id: string };
  target: string | { id: string };
  type?: string;
};

type GraphPayload = {
  nodes: GraphNode[];
  links?: GraphLink[];
  edges?: GraphLink[];
};

const nodeLinkFixture: GraphPayload = {
  nodes: [
    {
      id: 'project-plan',
      title: 'Project Plan',
      type: 'note',
      description: 'Planning note',
      community: 'planning'
    },
    {
      id: 'journal',
      title: 'Journal',
      type: 'note',
      description: 'Journal note',
      community: 'daily'
    },
    { id: 'tag:pkm', title: '#pkm', type: 'tag', description: 'PKM tag', community: 'tags' },
    {
      id: 'missing-roadmap',
      title: 'Missing Roadmap',
      type: 'note_or_unresolved',
      description: 'Unresolved note'
    }
  ],
  links: [
    { source: 'project-plan', target: 'journal', type: 'wikilink' },
    { source: 'project-plan', target: 'tag:pkm', type: 'has_tag' },
    { source: 'journal', target: 'missing-roadmap', type: 'semantic_similar' }
  ]
};

const edgesFixture: GraphPayload = {
  nodes: [
    { id: 'alpha', title: 'Alpha Note', type: 'note' },
    { id: 'beta', title: 'Beta Note', type: 'note' }
  ],
  edges: [{ source: { id: 'alpha' }, target: { id: 'beta' }, type: 'wikilink' }]
};

const malformedPayload = {
  nonsense: true,
  nodes: [12, null, { nope: 'yes' }],
  links: [{ source: 'ghost', target: 'nope', type: 'wikilink' }]
};

test.describe('vault graph page', () => {
  test('renders graph API data with modes, filters, and note-only navigation', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    const graphRequests: string[] = [];
    await mockGraphApi(page, async (route) => {
      graphRequests.push(route.request().url());
      await json(route, nodeLinkFixture);
    });

    await page.goto(`/${encodeURIComponent(vaultName)}/graph`);

    await expect(page.locator('.graph-summary')).toHaveText(/4 nodes · 3 edges/);
    expect(
      graphRequests.some(
        (url) => decodeURIComponent(new URL(url).pathname) === `/api/v1/vault/${vaultName}/graph`
      )
    ).toBe(true);
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(4);
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(3);
    await expect(
      page.locator('[data-testid="graph-row"]').filter({ hasText: 'Project Plan' })
    ).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]').filter({ hasText: '#pkm' })).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]').filter({ hasText: 'Missing Roadmap' })).toHaveCount(1);

    await page.getByRole('button', { name: 'Cluster' }).click();
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Mode: Cluster/);
    await expect(page.locator('.cluster-labels')).toContainText('planning');

    await page.getByRole('button', { name: 'Degree' }).click();
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Mode: Degree/);

    await page.getByLabel('Node type filter').selectOption('tag');
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]')).toContainText('#pkm');
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(0);

    const tagUrl = page.url();
    await page.locator('.graph-node.node-tag').click({ force: true });
    expect(page.url()).toBe(tagUrl);

    await page.getByLabel('Node type filter').selectOption('note_or_unresolved');
    await page.locator('.graph-node.node-note_or_unresolved').click({ force: true });
    expect(page.url()).toBe(tagUrl);

    await page.getByLabel('Node type filter').selectOption('all');
    await page.getByLabel('Edge type filter').selectOption('wikilink');
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(1);
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(2);

    await page.getByRole('button', { name: 'List' }).click();
    await expect(page.locator('[data-testid="graph-mode"]')).toHaveText(/Mode: List/);
    await expect(page.getByRole('table', { name: 'Graph nodes' })).toBeVisible();
    await expect(
      page
        .locator('[data-testid="graph-row"]')
        .filter({ hasText: 'Project Plan' })
        .getByRole('button', { name: 'Open note Project Plan' })
    ).toBeVisible();

    await page.getByRole('button', { name: 'Radial' }).click();
    await page
      .locator('[data-testid="graph-row"]')
      .filter({ hasText: 'Project Plan' })
      .getByRole('button', { name: 'Open note Project Plan' })
      .click();
    await expect(page).toHaveURL(
      new RegExp(`/${escapeRegExp(encodeURIComponent(vaultName))}/notes/project-plan$`)
    );
  });

  test('accepts edges arrays and object-like references', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, edgesFixture));

    await page.goto(`/${encodeURIComponent(vaultName)}/graph`);

    await expect(page.locator('.graph-summary')).toHaveText(/2 nodes · 1 edge/);
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(2);
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(1);
    await expect(
      page.locator('[data-testid="graph-row"]').filter({ hasText: 'Alpha Note' })
    ).toHaveCount(1);
  });

  test('treats malformed payloads as empty graph data', async ({ page }) => {
    await mockGraphApi(page, async (route) => json(route, malformedPayload));

    await page.goto(`/${vaultName}/graph`);

    await expect(page.getByText('Graph is empty.')).toBeVisible();
  });

  test('shows unavailable state for backend failures', async ({ page }) => {
    await mockGraphApi(page, async (route) => route.fulfill({ status: 500, body: 'boom' }));

    await page.goto(`/${vaultName}/graph`);

    await expect(page.locator('.graph-summary')).toHaveText('Graph unavailable');
    await expect(page.getByText('GET graph → 500')).toBeVisible();
  });

  test('missing graph response explains how to create the graph index', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => route.fulfill({ status: 404, body: 'not found' }));

    await page.goto(`/${encodeURIComponent(vaultName)}/graph`);

    await expect(page.getByText('Graph index not found.')).toBeVisible();
    await expect(page.getByText(/pkm index/)).toBeVisible();
  });

  test('shows no-match guidance when filters eliminate all rows', async ({ page }) => {
    await mockGraphApi(page, async (route) => json(route, graphFixture));

    await page.goto(`/${vaultName}/graph`);
    await expect(page.locator('.graph-summary')).toHaveText(/4 nodes · 3 edges/);

    await page.getByLabel('Node type filter').selectOption('tag');
    await page.getByLabel('Edge type filter').selectOption('semantic_similar');
    await expect(page.getByText('No graph matches for the current filters.')).toBeVisible();
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="graph-edge"]')).toHaveCount(0);
  });

  test('large graphs cap only the visual overview while keeping the list browsable', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    const nodes = Array.from({ length: 86 }, (_, index) => ({
      id: `note-${String(index + 1).padStart(2, '0')}`,
      title: `Note ${index + 1}`,
      type: 'note' as const
    }));
    const links = nodes.slice(1).map((node, index) => ({
      source: nodes[index].id,
      target: node.id,
      type: 'wikilink'
    }));
    await mockGraphApi(page, async (route) => json(route, { nodes, links }));

    await page.goto(`/${encodeURIComponent(vaultName)}/graph`);

    await expect(page.locator('.graph-summary')).toHaveText(/86 nodes · 85 edges/);
    await expect(page.locator('.cap-status')).toHaveText(/Rendering first 80 of 86/);
    await expect(page.locator('[data-testid="graph-node"]')).toHaveCount(80);
    await expect(page.locator('[data-testid="graph-row"]')).toHaveCount(86);
  });
});

async function mockGraphApi(page: Page, handler: (route: Route) => Promise<void>) {
  await page.route('**/api/v1/vault/*/graph', handler);
}

async function json(route: Route, payload: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(payload)
  });
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
