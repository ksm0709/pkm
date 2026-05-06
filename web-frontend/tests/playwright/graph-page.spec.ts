import { expect, type Page, type Route, test } from '@playwright/test';
import { applyTheme } from './fixtures/theme';

type GraphNode = {
  id: string;
  title?: string;
  label?: string;
  type?: 'note' | 'tag' | 'note_or_unresolved';
  description?: string;
  community?: string;
  graph_tier?: string;
  importance?: number;
  path?: string;
};

type GraphLink = {
  source: string | { id: string };
  target: string | { id: string };
  type?: string;
  confidence?: number;
  weight?: number;
};

type GraphPayload = {
  nodes: GraphNode[];
  links?: GraphLink[];
  edges?: GraphLink[];
};

type TestNode = {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  radius: number;
  degree: number;
  hub: boolean;
  visible: boolean;
};

type TestApi = {
  settle: (ticks?: number) => Promise<void>;
  getNode: (id: string) => TestNode | null;
  getEdge: (
    source: string,
    target: string,
    type?: string
  ) => null | { source: string; target: string; type: string; distance: number; confidence: number; visible: boolean };
  getTransform: () => { x: number; y: number; k: number };
  getFocusState: (id: string) => 'focused' | 'neighbor' | 'muted' | 'normal' | null;
  getRenderedLabels: () => Array<{ id: string; text: string }>;
  hitTest: (screenX: number, screenY: number) => { id: string } | null;
  dragNode: (id: string, dx: number, dy: number) => Promise<void>;
  getRenderedCounts: () => { nodes: number; edges: number; labels: number };
  getForceOptions: () => { repulsion: number; linkDistance: number };
  getSimulationState: () => { generation: number; alpha: number; paused: boolean };
  getWorldState: () => {
    width: number;
    height: number;
    nodeBounds: { minX: number; minY: number; maxX: number; maxY: number };
  };
  getNodeStyle: (id: string) => null | { fill: string; stroke: string };
};

const TEST_VAULT = 'bear';

