import { expect, type Page, type Route, test } from '@playwright/test';
import { applyTheme } from './fixtures/theme';
import { loginAndFindVault } from './helpers/pkm';

type GraphNode = {
  id: string;
  title?: string;
  label?: string;
  type?: 'note' | 'tag' | 'note_or_unresolved';
  description?: string;
  community?: string;
  cluster?: string;
  clusters?: string[];
  top_tags?: string[];
  graph_tier?: string;
  importance?: number;
};

type GraphLink = {
  source: string | { id: string };
  target: string | { id: string };
  type?: string;
  confidence?: number;
  weight?: number;
  relation?: string;
};

type GraphPayload = {
  nodes: GraphNode[];
  links?: GraphLink[];
  edges?: GraphLink[];
};

const enrichedGraphFixture: GraphPayload = {
  nodes: [
    {
      id: 'project-plan',
      title: 'Project Plan',
      type: 'note',
      description: 'Planning note',
      community: 'planning',
      importance: 8,
      top_tags: ['pkm']
    },
    {
      id: 'journal',
      title: 'Journal',
      type: 'note',
      description: 'Journal note',
      community: 'daily',
      importance: 3
    },
    {
      id: 'architecture',
      title: 'Architecture',
      type: 'note',
      description: 'Architecture note',
      community: 'architecture',
      importance: 7
    },
    {
      id: 'daily-log',
      title: 'Daily Log',
      type: 'note',
      description: 'Daily note',
      community: 'daily',
      importance: 4
    },
    {
      id: 'hub-pkm-development',
      title: 'PKM Development Hub',
      type: 'note',
      description: 'High degree hub note',
      community: 'planning',
      graph_tier: 'hub',
      importance: 9
    },
    {
      id: 'tag:pkm',
      title: '#pkm',
      type: 'tag',
      description: 'PKM tag',
      community: 'planning'
    },
    {
      id: 'missing-roadmap',
      title: 'Missing Roadmap',
      type: 'note_or_unresolved',
      description: 'Unresolved note',
      community: 'planning'
    }
  ],
  links: [
    { source: 'project-plan', target: 'journal', type: 'wikilink', weight: 1 },
    { source: 'project-plan', target: 'architecture', type: 'wikilink', weight: 1 },
    { source: 'project-plan', target: 'tag:pkm', type: 'has_tag', weight: 0.8 },
    { source: 'tag:pkm', target: 'hub-pkm-development', type: 'tagged_by', weight: 0.8 },
    { source: 'hub-pkm-development', target: 'project-plan', type: 'wikilink', weight: 1 },
    { source: 'hub-pkm-development', target: 'journal', type: 'wikilink', weight: 1 },
    { source: 'hub-pkm-development', target: 'architecture', type: 'wikilink', weight: 1 },
    { source: 'hub-pkm-development', target: 'daily-log', type: 'wikilink', weight: 1 },
    { source: 'project-plan', target: 'architecture', type: 'semantic_similar', confidence: 0.92 },
    { source: 'journal', target: 'daily-log', type: 'semantic_similar', confidence: 0.41 },
    { source: 'project-plan', target: 'missing-roadmap', type: 'semantic_similar', confidence: 0.55 }
  ]
};

const malformedPayload = {
  nonsense: true,
  nodes: [12, null, { nope: 'yes' }],
  links: [{ source: 'ghost', target: 'nope', type: 'wikilink' }]
};