const enrichedGraphFixture: GraphPayload = {
  nodes: [
    {
      id: 'project-plan',
      title: 'Project Plan',
      type: 'note',
      community: 'planning',
      importance: 8,
      description: 'Planning hub for active PKM work.'
    },
    { id: 'journal', title: 'Journal', type: 'note', community: 'daily', importance: 3 },
    { id: 'architecture', title: 'Architecture', type: 'note', community: 'architecture', importance: 7 },
    { id: 'daily-log', title: 'Daily Log', type: 'note', community: 'daily', importance: 4 },
    {
      id: 'daily-hub',
      title: 'Daily Hub',
      type: 'note',
      community: 'daily',
      graph_tier: 'hub',
      path: '/vault/daily/daily-hub.md'
    },
    {
      id: 'hub-pkm-development',
      title: 'PKM Development Hub',
      type: 'note',
      community: 'planning',
      graph_tier: 'hub',
      importance: 9
    },
    { id: 'tag:pkm', title: '#pkm', type: 'tag', community: 'planning' },
    { id: 'missing-roadmap', title: 'Missing Roadmap', type: 'note_or_unresolved', community: 'planning' }
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
  test('renders a canvas force graph from enriched graph data', async ({ page }) => {
    const vaultName = TEST_VAULT;
    const graphRequests: string[] = [];
    await mockGraphApi(page, async (route) => {
      graphRequests.push(route.request().url());
      await json(route, enrichedGraphFixture);
    });

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    expect(graphRequests.some((url) => decodeURIComponent(new URL(url).pathname) === `/api/v1/vault/${vaultName}/graph`)).toBe(true);
    await expect(page.getByTestId('graph-force-surface')).toBeVisible();
    await expect(page.getByTestId('graph-canvas')).toBeVisible();
    await expect(page.getByTestId('graph-node')).toHaveCount(0);
    await expect(page.getByTestId('graph-summary')).toHaveCount(0);
    await expect(page.getByTestId('graph-cap-status')).toHaveCount(0);
    const surfaceFrame = await page.getByTestId('graph-force-surface').evaluate((element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return { borderTopWidth: style.borderTopWidth, width: rect.width, height: rect.height };
    });
    expect(surfaceFrame.borderTopWidth).toBe('0px');
    expect(surfaceFrame.height).toBeGreaterThan(520);
    const world = await graphWorldState(page);
    expect(world.width).toBeGreaterThan(surfaceFrame.width * 2);
    expect(world.height).toBeGreaterThan(surfaceFrame.height * 2);
    expect(world.nodeBounds.maxX).toBeGreaterThan(surfaceFrame.width);
    expect(world.nodeBounds.maxY).toBeGreaterThan(surfaceFrame.height);

    const counts = await graphCounts(page);
    expect(counts.nodes).toBe(enrichedGraphFixture.nodes.length);
    expect(counts.edges).toBe(enrichedGraphFixture.links?.length);

    const hub = await graphNode(page, 'hub-pkm-development');
    const journal = await graphNode(page, 'journal');
    expect(hub?.hub).toBe(true);
    expect(hub?.radius ?? 0).toBeGreaterThan(journal?.radius ?? 0);
    expect((await graphNode(page, 'tag:pkm'))?.type).toBe('tag');
    const normalStyle = await graphNodeStyle(page, 'architecture');
    expect(normalStyle?.fill).toBe('#374151');
    expect(normalStyle?.stroke).toBe('#111827');
    const dailyStyle = await graphNodeStyle(page, 'journal');
    expect(dailyStyle?.fill).toBe('#bbf7d0');
    expect(dailyStyle?.stroke).toBe('#16a34a');
    const dailyHubStyle = await graphNodeStyle(page, 'daily-hub');
    expect(dailyHubStyle?.fill).toBe('#2563eb');
    expect(dailyHubStyle?.stroke).toBe('#93c5fd');
    const tagStyle = await graphNodeStyle(page, 'tag:pkm');
    expect(tagStyle?.fill).toMatch(/^#(?:ca8a04|facc15)$/);
    expect(tagStyle?.stroke).toBe('#fef08a');
  });

  test('uses semantic confidence, zooms, pans, and drags nodes', async ({ page }) => {
    const vaultName = TEST_VAULT;
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    const semantic = await graphEdge(page, 'project-plan', 'architecture', 'semantic_similar');
    const wikilink = await graphEdge(page, 'project-plan', 'journal', 'wikilink');
    expect(semantic?.confidence).toBe(0.92);
    expect(semantic?.distance ?? Infinity).toBeLessThan(wikilink?.distance ?? 0);

    const generationBeforeForceChange = (await graphSimulationState(page)).generation;
    const nodeBeforeForceChange = await graphNode(page, 'journal');
    await setRange(page, 'Link distance', '160');
    await setRange(page, 'Repulsion strength', '-760');
    const hotState = await graphSimulationState(page);
    expect(hotState.generation).toBe(generationBeforeForceChange);
    expect(hotState.paused).toBe(false);
    expect(hotState.alpha).toBeGreaterThan(0);
    await expect.poll(async () => distance(nodeBeforeForceChange!, (await graphNode(page, 'journal'))!)).toBeGreaterThan(4);
    await settleGraph(page, 80);
    const expandedWikilink = await graphEdge(page, 'project-plan', 'journal', 'wikilink');
    const forceOptions = await graphForceOptions(page);
    expect(expandedWikilink?.distance ?? 0).toBeGreaterThan(wikilink?.distance ?? Infinity);
    expect(forceOptions).toEqual({ repulsion: -760, linkDistance: 160 });

    const beforeTransform = await graphTransform(page);
    await page.getByTestId('graph-canvas').hover();
    await page.mouse.wheel(0, -400);
    await expect.poll(() => graphTransform(page)).not.toEqual(beforeTransform);

    const afterZoom = await graphTransform(page);
    await dragCanvas(page, 30, -20);
    const afterPan = await graphTransform(page);
    expect(afterPan.x).not.toBe(afterZoom.x);
    expect(afterPan.y).not.toBe(afterZoom.y);

    const beforeNode = await graphNode(page, 'journal');
    await page.evaluate(async () => {
      await (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.dragNode('journal', 45, 10);
    });
    const afterNode = await graphNode(page, 'journal');
    expect(distance(beforeNode!, afterNode!)).toBeGreaterThan(10);
  });

  test('click focuses a neighborhood without URL navigation', async ({ page }) => {
    const vaultName = TEST_VAULT;
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    const before = page.url();

    await clickNode(page, 'project-plan');

    expect(page.url()).toBe(before);
    await expect(page.getByTestId('graph-focus-status')).toContainText('Project Plan');
    await expect(page.getByTestId('graph-focus-description')).toContainText('Planning hub for active PKM work.');
    expect(await focusState(page, 'project-plan')).toBe('focused');
    expect(await focusState(page, 'architecture')).toBe('neighbor');
    expect(await focusState(page, 'daily-log')).toBe('muted');
    expect(await graphLabels(page)).toEqual([
      { id: 'architecture', text: 'architecture' },
      { id: 'hub-pkm-development', text: 'hub-pkm-development' },
      { id: 'journal', text: 'journal' },
      { id: 'missing-roadmap', text: 'missing-roadmap' },
      { id: 'project-plan', text: 'project-plan' },
      { id: 'tag:pkm', text: 'tag:pkm' }
    ]);
  });

  test('double tapping empty graph space clears the focused neighborhood', async ({ page }) => {
    const vaultName = TEST_VAULT;
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    await clickNode(page, 'project-plan');
    await expect(page.getByTestId('graph-focus-status')).toContainText('Project Plan');
    expect(await focusState(page, 'daily-log')).toBe('muted');

    await doubleTapEmptyCanvas(page);

    await expect(page.getByTestId('graph-focus-status')).toContainText('full graph');
    expect(await focusState(page, 'project-plan')).toBe('normal');
    expect(await focusState(page, 'daily-log')).toBe('normal');
  });

  test('cmd click and long press open note preview while tag and unresolved nodes focus only', async ({ page }) => {
    const vaultName = TEST_VAULT;
    const previewRequests: string[] = [];
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));
    await mockNoteApi(page, async (route) => {
      previewRequests.push(route.request().url());
      await json(route, notePayload('project-plan', 'Project Plan'));
    });

    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    const before = page.url();

    await clickNode(page, 'project-plan', [modifierKey()]);
    await expect(page.getByTestId('graph-preview-sheet')).toBeVisible();
    await expect(page.getByTestId('graph-preview-sheet')).toContainText('Preview body for Project Plan');
    expect(previewRequests.some((url) => decodeURIComponent(new URL(url).pathname).endsWith('/notes/project-plan'))).toBe(true);
    await page.getByRole('button', { name: 'Close note preview' }).click();
    await expect(page.getByTestId('graph-preview-sheet')).toHaveCount(0);

    await clickNode(page, 'project-plan', [modifierKey()]);
    await expect(page.getByTestId('graph-preview-sheet')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('graph-preview-sheet')).toHaveCount(0);

    await longPressNode(page, 'project-plan');
    await expect(page.getByTestId('graph-preview-sheet')).toBeVisible();
    await page.keyboard.press('Escape');

    await clickNode(page, 'tag:pkm', [modifierKey()]);
    await expect(page.getByTestId('graph-preview-sheet')).toHaveCount(0);
    await expect(page.getByTestId('graph-focus-status')).toContainText('#pkm');

    await clickNode(page, 'missing-roadmap', [modifierKey()]);
    await expect(page.getByTestId('graph-preview-sheet')).toHaveCount(0);
    await expect(page.getByTestId('graph-focus-status')).toContainText('Missing Roadmap');
    expect(page.url()).toBe(before);
  });

  test('keyboard search, preview action, and escape keep canvas graph accessible', async ({ page }) => {
    const vaultName = TEST_VAULT;
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));
    await mockNoteApi(page, async (route) => json(route, notePayload('project-plan', 'Project Plan')));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    await page.getByRole('searchbox', { name: 'Search graph nodes' }).fill('project');
    await page.getByRole('button', { name: /Focus Project Plan/ }).click();
    await expect(page.getByTestId('graph-focus-status')).toContainText('Project Plan');
    await expect(page.getByTestId('graph-a11y-status')).toContainText(/Project Plan/);

    await page.getByRole('button', { name: /Preview focused note/ }).click();
    await expect(page.getByTestId('graph-preview-sheet')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('graph-preview-sheet')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('graph-focus-status')).toContainText('full graph');
  });

  test('handles graph failures, malformed payloads, cap status, and preview failures', async ({ page }) => {
    const vaultName = TEST_VAULT;

    await mockGraphApi(page, async (route) => route.fulfill({ status: 404, body: 'not found' }));
    await page.goto(graphPath(vaultName));
    await expect(page.getByText('Graph index not found.')).toBeVisible();

    await page.unroute('**/api/v1/vault/*/graph');
    await mockGraphApi(page, async (route) => json(route, malformedPayload));
    await page.goto(graphPath(vaultName));
    await expect(page.getByText('Graph is empty.')).toBeVisible();

    await page.unroute('**/api/v1/vault/*/graph');
    await mockGraphApi(page, async (route) => route.fulfill({ status: 500, body: 'boom' }));
    await page.goto(graphPath(vaultName));
    await expect(page.getByText(/GET graph.*500/)).toBeVisible();

    await page.unroute('**/api/v1/vault/*/graph');
    await mockGraphApi(page, async (route) => json(route, graphWithLowImportanceNodes(325)));
    await mockNoteApi(page, async (route) => route.fulfill({ status: 500, body: 'preview boom' }));
    await page.goto(graphPath(vaultName));
    await settleGraph(page);
    await expect(page.getByTestId('graph-cap-status')).toHaveCount(0);
    await page.getByRole('searchbox', { name: 'Search graph nodes' }).fill('project');
    await page.getByRole('button', { name: /Focus Project Plan/ }).click();
    await page.getByRole('button', { name: /Preview focused note/ }).click();
    await expect(page.getByTestId('graph-preview-error')).toContainText(/preview.*500/i);
  });

  test('keeps zoom controls usable on mobile viewports and dark theme surfaces dark', async ({ page }, testInfo) => {
    const vaultName = TEST_VAULT;
    await page.setViewportSize({ width: 390, height: 740 });
    if (testInfo.project.name.includes('dark')) {
      await page.addInitScript(() => localStorage.setItem('pkm.theme', 'dark'));
      await applyTheme(page, 'dark');
    }
    await mockGraphApi(page, async (route) => json(route, enrichedGraphFixture));

    await page.goto(graphPath(vaultName));
    await settleGraph(page);

    await expect(page.getByTestId('graph-controls')).toBeVisible();
    await page.getByRole('button', { name: 'Zoom out' }).click();
    expect((await graphTransform(page)).k).toBeLessThan(1);
    const beforePinch = await graphTransform(page);
    await pinchCanvas(page, 90, 180);
    expect((await graphTransform(page)).k).toBeGreaterThan(beforePinch.k);

    if (testInfo.project.name.includes('dark')) {
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
      const surfaceBackground = await page.getByTestId('graph-force-surface').evaluate((element) => {
        return window.getComputedStyle(element).backgroundColor;
      });
      expect(surfaceBackground).not.toBe('rgb(255, 255, 255)');
    }
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

async function settleGraph(page: Page, ticks = 180) {
  await expect(page.getByTestId('graph-canvas')).toBeVisible({ timeout: 3000 });
  await page.waitForFunction(() => Boolean((window as typeof window & { __pkmGraphTest?: TestApi }).__pkmGraphTest?.settle), null, { timeout: 2000 });
  await page.evaluate(async (settleTicks) => {
    await (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.settle(settleTicks);
  }, ticks);
}

function graphPath(vaultName: string) {
  return `/${encodeURIComponent(vaultName)}/graph`;
}

async function graphNode(page: Page, id: string) {
  return page.evaluate((nodeId) => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getNode(nodeId), id);
}

async function graphEdge(page: Page, source: string, target: string, type?: string) {
  return page.evaluate(([s, t, edgeType]) => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getEdge(s, t, edgeType || undefined), [
    source,
    target,
    type ?? ''
  ]);
}

async function graphCounts(page: Page) {
  return page.evaluate(() => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getRenderedCounts());
}

async function graphLabels(page: Page) {
  return page.evaluate(() => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getRenderedLabels());
}

async function graphTransform(page: Page) {
  return page.evaluate(() => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getTransform());
}

async function graphForceOptions(page: Page) {
  return page.evaluate(() => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getForceOptions());
}

async function graphSimulationState(page: Page) {
  return page.evaluate(() => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getSimulationState());
}

async function graphWorldState(page: Page) {
  return page.evaluate(() => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getWorldState());
}

async function graphNodeStyle(page: Page, id: string) {
  return page.evaluate((nodeId) => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getNodeStyle(nodeId), id);
}

async function focusState(page: Page, id: string) {
  return page.evaluate((nodeId) => (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.getFocusState(nodeId), id);
}

async function setRange(page: Page, name: string, value: string) {
  await page.getByLabel(name).evaluate(
    (input, nextValue) => {
      const range = input as HTMLInputElement;
      range.value = nextValue;
      range.dispatchEvent(new Event('input', { bubbles: true }));
    },
    value
  );
}

async function clickNode(page: Page, id: string, modifiers: ('Control' | 'Meta')[] = []) {
  const node = await graphNode(page, id);
  expect(node).not.toBeNull();
  const box = await page.getByTestId('graph-canvas').boundingBox();
  expect(box).not.toBeNull();
  const transform = await graphTransform(page);
  for (const modifier of modifiers) await page.keyboard.down(modifier);
  await page.mouse.click(box!.x + node!.x * transform.k + transform.x, box!.y + node!.y * transform.k + transform.y);
  for (const modifier of [...modifiers].reverse()) await page.keyboard.up(modifier);
}

async function longPressNode(page: Page, id: string) {
  const node = await graphNode(page, id);
  expect(node).not.toBeNull();
  const box = await page.getByTestId('graph-canvas').boundingBox();
  expect(box).not.toBeNull();
  const transform = await graphTransform(page);
  await page.mouse.move(box!.x + node!.x * transform.k + transform.x, box!.y + node!.y * transform.k + transform.y);
  await page.mouse.down();
  await page.waitForTimeout(650);
  await page.mouse.up();
}

async function dragCanvas(page: Page, dx: number, dy: number) {
  const box = await page.getByTestId('graph-canvas').boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2 + dx, box!.y + box!.height / 2 + dy, { steps: 5 });
  await page.mouse.up();
}

async function pinchCanvas(page: Page, startDistance: number, endDistance: number) {
  const box = await page.getByTestId('graph-canvas').boundingBox();
  expect(box).not.toBeNull();
  const center = { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 };
  await dispatchTouchPointer(page, 'pointerdown', 21, center.x - startDistance / 2, center.y);
  await dispatchTouchPointer(page, 'pointerdown', 22, center.x + startDistance / 2, center.y);
  await dispatchTouchPointer(page, 'pointermove', 21, center.x - endDistance / 2, center.y);
  await dispatchTouchPointer(page, 'pointermove', 22, center.x + endDistance / 2, center.y);
  await dispatchTouchPointer(page, 'pointerup', 21, center.x - endDistance / 2, center.y);
  await dispatchTouchPointer(page, 'pointerup', 22, center.x + endDistance / 2, center.y);
}

async function doubleTapEmptyCanvas(page: Page) {
  const point = await emptyCanvasPoint(page);
  await dispatchTouchPointer(page, 'pointerdown', 31, point.x, point.y);
  await dispatchTouchPointer(page, 'pointerup', 31, point.x, point.y);
  await page.waitForTimeout(80);
  await dispatchTouchPointer(page, 'pointerdown', 32, point.x, point.y);
  await dispatchTouchPointer(page, 'pointerup', 32, point.x, point.y);
}

async function emptyCanvasPoint(page: Page) {
  const box = await page.getByTestId('graph-canvas').boundingBox();
  expect(box).not.toBeNull();
  const candidates = [
    { x: box!.x + 24, y: box!.y + 24 },
    { x: box!.x + box!.width - 24, y: box!.y + 24 },
    { x: box!.x + 24, y: box!.y + box!.height - 24 },
    { x: box!.x + box!.width - 24, y: box!.y + box!.height - 24 },
    { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 }
  ];
  for (const candidate of candidates) {
    const hit = await page.evaluate(
      ({ x, y, left, top }) =>
        (window as typeof window & { __pkmGraphTest: TestApi }).__pkmGraphTest.hitTest(
          x - left,
          y - top
        ),
      { ...candidate, left: box!.x, top: box!.y }
    );
    if (!hit) return candidate;
  }
  throw new Error('Unable to find empty graph canvas point');
}

async function dispatchTouchPointer(page: Page, type: string, pointerId: number, clientX: number, clientY: number) {
  await page.getByTestId('graph-canvas').dispatchEvent(type, {
    bubbles: true,
    cancelable: true,
    pointerId,
    pointerType: 'touch',
    isPrimary: pointerId === 21,
    clientX,
    clientY
  });
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

function modifierKey(): 'Control' | 'Meta' {
  return process.platform === 'darwin' ? 'Meta' : 'Control';
}