test.describe('vault graph page', () => {
  test('renders a clustered force graph from enriched graph data', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    const graphRequests: string[] = [];
    await mockGraphApi(page, async (route) => {
      graphRequests.push(route.request().url());
      await json(route, enrichedGraphFixture);
    });

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    expect(
      graphRequests.some(
        (url) => decodeURIComponent(new URL(url).pathname) === `/api/v1/vault/${vaultName}/graph`
      )
    ).toBe(true);
    await expect(page.getByTestId('graph-force-surface')).toBeVisible();
    await expect(page.getByTestId('graph-node')).toHaveCount(enrichedGraphFixture.nodes.length);
    await expect(page.getByTestId('graph-edge')).toHaveCount(enrichedGraphFixture.links?.length ?? 0);
    await expect(graphNode(page, 'project-plan')).toHaveAttribute('data-node-type', 'note');
    await expect(graphNode(page, 'tag:pkm')).toHaveAttribute('data-node-type', 'tag');
    await expect(graphNode(page, 'missing-roadmap')).toHaveAttribute('data-node-type', 'note_or_unresolved');
    await expect(graphNode(page, 'hub-pkm-development')).toHaveAttribute('data-hub', 'true');
    await expect(page.getByRole('button', { name: 'Radial' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Cluster' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Degree' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'List' })).toHaveCount(0);
  });

  test('sizes nodes by degree and marks hubs', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    const hubSize = await numericAttribute(graphNode(page, 'hub-pkm-development'), 'data-size');
    const journalSize = await numericAttribute(graphNode(page, 'journal'), 'data-size');
    expect(hubSize).toBeGreaterThan(journalSize);
    await expect(graphNode(page, 'hub-pkm-development')).toHaveClass(/node-hub/);
    await expect(graphNode(page, 'hub-pkm-development')).toHaveAttribute('data-degree', '5');
  });

  test('uses semantic similarity confidence as layout force input', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    const semanticEdge = graphEdge(page, 'project-plan', 'architecture', 'semantic_similar');
    await expect(semanticEdge).toHaveAttribute('data-edge-type', 'semantic_similar');
    await expect(semanticEdge).toHaveAttribute('data-confidence', '0.92');
    await expect(semanticEdge).toHaveAttribute('data-weight', /^(?!0(?:\.0+)?$).+/);
    await expect(semanticEdge).toHaveAttribute('data-force-distance', /^(?!0(?:\.0+)?$).+/);

    const highConfidenceDistance = distance(
      await nodePosition(page, 'project-plan'),
      await nodePosition(page, 'architecture')
    );
    const unrelatedDistance = distance(
      await nodePosition(page, 'project-plan'),
      await nodePosition(page, 'daily-log')
    );
    expect(highConfidenceDistance).toBeLessThan(unrelatedDistance);
  });

  test('click focuses a neighborhood without URL navigation', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    const before = page.url();
    await graphNode(page, 'project-plan').click({ force: true });

    expect(page.url()).toBe(before);
    await expect(page.getByTestId('graph-focus-status')).toContainText('Project Plan');
    await expect(graphNode(page, 'architecture')).toHaveAttribute('data-focus-state', 'neighbor');
    await expect(graphNode(page, 'daily-log')).toHaveAttribute('data-focus-state', 'muted');
  });

  test('focus keeps global muted nodes rendered with stable positions', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    const before = await nodePosition(page, 'daily-log');

    await graphNode(page, 'project-plan').click({ force: true });
    await settleGraph(page);
    const after = await nodePosition(page, 'daily-log');

    await expect(graphNode(page, 'daily-log')).toHaveAttribute('data-focus-state', 'muted');
    expect(distance(before, after)).toBeLessThanOrEqual(8);
  });

  test('cmd click opens a note preview sheet and the open note icon routes to the note', async ({
    page
  }) => {
    const vaultName = await loginAndFindVault(page);
    const previewRequests: string[] = [];
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));
    await mockNoteApi(page, async (route) => {
      previewRequests.push(route.request().url());
      await json(route, notePayload('project-plan', 'Project Plan'));
    });

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    await graphNode(page, 'project-plan').click({ modifiers: [modifierKey()], force: true });

    await expect(page.getByTestId('graph-preview-sheet')).toBeVisible();
    await expect(page.getByTestId('graph-force-surface')).toBeVisible();
    await expect(page.getByTestId('graph-preview-sheet')).toContainText('Preview body for Project Plan');
    await expect(page.getByTestId('graph-layout')).toHaveAttribute('data-preview-open', 'true');
    expect(previewRequests.some((url) => decodeURIComponent(new URL(url).pathname).endsWith('/notes/project-plan'))).toBe(
      true
    );

    await page.getByRole('button', { name: /Open note Project Plan/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultPathPattern(vaultName)}/notes/project-plan$`));
  });

  test('long press opens a note preview without URL navigation', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));
    await mockNoteApi(page, async (route) => json(route, notePayload('project-plan', 'Project Plan')));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    const before = page.url();
    const box = await graphNode(page, 'project-plan').boundingBox();
    expect(box).not.toBeNull();

    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.waitForTimeout(700);
    await page.mouse.up();

    expect(page.url()).toBe(before);
    await expect(page.getByTestId('graph-preview-sheet')).toBeVisible();
    await expect(page.getByTestId('graph-preview-sheet')).toContainText('Preview body for Project Plan');
  });

  test('tag and unresolved nodes focus only and never open fake note previews', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    const previewRequests: string[] = [];
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));
    await mockNoteApi(page, async (route) => {
      previewRequests.push(route.request().url());
      await route.fulfill({ status: 500, body: 'tags and unresolved nodes must not fetch notes' });
    });

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    const before = page.url();

    await graphNode(page, 'tag:pkm').click({ modifiers: [modifierKey()], force: true });
    await expect(page.getByTestId('graph-focus-status')).toContainText('#pkm');
    await expect(page.getByTestId('graph-preview-sheet')).toHaveCount(0);
    expect(page.url()).toBe(before);

    await graphNode(page, 'missing-roadmap').click({ modifiers: [modifierKey()], force: true });
    await expect(page.getByTestId('graph-focus-status')).toContainText('Missing Roadmap');
    await expect(page.getByTestId('graph-preview-sheet')).toHaveCount(0);
    expect(page.url()).toBe(before);
    expect(previewRequests).toEqual([]);
  });

  test('limits labels to important and viewport nodes', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    const graph = graphWithLowImportanceNodes(72);
    await mockGraphApi(page, async (route) => json(route, graph));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    const labelCount = await page.getByTestId('graph-label').count();
    expect(labelCount).toBeLessThan(graph.nodes.length);
    await expect(graphLabel(page, 'hub-pkm-development')).toBeVisible();

    await graphNode(page, 'low-01').click({ force: true });
    await expect(graphLabel(page, 'low-01')).toBeVisible();
  });

  test('explains how to create the graph index when graph data is missing', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => route.fulfill({ status: 404, body: 'not found' }));

    await page.goto(graphPath(vaultName));

    await expect(page.getByText('Graph index not found.')).toBeVisible();
    await expect(page.getByText(/pkm index/)).toBeVisible();
  });

  test('treats malformed payloads as empty graph data', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, malformedPayload));

    await page.goto(graphPath(vaultName));

    await expect(page.getByText('Graph is empty.')).toBeVisible();
    await expect(page.getByTestId('graph-node')).toHaveCount(0);
  });

  test('shows graph backend failures without rendering stale graph data', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => route.fulfill({ status: 500, body: 'boom' }));

    await page.goto(graphPath(vaultName));

    await expect(page.getByText(/GET graph.*500/)).toBeVisible();
    await expect(page.getByTestId('graph-node')).toHaveCount(0);
  });

  test('shows preview failure inside the sheet', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));
    await mockNoteApi(page, async (route) => route.fulfill({ status: 500, body: 'preview boom' }));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    await graphNode(page, 'project-plan').click({ modifiers: [modifierKey()], force: true });

    await expect(page.getByTestId('graph-preview-sheet')).toBeVisible();
    await expect(page.getByTestId('graph-preview-error')).toContainText(/preview.*500/i);
  });

  test('caps the interactive graph at 300 nodes while preserving total counts', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    const graph = graphWithLowImportanceNodes(325);
    await mockGraphApi(page, async (route) => json(route, graph));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    await expect(page.getByTestId('graph-node')).toHaveCount(300);
    await expect(page.getByTestId('graph-cap-status')).toContainText('Rendering first 300 of 331');
    await expect(page.getByTestId('graph-summary')).toContainText('331 nodes');
  });

  test('adjusts attraction, repulsion, and zoom from graph controls', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    const before = await nodePosition(page, 'journal');

    await page.getByRole('slider', { name: 'Repulsion' }).fill('2.4');
    await page.getByRole('slider', { name: 'Attraction' }).fill('0.7');
    await settleGraph(page);
    const after = await nodePosition(page, 'journal');

    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-repulsion', '2.4');
    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-attraction', '0.7');
    expect(distance(before, after)).toBeGreaterThan(1);

    await page.getByRole('button', { name: 'Zoom in' }).click();
    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-zoom', '1.1');

    await page.getByRole('button', { name: 'Reset graph controls' }).click();
    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-zoom', '1');
    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-repulsion', '1.6');
    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-attraction', '1');
  });

  test('keeps zoom controls usable on mobile viewports', async ({ page }) => {
    const vaultName = await loginAndFindVault(page);
    await page.setViewportSize({ width: 390, height: 740 });
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    await expect(page.getByTestId('graph-controls')).toBeVisible();
    await page.getByRole('button', { name: 'Zoom out' }).click();
    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-zoom', '0.9');
    await page.getByRole('slider', { name: 'Zoom' }).fill('1.4');
    await expect(page.getByTestId('graph-force-surface')).toHaveAttribute('data-zoom', '1.4');
  });

  test('uses dark theme graph surfaces instead of hard-coded white', async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.includes('dark'), 'dark theme contract only');
    const vaultName = await loginAndFindVault(page);
    await page.addInitScript(() => {
      localStorage.setItem('pkm.theme', 'dark');
    });
    await applyTheme(page, 'dark');
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    const surfaceBackground = await page.getByTestId('graph-force-surface').evaluate((element) => {
      return window.getComputedStyle(element).backgroundColor;
    });
    const pageBackground = await page.locator('.graph-page').evaluate((element) => {
      return window.getComputedStyle(element).backgroundColor;
    });

    expect(surfaceBackground).not.toBe('rgb(255, 255, 255)');
    expect(pageBackground).not.toBe('rgb(255, 255, 255)');
  });
});

async function mockGraphApi(page: Page, handler: (route: Route) => Promise<void>) {
  await page.route('**/api/v1/vault/*/graph', handler);
}

async function mockNoteApi(page: Page, handler: (route: Route) => Promise<void>) {
  await page.route('**/api/v1/vault/*/notes/*', handler);
}

async function json(route: Route, payload: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(payload)
  });
}

async function settleGraph(page: Page) {
  await expect(page.getByTestId('graph-force-surface')).toBeVisible({ timeout: 1500 });
  await page.waitForFunction(() => {
    const testHook = (window as typeof window & { __pkmGraphTest?: { settle?: () => Promise<void> | void } })
      .__pkmGraphTest;
    return Boolean(testHook?.settle);
  }, null, { timeout: 1500 });
  await page.evaluate(async () => {
    await (window as typeof window & { __pkmGraphTest: { settle: () => Promise<void> | void } }).__pkmGraphTest.settle();
  });
}

function graphPath(vaultName: string) {
  return `/${encodeURIComponent(vaultName)}/graph`;
}

function graphNode(page: Page, id: string) {
  return page.locator(`[data-testid="graph-node"][data-node-id="${cssString(id)}"]`);
}

function graphLabel(page: Page, id: string) {
  return page.locator(`[data-testid="graph-label"][data-node-id="${cssString(id)}"]`);
}

function graphEdge(page: Page, source: string, target: string, type?: string) {
  const edgeTypeSelector = type ? `[data-edge-type="${cssString(type)}"]` : '';
  return page.locator(
    `[data-testid="graph-edge"][data-source="${cssString(source)}"][data-target="${cssString(target)}"]${edgeTypeSelector}`
  );
}

async function numericAttribute(locator: ReturnType<Page['locator']>, name: string) {
  const value = await locator.getAttribute(name);
  expect(value).not.toBeNull();
  return Number(value);
}

async function nodePosition(page: Page, id: string) {
  const value = await graphNode(page, id).getAttribute('data-position');
  expect(value).not.toBeNull();
  const match = value!.match(/^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$/);
  expect(match).not.toBeNull();
  return { x: Number(match![1]), y: Number(match![2]) };
}

function distance(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function notePayload(id: string, title: string) {
  return {
    note_id: id,
    title,
    body: `# ${title}\n\nPreview body for ${title}.`,
    frontmatter: { tags: ['pkm'] },
    tags: ['pkm'],
    importance: 8
  };
}

function graphWithLowImportanceNodes(count: number): GraphPayload {
  const lowNodes = Array.from({ length: count }, (_, index) => ({
    id: `low-${String(index + 1).padStart(2, '0')}`,
    title: `Low ${index + 1}`,
    type: 'note' as const,
    community: index % 2 === 0 ? 'daily' : 'archive',
    importance: 1
  }));
  const lowLinks = lowNodes.map((node, index) => ({
    source: index % 2 === 0 ? 'journal' : 'daily-log',
    target: node.id,
    type: 'wikilink',
    weight: 0.2
  }));

  return {
    nodes: [...enrichedGraphFixture.nodes.filter((node) => node.id !== 'missing-roadmap'), ...lowNodes],
    links: [...(enrichedGraphFixture.links ?? []), ...lowLinks]
  };
}

function cssString(value: string) {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function vaultPathPattern(value: string) {
  const decoded = escapeRegExp(value);
  const encoded = escapeRegExp(encodeURIComponent(value));
  return decoded === encoded ? decoded : `(?:${decoded}|${encoded})`;
}

function modifierKey() {
  return process.platform === 'darwin' ? 'Meta' : 'Control';
}
