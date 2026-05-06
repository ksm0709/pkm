import { expect, test, type Page, type Route } from '@playwright/test';

const vaultName = 'alpha';
const otherVaultName = 'beta';
const today = new Date().toISOString().slice(0, 10);
const longToken = 'supercalifragilistic'.repeat(18);
const projectPlanBody =
  '# Project Plan\n\nExpected rendered markdown body with #pkm and #work tags plus [highlight-only] bracket emphasis and [actual link](https://example.com).\n\n> Muted callout text for lower-priority context.\n\n- [ ] Draft task\n- [>] Active task\n- [x] Done task\n- [~] Paused task\n\nSee [[research-note]], [[research-note|aliased research]], and [[tag:pkm]].\n\nInline code `#pkm` and `[highlight-only]` remain plain.\n\n```md\n#work\n[highlight-only]\n- [ ] Code task stays literal\n[[research-note]]\n```';
const longContentBody = `# Long Content\n\n${longToken}\n\n\`${longToken}\`\n\n\`\`\`\n${longToken}\n\`\`\``;

const notes = [
  {
    note_id: 'project-plan',
    title: 'Project Plan',
    path: 'notes/project-plan.md',
    tags: ['work', 'pkm'],
    created_at: '2026-05-01',
    modified_at: '2026-05-01T10:00:00Z',
    description: 'Project coordination summary and next actions.'
  },
  {
    note_id: 'research-note',
    title: 'Research Note',
    path: 'notes/research-note.md',
    tags: ['pkm'],
    created_at: '2026-05-02',
    modified_at: '2026-05-03T12:00:00Z',
    description: 'Research backlink context and related notes.'
  },
  {
    note_id: 'long-content',
    title: 'Long Content',
    path: 'notes/long-content.md',
    tags: ['layout'],
    created_at: '2026-05-03',
    modified_at: '2026-05-02T12:00:00Z',
    description: 'Long line wrapping stress note.'
  }
];


const graphFixture = {
  nodes: [
    { id: 'project-plan', title: 'Project Plan', type: 'note', community: 'planning', graph_tier: 1 },
    { id: 'research-note', title: 'Research Note', type: 'note', community: 'planning', graph_tier: 2 },
    { id: 'tag:pkm', title: '#pkm', type: 'tag', cluster: 'tags' }
  ],
  links: [
    { source: 'project-plan', target: 'research-note', type: 'wikilink' },
    { source: 'project-plan', target: 'tag:pkm', type: 'has_tag' }
  ]
};

const betaNotes = [
  {
    note_id: 'beta-home',
    title: 'Beta Home',
    path: 'notes/beta-home.md',
    tags: ['beta'],
    created_at: '2026-05-03'
  }
];

const workflowBodies: Record<string, string> = {
  'zettelkasten_maintenance':
    'Execute the maintenance workflow.\n\n1. Review clusters.\n2. Create hub notes.\n3. Consolidate daily notes.',
  'daily_task_summary':
    "Create today's task summary subnote using create_daily_subnote."
};

let workflowConfigs: Record<string, {
  id: string;
  title: string;
  schedule_hour: number;
  trigger_time: string;
  enabled: boolean;
  marker_file: string;
  pre_hook: string | null;
  post_hook: string | null;
  snippet: string;
  body: string;
  jitter_type: string;
}>;

let askPayloads: Array<{ query?: string; context?: string; ask_session_id?: string }> = [];
let configCredentialStatus: Record<string, { configured: boolean; fingerprint: string | null }>;
let failNextConfigSaveFor = '';
let configGetCount = 0;

const noteBodies: Record<string, unknown> = {
  'project-plan': {
    note_id: 'project-plan',
    title: 'Project Plan',
    body: projectPlanBody,
    frontmatter: {},
    created: '2026-05-01',
    updated: '2026-05-02',
    tags: ['work', 'pkm'],
    importance: 7
  },
  'research-note': {
    note_id: 'research-note',
    title: 'Research Note',
    body: '# Research Note\n\nLinked neighbor content.',
    frontmatter: {},
    created: '2026-05-02',
    updated: null,
    tags: ['pkm'],
    importance: 5
  },
  [today]: {
    note_id: today,
    title: "Today's Daily",
    body: `# ${today}\n\nDaily note for keyboard routing.\n\n## Logs\n- [09:15:00] Morning planning checkpoint.\n- [14:05] Afternoon implementation update.`,
    frontmatter: {},
    created: today,
    updated: null,
    tags: ['daily'],
    importance: 4
  },
  [`${today}-standup`]: {
    note_id: `${today}-standup`,
    title: 'Standup Subnote',
    body: '# Standup Subnote\n\nDaily subnote content.',
    frontmatter: {},
    created: today,
    updated: null,
    tags: ['daily', 'meeting'],
    importance: 4
  },
  'long-content': {
    note_id: 'long-content',
    title: 'Long Content',
    body: longContentBody,
    frontmatter: {},
    created: '2026-05-03',
    updated: null,
    tags: ['layout'],
    importance: 5
  },
  'beta-home': {
    note_id: 'beta-home',
    title: 'Beta Home',
    body: '# Beta Home\n\nBeta vault landing content.',
    frontmatter: {},
    created: '2026-05-03',
    updated: null,
    tags: ['beta'],
    importance: 5
  }
};

test.describe('generated routing and event contracts', () => {
  test.beforeEach(async ({ page }) => {
    resetMockNotes();
    resetMockWorkflows();
    resetMockConfigs();
    askPayloads = [];
    failNextConfigSaveFor = '';
    configGetCount = 0;
    await mockPkmApi(page);
  });

  test('root, vault, note, and neighbor routes render their expected states', async ({
    page
  }) => {
    await page.addInitScript(() => localStorage.setItem('pkm.lastVault', 'alpha'));
    await page.goto('/');

    await expect(page).toHaveURL(new RegExp(`/${otherVaultName}/logger$`));
    await expectTopbar(page, otherVaultName, 'logger');
    await expect(page.getByRole('heading', { name: 'Logger' })).toHaveCount(0);
    await expect(page.getByText('Morning planning checkpoint.')).toBeVisible();

    await page.goto(`/${vaultName}`);
    await expectTopbar(page, vaultName, 'notes');
    await expect(page.getByRole('heading', { name: vaultName })).toHaveCount(0);
    await expect(page.getByText('3 notes')).toBeVisible();
    await expect(page.getByRole('link', { name: /Project Plan/ })).toBeVisible();
    await expect(page.locator('.note-title')).toHaveText([
      'Research Note',
      'Long Content',
      'Project Plan'
    ]);
    await expect(page.locator('.note-description')).toHaveText([
      'Research backlink context and related notes.',
      'Long line wrapping stress note.',
      'Project coordination summary and next actions.'
    ]);
    await expect(page.locator('.note-description', { hasText: 'project-plan.md' })).toHaveCount(0);
    await expect(page.getByLabel('Tag summary').getByText('#pkm')).toBeVisible();

    await page.getByRole('link', { name: /Project Plan/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/project-plan$`));
    await expectNoteHeaderId(page, 'project-plan');
    await expect(page.getByText(/Expected rendered markdown body/)).toBeVisible();
    await expect(page.getByText('SIGNAL ANALYZER')).toBeVisible();

    await page.getByRole('button', { name: 'Edit' }).click();
    await expect(page.locator('.cm-editor')).toBeVisible();

    await page.getByRole('link', { name: /Research Note/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/research-note$`));
    await expectNoteHeaderId(page, 'research-note');
  });

  test('note content scroll keeps topbar and navigation drawer fixed', async ({ page }) => {
    noteBodies['long-content'] = {
      ...(noteBodies['long-content'] as Record<string, unknown>),
      body: `# Long Content\n\n${Array.from(
        { length: 90 },
        (_, index) => `Scrollable note paragraph ${index + 1}. ${longToken.slice(0, 80)}`
      ).join('\n\n')}`
    };

    await page.addInitScript(() => localStorage.setItem('pkm.appNavOpen', 'true'));
    await page.goto(`/${vaultName}/notes/long-content`);
    await expect(page.locator('.app-nav-drawer.open')).toBeVisible();
    const notesNavItem = page.locator('.app-nav-drawer.open .nav-item', { hasText: 'Notes' });
    await expect(notesNavItem).toBeVisible();

    const topbarBefore = await page.locator('.topbar').boundingBox();
    const drawerBefore = await page.locator('.app-nav-drawer').boundingBox();
    expect(topbarBefore).not.toBeNull();
    expect(drawerBefore).not.toBeNull();

    const scrollMetrics = await page.locator('.vault-content').evaluate((el) => {
      el.scrollTop = el.scrollHeight;
      return {
        scrollTop: el.scrollTop,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        pageScrollY: window.scrollY
      };
    });

    expect(scrollMetrics.scrollHeight).toBeGreaterThan(scrollMetrics.clientHeight);
    expect(scrollMetrics.scrollTop).toBeGreaterThan(0);
    expect(scrollMetrics.pageScrollY).toBe(0);
    await expect(notesNavItem).toBeVisible();

    const topbarAfter = await page.locator('.topbar').boundingBox();
    const drawerAfter = await page.locator('.app-nav-drawer').boundingBox();
    expect(Math.round(topbarAfter?.y ?? -1)).toBe(Math.round(topbarBefore?.y ?? -2));
    expect(Math.round(drawerAfter?.y ?? -1)).toBe(Math.round(drawerBefore?.y ?? -2));
  });

  test('read mode wikilinks render as note links without linking code blocks', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    const noteBody = page.locator('.note-body');
    await expect(noteBody.getByText(/Expected rendered markdown body/)).toBeVisible();

    await expect(noteBody.getByRole('link', { name: 'research-note' })).toHaveAttribute(
      'href',
      `/${vaultName}/notes/research-note`
    );
    await expect(noteBody.getByRole('link', { name: 'aliased research' })).toHaveAttribute(
      'href',
      `/${vaultName}/notes/research-note`
    );
    await expect(noteBody.getByRole('link', { name: 'tag:pkm' })).toHaveAttribute(
      'href',
      `/${vaultName}/notes/tag%3Apkm`
    );
    await expect(noteBody.locator('pre code')).toContainText('[[research-note]]');
    await expect(noteBody.locator('pre code a')).toHaveCount(0);

    await noteBody.getByRole('link', { name: 'aliased research' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/research-note$`));
    await expectNoteHeaderId(page, 'research-note');
  });

  test('unresolved note links auto-create a blank note in the app', async ({ page }) => {
    await page.goto(`/${vaultName}/notes/unresolved-auto-note`);

    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/unresolved-auto-note$`));
    await expectNoteHeaderId(page, 'unresolved-auto-note');
    await expect(page.getByText('Note not found.')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible();
    expect(noteBodies['unresolved-auto-note']).toMatchObject({
      note_id: 'unresolved-auto-note',
      title: 'unresolved auto note',
      body: ''
    });
  });

  test('tag wikilink route renders tag hub neighbors when no tag note file exists', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    await page.locator('.note-body').getByRole('link', { name: 'tag:pkm' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/tag%3Apkm$`));
    await expectTopbar(page, vaultName, 'tag:pkm');
    await expect(page.getByRole('heading', { name: '#pkm' })).toHaveCount(0);
    await expect(page.getByText('Tag note not found.')).toBeVisible();
    await expect(page.getByText('SIGNAL ANALYZER')).toBeVisible();
    await expect(page.getByText('INBOUND')).toBeVisible();
    await expect(page.getByRole('link', { name: /Project Plan/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Research Note/ })).toBeVisible();
    await expect(page.getByText('Project coordination summary and next actions.')).toBeVisible();
    await expect(page.getByText('Research backlink context and related notes.')).toBeVisible();
    await expect(page.getByText('project-plan.md')).toHaveCount(0);
    await expect(page.getByText('research-note.md')).toHaveCount(0);
    await expectNoMissingPage(page, { allowTagNotFound: true });
  });

  test('read mode inline syntax renders tag chips, bracket highlights, and muted callouts', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    const noteBody = page.locator('.note-body');
    const pkmChip = noteBody.locator('a.note-tag-chip[data-tag="pkm"]').first();
    const workChip = noteBody.locator('a.note-tag-chip[data-tag="work"]').first();

    await expect(pkmChip).toHaveAttribute('href', `/${vaultName}/notes/tag%3Apkm`);
    await expect(workChip).toHaveAttribute('href', `/${vaultName}/notes/tag%3Awork`);
    await expect(pkmChip).toBeVisible();
    await expect(workChip).toBeVisible();
    await expect(pkmChip).toHaveCSS('border-radius', /999/);

    const headerPkmChip = page.locator('.note-tags a.note-tag-chip[data-tag="pkm"]');
    const headerWorkChip = page.locator('.note-tags a.note-tag-chip[data-tag="work"]');
    await expect(headerPkmChip).toHaveAttribute('href', `/${vaultName}/notes/tag%3Apkm`);
    await expect(headerWorkChip).toHaveAttribute('href', `/${vaultName}/notes/tag%3Awork`);
    await expect(headerPkmChip).toBeVisible();
    await expect(headerWorkChip).toBeVisible();

    const chipHues = await Promise.all([
      pkmChip.evaluate((el) => getComputedStyle(el).getPropertyValue('--tag-hue')),
      workChip.evaluate((el) => getComputedStyle(el).getPropertyValue('--tag-hue'))
    ]);
    expect(chipHues[0]).not.toBe(chipHues[1]);

    await expect(noteBody.locator('code a.note-tag-chip')).toHaveCount(0);
    await expect(noteBody.locator('pre a.note-tag-chip')).toHaveCount(0);
    await expect(noteBody.locator('code', { hasText: '#pkm' })).toBeVisible();
    await expect(noteBody.locator('pre code')).toContainText('#work');

    const bracketHighlight = noteBody.locator('span.note-bracket-highlight', {
      hasText: '[highlight-only]'
    });
    await expect(bracketHighlight).toBeVisible();
    await expect(
      noteBody.locator('a', { hasText: '[highlight-only]' })
    ).toHaveCount(0);
    await expect(noteBody.locator('a', { hasText: 'actual link' })).toHaveAttribute(
      'href',
      'https://example.com'
    );
    await expect(noteBody.locator('code span.note-bracket-highlight')).toHaveCount(0);
    await expect(noteBody.locator('pre span.note-bracket-highlight')).toHaveCount(0);
    await expect(
      noteBody.locator('p code', { hasText: /^\[highlight-only\]$/ })
    ).toBeVisible();
    await expect(noteBody.locator('pre code')).toContainText('[highlight-only]');

    const calloutMetrics = await noteBody.locator('blockquote').evaluate((el) => {
      const blockquoteStyle = getComputedStyle(el);
      const paragraph = document.querySelector('.note-body p');
      const paragraphStyle = paragraph ? getComputedStyle(paragraph) : null;
      return {
        backgroundColor: blockquoteStyle.backgroundColor,
        color: blockquoteStyle.color,
        paragraphColor: paragraphStyle?.color ?? ''
      };
    });

    expect(calloutMetrics.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
    expect(calloutMetrics.color).not.toBe(calloutMetrics.paragraphColor);
  });

  test('read mode task states render and cycle through saved markdown states', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);

    const noteBody = page.locator('.note-body');
    const taskStates = noteBody.locator('button.note-task-state');
    await expect(taskStates).toHaveCount(4);
    await expect(taskStates.nth(0)).toHaveText('');
    await expect(taskStates.nth(1)).toHaveText('>');
    await expect(taskStates.nth(2)).toHaveText('✓');
    await expect(taskStates.nth(3)).toHaveText('~');
    await expect(taskStates.nth(0)).toHaveAttribute('aria-label', 'Task status todo');
    await expect(taskStates.nth(1)).toHaveAttribute('aria-label', 'Task status in progress');
    await expect(taskStates.nth(2)).toHaveAttribute('aria-label', 'Task status done');
    await expect(taskStates.nth(3)).toHaveAttribute('aria-label', 'Task status canceled');
    const taskStateStyles = await taskStates.evaluateAll((buttons) =>
      buttons.map((button) => {
        const style = getComputedStyle(button);
        const rect = button.getBoundingClientRect();
        return {
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          borderRadius: style.borderRadius,
          backgroundColor: style.backgroundColor
        };
      })
    );
    for (const style of taskStateStyles) {
      expect(Math.abs(style.width - style.height)).toBeLessThanOrEqual(1);
      expect(style.borderRadius).not.toMatch(/999/);
    }
    expect(taskStateStyles[0].backgroundColor).toMatch(/rgb\(.*\)/);
    expect(taskStateStyles[0].backgroundColor).not.toBe(taskStateStyles[1].backgroundColor);
    expect(taskStateStyles[1].backgroundColor).not.toBe(taskStateStyles[2].backgroundColor);
    expect(taskStateStyles[2].backgroundColor).not.toBe(taskStateStyles[3].backgroundColor);
    await expect(noteBody.getByText('Draft task')).toBeVisible();
    await expect(noteBody.locator('pre button.note-task-state')).toHaveCount(0);
    await expect(noteBody.locator('pre code')).toContainText('- [ ] Code task stays literal');

    await taskStates.nth(0).click();
    await expect(taskStates.nth(0)).toHaveText('>');
    expect(noteBodyFor('project-plan')).toContain('- [>] Draft task');

    await taskStates.nth(0).click();
    await expect(taskStates.nth(0)).toHaveText('✓');
    expect(noteBodyFor('project-plan')).toContain('- [x] Draft task');

    await taskStates.nth(3).click();
    await expect(taskStates.nth(3)).toHaveText('');
    expect(noteBodyFor('project-plan')).toContain('- [ ] Paused task');
  });

  test('drawer, command palette, daily keyboard routing, and nav routes behave consistently', async ({
    page
  }) => {
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await expect(page.getByRole('button', { name: 'Open navigation drawer' })).toBeVisible();
    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'false'
    );

    await page.keyboard.press('Escape');
    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'true'
    );

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await page.getByRole('button', { name: 'Search' }).click();
    await expectCommandPaletteFocused(page);
    await page.keyboard.press('Escape');

    await page.keyboard.press('Control+K');
    await expectCommandPaletteFocused(page);
    await page.locator('.cmdk-input').fill('project');
    await expect(page.getByRole('option', { name: /Project Plan/ })).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/project-plan$`));

    await page.goto(`/${vaultName}`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await page.getByRole('button', { name: 'Ask' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/ask$`));

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await page.getByRole('button', { name: 'Daily' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/daily$`));
    await expectTopbar(page, vaultName, 'daily');
    await expect(page.getByRole('heading', { name: 'Daily' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: today, exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: /Standup Subnote/ })).toBeVisible();
    await expect(page.getByText('Today entry')).toHaveCount(0);
    await expect(page.getByText(/todo open/)).toHaveCount(0);
    await page.getByRole('link', { name: /Standup Subnote/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/${today}-standup$`));
    await expectNoteHeaderId(page, `${today}-standup`);
    await expect(page.getByText('Daily subnote content.')).toBeVisible();

    await page.goto(`/${vaultName}/daily`);
    await page.getByRole('link', { name: today }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/${today}$`));
    await expectNoteHeaderId(page, today);
    await expect(page.getByText('Daily note for keyboard routing.')).toBeVisible();

    await page.goto(`/${vaultName}/daily`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await expectTopbar(page, vaultName, 'daily');
    await expect(page.getByRole('heading', { name: 'Daily' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'false'
    );
    await page.getByRole('button', { name: 'Tags' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/tags$`));
    await expect(page.getByText('3 tags')).toBeVisible();
    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await page.getByRole('button', { name: 'Graph' }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/graph$`));
    await expect(page.getByText('3 nodes')).toBeVisible();

    await page.evaluate(() => {
      if (document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
    });
    await expect.poll(() => page.evaluate(() => Boolean((window as any).__pkmNav))).toBe(true);
    await page.keyboard.press('g');
    await page.keyboard.press('d');
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/${today}$`));
    await expectNoteHeaderId(page, today);
  });

  test('tags page sorts tags by reference count and opens tag notes', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/tags`);
    await page.waitForLoadState('networkidle').catch(() => {});

    await expectTopbar(page, vaultName, 'tags');
    await expect(page.getByText('3 tags')).toBeVisible();
    await expect(page.locator('.tag-name')).toHaveText(['#pkm', '#layout', '#work']);
    await expect(page.locator('.tag-count')).toHaveText(['2', '1', '1']);

    await page.getByRole('link', { name: /#pkm/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/tag%3Apkm$`));
    await expectTopbar(page, vaultName, 'tag:pkm');
    await expect(page.getByText('2 linked notes')).toBeVisible();
  });

  test('ask route auto-submits query params and streams manual submissions', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/ask?q=hello%20world`);

    await expect(page.getByText('hello world', { exact: true })).toBeVisible();
    await expect(page.getByText('Answer for hello world')).toBeVisible();
    await expect(page.locator('.chat-event.thinking .event-icon')).toHaveAttribute(
      'aria-label',
      'Thinking'
    );

    await page.goto(`/${vaultName}/ask?q=result%20payload`);
    await expect(page.getByText('result payload', { exact: true })).toBeVisible();
    await expect(page.getByText('Response-only answer for result payload')).toBeVisible();

    await page.getByPlaceholder(/Ask/).fill('second question');
    await page.getByRole('button', { name: 'Submit' }).click();

    await expect(page.getByText('second question', { exact: true })).toBeVisible();
    await expect(page.getByText('Answer for second question')).toBeVisible();
  });

  test('ask restores recent transcript after page reload', async ({ page }) => {
    await page.goto(`/${vaultName}/ask`);

    const input = page.getByPlaceholder(/Ask/);
    await input.fill('restore session check');
    await page.getByRole('button', { name: 'Submit' }).click();

    await expect(page.getByText('restore session check', { exact: true })).toBeVisible();
    await expect(page.getByText('Answer for restore session check')).toBeVisible();

    await page.reload();

    await expect(page.getByText('restore session check', { exact: true })).toBeVisible();
    await expect(page.getByText('Answer for restore session check')).toBeVisible();
    await expect(page.getByText('Enter a query packet below.')).toHaveCount(0);
  });

  test('ask keeps the latest assistant turn anchored near the chat bottom', async ({
    page
  }) => {
    await page.setViewportSize({ width: 390, height: 720 });
    await page.goto(`/${vaultName}/ask`);

    const input = page.getByPlaceholder(/Ask/);
    await input.fill('scroll anchor check');
    await page.getByRole('button', { name: 'Submit' }).click();

    await expect(page.getByText('Answer for scroll anchor check')).toBeVisible();
    const bottomGap = async () => {
      return page.evaluate(() => {
        const scrollArea = document.querySelector('.scroll-area')?.getBoundingClientRect();
        const latestAssistant = Array.from(document.querySelectorAll('.chat-message.assistant'))
          .at(-1)
          ?.getBoundingClientRect();
        if (!scrollArea || !latestAssistant) return Number.POSITIVE_INFINITY;
        return Math.round(scrollArea.bottom - latestAssistant.bottom);
      });
    };
    await expect.poll(bottomGap).toBeGreaterThanOrEqual(56);
    await expect.poll(bottomGap).toBeLessThanOrEqual(104);
  });

  test('ask input states and response transcript render correctly', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 720 });
    await page.goto(`/${vaultName}/ask`);

    const input = page.getByPlaceholder(/Ask/);
    const submit = page.getByRole('button', { name: 'Submit' });
    await expect(page.getByText('Enter a query packet below.')).toBeVisible();
    await expect(page.getByText('model test/default-model (auto)')).toBeVisible();
    await expect(submit).toBeDisabled();
    const initialInputBox = await page.locator('.ask-input').boundingBox();
    expect(initialInputBox).not.toBeNull();
    expect(Math.abs(initialInputBox?.x ?? 0)).toBeLessThanOrEqual(1);
    expect(Math.abs((initialInputBox?.width ?? 0) - 390)).toBeLessThanOrEqual(1);
    expect(Math.abs((initialInputBox?.y ?? 0) + (initialInputBox?.height ?? 0) - 720)).toBeLessThanOrEqual(2);
    const pageScrollMetrics = await page.evaluate(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: document.documentElement.clientHeight,
      scrollY: window.scrollY
    }));
    expect(pageScrollMetrics.scrollHeight).toBeLessThanOrEqual(pageScrollMetrics.clientHeight + 1);
    expect(pageScrollMetrics.scrollY).toBe(0);
    const composerStyle = await page.locator('.composer-shell').evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return { position: style.position, flexShrink: style.flexShrink };
    });
    expect(composerStyle.position).toBe('relative');
    expect(composerStyle.flexShrink).toBe('0');
    const askPageStyle = await page.locator('.ask-page').evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return { height: style.height, maxHeight: style.maxHeight, overflow: style.overflow };
    });
    expect(askPageStyle.overflow).toBe('hidden');
    expect(askPageStyle.maxHeight).toBe('none');
    await page.setViewportSize({ width: 390, height: 560 });
    await expect.poll(async () => {
      const box = await page.locator('.ask-input').boundingBox();
      return Math.round((box?.y ?? 0) + (box?.height ?? 0));
    }).toBe(560);
    await page.setViewportSize({ width: 390, height: 720 });
    await expect.poll(async () => {
      const box = await page.locator('.ask-input').boundingBox();
      return Math.round((box?.y ?? 0) + (box?.height ?? 0));
    }).toBe(720);
    const modelBox = await page.getByText('model test/default-model (auto)').boundingBox();
    const submitBox = await submit.boundingBox();
    const inputBox = await input.boundingBox();
    expect(modelBox).not.toBeNull();
    expect(submitBox).not.toBeNull();
    expect(inputBox).not.toBeNull();
    expect((modelBox?.x ?? 0)).toBeLessThanOrEqual((inputBox?.x ?? 0));
    const submitStyle = await submit.evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return { borderWidth: style.borderWidth, backgroundColor: style.backgroundColor };
    });
    expect(submitStyle.borderWidth).toBe('0px');
    const askTextareaStyle = await input.evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return {
        borderTopWidth: style.borderTopWidth,
        borderRightWidth: style.borderRightWidth,
        borderBottomWidth: style.borderBottomWidth,
        borderLeftWidth: style.borderLeftWidth
      };
    });
    expect(askTextareaStyle).toEqual({
      borderTopWidth: '0px',
      borderRightWidth: '0px',
      borderBottomWidth: '0px',
      borderLeftWidth: '0px'
    });

    await input.fill('line one');
    await expect(submit).toBeEnabled();
    await input.press('Enter');
    await expect(input).toHaveValue('line one\n');
    await expect(page.getByText('line one', { exact: true })).toHaveCount(0);

    await input.fill('rendering check');
    await input.press('Control+Enter');

    await expect(page.getByText('rendering check', { exact: true })).toBeVisible();
    await expect(page.locator('.chat-message.user')).toContainText('rendering check');
    await expect(page.locator('.chat-event.thinking .event-icon')).toHaveAttribute(
      'aria-label',
      'Thinking'
    );
    await expect(page.getByText('Reasoning for rendering check')).toBeHidden();
    await page.locator('summary[aria-label="Thinking details"]').click();
    await expect(page.getByText('Reasoning for rendering check')).toBeVisible();
    await expect(page.locator('.chat-event.tool-use .event-icon')).toHaveAttribute(
      'aria-label',
      'Tool use'
    );
    await expect(page.locator('.chat-event.tool-use')).toContainText('search');
    await expect(page.getByText('{"q":"rendering check"}')).toBeHidden();
    await page.locator('summary[aria-label="Tool use details search"]').click();
    await expect(page.getByText('{"q":"rendering check"}')).toBeVisible();
    await expect(page.locator('.chat-event.task .event-icon')).toHaveAttribute(
      'aria-label',
      'Task'
    );
    await expect(page.locator('.chat-event.task')).toContainText('Queued rendering check');
    await expect(page.getByText(`Answer for rendering check ${longToken}`)).toBeVisible();
    const transcriptChrome = await page
      .locator('.chat-message.user, .chat-message.assistant, .chat-event')
      .evaluateAll((els) =>
        els.map((el) => {
          const style = getComputedStyle(el as HTMLElement);
          return {
            borderTopWidth: style.borderTopWidth,
            backgroundColor: style.backgroundColor
          };
        })
      );
    for (const style of transcriptChrome) {
      expect(style.borderTopWidth).toBe('0px');
      expect(style.backgroundColor).toBe('rgba(0, 0, 0, 0)');
    }
    await expect(input).toBeEnabled();
    await expect(input).toHaveValue('');
    await expect(submit).toBeDisabled();
    const submittedInputBox = await page.locator('.ask-input').boundingBox();
    expect(submittedInputBox).not.toBeNull();
    expect(Math.abs((submittedInputBox?.y ?? 0) + (submittedInputBox?.height ?? 0) - 720)).toBeLessThanOrEqual(2);

    const transcriptOverflow = await page.locator('.transcript').evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth
    }));
    expect(transcriptOverflow.scrollWidth).toBeLessThanOrEqual(
      transcriptOverflow.clientWidth + 1
    );
  });

  test('ask pending agent turn renders animated ascii activity', async ({ page }) => {
    await page.goto(`/${vaultName}/ask`);

    const input = page.getByPlaceholder(/Ask/);
    await input.fill('slow animation check');
    await page.getByRole('button', { name: 'Submit' }).click();

    const activity = page.locator('.agent-activity');
    const frame = activity.locator('.activity-frame');
    await expect(activity).toBeVisible();
    await expect(activity).toContainText('agent turn');
    const firstFrame = await frame.textContent();
    await expect.poll(async () => frame.textContent()).not.toBe(firstFrame);
    await expect(page.getByText('Answer for slow animation check')).toBeVisible();
    await expect(activity).toHaveCount(0);
  });

  test('ask keeps an active agent turn running across in-app route changes', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/ask`);

    const input = page.getByPlaceholder(/Ask/);
    await input.fill('route carry check');
    await page.getByRole('button', { name: 'Submit' }).click();

    await expect(page.getByText('route carry check', { exact: true })).toBeVisible();
    await expect(page.locator('.agent-activity')).toBeVisible();

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await page.locator('button[aria-label="Notes"]').evaluate((el) => (el as HTMLElement).click());
    await expect(page).toHaveURL(new RegExp(`/${vaultName}$`));
    await expect(page.getByRole('link', { name: /Project Plan/ })).toBeVisible();

    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await page.locator('button[aria-label="Ask"]').evaluate((el) => (el as HTMLElement).click());
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/ask$`));

    await expect(page.getByText('route carry check', { exact: true })).toBeVisible();
    await expect(page.locator('.agent-activity')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Submit' })).toBeDisabled();
    await expect(page.getByText('Answer for route carry check')).toBeVisible();
    await expect(page.locator('.agent-activity')).toHaveCount(0);
  });

  test('ask assistant output renders markdown content', async ({ page }) => {
    await page.goto(`/${vaultName}/ask`);

    await page.getByPlaceholder(/Ask/).fill('markdown check');
    await page.getByRole('button', { name: 'Submit' }).click();

    const assistant = page.locator('.chat-message.assistant').last();
    await expect(assistant.getByRole('heading', { name: 'Markdown reply', level: 2 })).toBeVisible();
    await expect(assistant.getByText('bold answer')).toBeVisible();
    await expect(assistant.locator('strong')).toContainText('bold answer');
    await expect(assistant.locator('li').first()).toContainText('First item');
    await expect(assistant.locator('code')).toContainText('inline_code');
    await expect(assistant.getByRole('link', { name: 'reference link' })).toHaveAttribute(
      'href',
      'https://example.com'
    );
    await expect(assistant.locator('pre')).toHaveCount(0);
  });

  test('ask manage_tasks tool renders task checklist above the input', async ({ page }) => {
    await page.goto(`/${vaultName}/ask`);

    await page.getByPlaceholder(/Ask/).fill('manage tasks check');
    await page.getByRole('button', { name: 'Submit' }).click();

    const taskList = page.locator('.ask-task-list');
    await expect(taskList).toBeVisible();
    await expect(taskList.getByText('Review workflow schedule')).toBeVisible();
    await expect(taskList.getByText('Write regression test')).toBeVisible();
    await expect(taskList.getByText('Run task parser')).toBeVisible();
    await expect(taskList.getByRole('checkbox')).toHaveCount(3);
    await expect(taskList.getByRole('checkbox', { name: 'Review workflow schedule' })).toBeChecked();
    await expect(taskList.getByRole('checkbox', { name: 'Write regression test' })).not.toBeChecked();
    await expect(taskList.getByRole('checkbox', { name: 'Run task parser' })).not.toBeChecked();
    await expect(taskList).not.toContainText('[{"text"');

    const completedTask = taskList.locator('.task-item', {
      hasText: 'Review workflow schedule'
    });
    const runningTask = taskList.locator('.task-item', { hasText: 'Run task parser' });
    await expect(completedTask.locator('.task-text')).toHaveCSS('text-decoration-line', /line-through/);
    await expect(runningTask.locator('.task-box')).toContainText('>');
    await expect(runningTask).toHaveClass(/progress/);
    await expect(page.locator('.chat-event.tool-use')).not.toContainText('manage_tasks');

    const taskToggle = taskList.getByRole('button', { name: /Managed tasks/i });
    await expect(taskToggle).toHaveAttribute('aria-expanded', 'true');
    await taskToggle.click();
    await expect(taskToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(taskList.getByText('Review workflow schedule')).toBeHidden();
    await taskToggle.click();
    await expect(taskToggle).toHaveAttribute('aria-expanded', 'true');
    await expect(taskList.getByText('Review workflow schedule')).toBeVisible();

    const taskBox = await taskList.boundingBox();
    const inputBox = await page.locator('.ask-input').boundingBox();
    expect(taskBox).not.toBeNull();
    expect(inputBox).not.toBeNull();
    expect((taskBox?.y ?? 0) + (taskBox?.height ?? 0)).toBeLessThanOrEqual(
      (inputBox?.y ?? 0) + 1
    );
  });

  test('ask slash menu shows session command, tiny-agent skills and workflows', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/ask`);

    const input = page.getByPlaceholder(/Ask/);
    await input.fill('/');

    const menu = page.locator('.ask-slash-menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByRole('option', { name: /^\/new\s+session/i })).toBeVisible();
    await expect(menu.getByRole('option', { name: /^\/pkm\s+skill/i })).toBeVisible();
    await expect(menu.getByRole('option', { name: /\/pkm:diagnosis.*skill/i })).toBeVisible();
    await expect(
      menu.getByRole('option', { name: /\/workflow daily_task_summary.*workflow/i })
    ).toBeVisible();
    await expect(menu.getByRole('option', { name: /\/search.*command/i })).toHaveCount(0);
    await expect(menu.getByRole('option', { name: /\/tdd.*skill/i })).toHaveCount(0);

    const menuBox = await menu.boundingBox();
    const inputBox = await page.locator('.ask-input').boundingBox();
    expect(menuBox).not.toBeNull();
    expect(inputBox).not.toBeNull();
    expect((menuBox?.y ?? 0) + (menuBox?.height ?? 0)).toBeLessThanOrEqual(
      (inputBox?.y ?? 0) + 1
    );

    await input.fill('/sum');
    await expect(menu.getByRole('option').first()).toContainText(
      '/workflow daily_task_summary'
    );

    await input.press('ArrowDown');
    await input.press('ArrowUp');
    await input.press('Enter');

    await expect(input).toHaveValue('/workflow daily_task_summary');
    await expect(menu).toHaveCount(0);
    await expect(page.getByText('/workflow daily_task_summary', { exact: true })).toHaveCount(0);

    await input.press('Control+Enter');

    await expect(page.getByText('/workflow daily_task_summary', { exact: true })).toBeVisible();
    await expect(page.getByText('Answer for /workflow daily_task_summary')).toBeVisible();
    await expect(input).toHaveValue('');
  });

  test('ask input suggests notes and tags while typing inline wikilinks', async ({ page }) => {
    await page.goto(`/${vaultName}/ask`);

    const textarea = page.locator('.ask-textarea');
    await textarea.fill('Review [[');
    const suggest = page.getByRole('listbox', { name: 'Inline suggestions' });
    await expect(suggest.getByRole('option').first()).toContainText('project-plan');

    await textarea.fill('Review [[res');
    await expect(suggest).toBeVisible();
    await expect(suggest.getByRole('option').first()).toContainText('research-note');

    await textarea.press('Enter');
    await expect(textarea).toHaveValue('Review [[research-note]]');

    await textarea.fill('Topic #pk');
    await expect(suggest.getByRole('option', { name: /#pkm/ })).toBeVisible();
    await textarea.press('Enter');
    await expect(textarea).toHaveValue('Topic #pkm');
  });

  test('ask /new clears cached transcript and following asks send prior turns as context', async ({
    page
  }) => {
    await page.goto(`/${vaultName}/ask`);

    const input = page.getByPlaceholder(/Ask/);
    await input.fill('first context check');
    await page.getByRole('button', { name: 'Submit' }).click();
    await expect(page.getByText('Answer for first context check')).toBeVisible();

    await input.fill('second context check');
    await page.getByRole('button', { name: 'Submit' }).click();
    await expect(page.getByText('Answer for second context check')).toBeVisible();

    expect(askPayloads).toHaveLength(2);
    expect(askPayloads[0].context ?? '').toBe('');
    expect(askPayloads[0].ask_session_id ?? '').toMatch(/^web-/);
    expect(askPayloads[1].context ?? '').toContain('User: first context check');
    expect(askPayloads[1].context ?? '').toContain('Assistant: Answer for first context check');
    expect(askPayloads[1].context ?? '').not.toContain('second context check');
    expect(askPayloads[1].ask_session_id).toBe(askPayloads[0].ask_session_id);
    const previousSessionId = askPayloads[1].ask_session_id;

    await input.fill('/');
    const menu = page.locator('.ask-slash-menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByRole('option', { name: /^\/new\s+session/i })).toBeVisible();

    await input.fill('/new');
    await input.press('Control+Enter');

    await expect(page.getByText('Enter a query packet below.')).toBeVisible();
    await expect(page.getByText('first context check', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Answer for second context check')).toHaveCount(0);
    await expect(input).toHaveValue('');
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem('pkm.askSession.alpha')))
      .toBeNull();

    await input.fill('fresh context check');
    await page.getByRole('button', { name: 'Submit' }).click();
    await expect(page.getByText('Answer for fresh context check')).toBeVisible();
    expect(askPayloads.at(-1)?.context ?? '').toBe('');
    expect(askPayloads.at(-1)?.ask_session_id).toMatch(/^web-/);
    expect(askPayloads.at(-1)?.ask_session_id).not.toBe(previousSessionId);
  });

  test('logger route renders today logs and appends new timestamped entries', async ({
    page
  }) => {
    await page.setViewportSize({ width: 390, height: 720 });
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'false'
    );
    await page
      .locator('button[aria-label="Logger"]')
      .evaluate((el) => (el as HTMLElement).click());

    await expect(page).toHaveURL(new RegExp(`/${vaultName}/logger$`));
    await expectTopbar(page, vaultName, 'logger');
    await expect(page.getByRole('heading', { name: 'Logger' })).toHaveCount(0);
    await expect(page.getByText(today)).toBeVisible();
    await expect(page.getByText('09:15:00')).toBeVisible();
    await expect(page.getByText('Morning planning checkpoint.')).toBeVisible();
    await expect(page.getByText('09:00')).toBeVisible();
    await expect(page.getByText('14:05')).toBeVisible();
    await expect(page.getByText('Afternoon implementation update.')).toBeVisible();
    await expect(page.getByText('14:00')).toBeVisible();

    const input = page.getByPlaceholder(/Add log/);
    const addLogButton = page.getByRole('button', { name: 'Add log' });
    await expect(addLogButton).toHaveText('⌘↵');
    const loggerInputBox = await page.locator('.logger-input').boundingBox();
    expect(loggerInputBox).not.toBeNull();
    expect(Math.abs((loggerInputBox?.y ?? 0) + (loggerInputBox?.height ?? 0) - 720)).toBeLessThanOrEqual(2);
    const loggerTextareaStyle = await input.evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return {
        borderTopWidth: style.borderTopWidth,
        borderRightWidth: style.borderRightWidth,
        borderBottomWidth: style.borderBottomWidth,
        borderLeftWidth: style.borderLeftWidth
      };
    });
    expect(loggerTextareaStyle).toEqual({
      borderTopWidth: '0px',
      borderRightWidth: '0px',
      borderBottomWidth: '0px',
      borderLeftWidth: '0px'
    });
    const addLogButtonStyle = await addLogButton.evaluate((el) => {
      const style = getComputedStyle(el as HTMLElement);
      return { borderWidth: style.borderWidth, backgroundColor: style.backgroundColor };
    });
    expect(addLogButtonStyle.borderWidth).toBe('0px');
    await input.fill('Shipped logger UI');
    await addLogButton.click();

    await expect(page.getByText('16:45:12')).toBeVisible();
    await expect(page.getByText('Shipped logger UI')).toBeVisible();
    await expect(input).toHaveValue('');
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}/notes/project-plan`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.getByLabel('Open vault logger').click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/logger$`));
    await expectTopbar(page, vaultName, 'logger');
    await expect(page.getByRole('heading', { name: 'Logger' })).toHaveCount(0);
  });

  test('logger input suggests notes and tags while typing inline wikilinks', async ({ page }) => {
    await page.goto(`/${vaultName}/logger`);

    const input = page.locator('.logger-textarea');
    await input.fill('Captured [[res');
    const suggest = page.getByRole('listbox', { name: 'Inline suggestions' });
    await expect(suggest.getByRole('option').first()).toContainText('research-note');
    await input.press('Enter');
    await expect(input).toHaveValue('Captured [[research-note]]');

    await input.fill('Captured #wo');
    await expect(suggest.getByRole('option', { name: /#work/ })).toBeVisible();
    await input.press('Enter');
    await expect(input).toHaveValue('Captured #work');
  });

  test('workflow routes render list, read mode detail, and editable schedule modal', async ({
    page
  }) => {
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await expect(page.locator('aside[aria-label="App navigation"]')).toHaveAttribute(
      'aria-hidden',
      'false'
    );
    await page
      .locator('button[aria-label="Workflows"]')
      .evaluate((el) => (el as HTMLElement).click());

    await expect(page).toHaveURL(new RegExp(`/${vaultName}/workflows$`));
    await expectTopbar(page, vaultName, 'workflows');
    await expect(page.getByRole('heading')).toHaveCount(0);
    await expect(page.locator('.ledger-head').getByText('WORKFLOW', { exact: true })).toBeVisible();
    await expect(page.locator('.ledger-head').getByText('TRIGGER', { exact: true })).toBeVisible();
    await expect(page.locator('.ledger-head').getByText('STATE', { exact: true })).toBeVisible();
    await expect(page.getByText('daily task summary')).toBeVisible();
    await expect(page.getByText('08:00')).toBeVisible();
    await expect(page.getByRole('link', { name: /daily task summary/ })).toContainText('on');

    await page.getByRole('link', { name: /daily task summary/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/workflows/daily_task_summary$`));
    await expectTopbar(page, vaultName, 'workflow:daily_task_summary');
    await expect(page.locator('.workflow-header .meta-rail')).toContainText('WORKFLOW');
    await expect(page.locator('.workflow-header .meta-rail')).toContainText(
      'daily_task_summary'
    );
    await expect(page.getByText("Create today's task summary subnote")).toBeVisible();

    await page.getByRole('button', { name: 'Workflow settings' }).click();
    const modal = page.getByRole('dialog', { name: 'Workflow settings' });
    await expect(modal).toBeVisible();
    await expect(modal.getByLabel('Enabled')).toBeChecked();
    await expect(modal.getByLabel('Trigger time')).toHaveValue('08:00');

    await modal.getByLabel('Enabled').uncheck();
    await modal.getByLabel('Trigger time').fill('06:00');
    await modal.getByRole('button', { name: 'Save workflow settings' }).click();

    await expect(modal).toHaveCount(0);
    await expect(page.getByText('06:00')).toBeVisible();
    await expect(page.getByText('off')).toBeVisible();
    expect(workflowConfigs.daily_task_summary.enabled).toBe(false);
    expect(workflowConfigs.daily_task_summary.trigger_time).toBe('06:00');
  });

  test('note body wraps long content within the viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto(`/${vaultName}/notes/long-content`);

    await expectNoteHeaderId(page, 'long-content');
    await expect(page.getByText(longToken).first()).toBeVisible();

    const bodyMetrics = await page.locator('.note-body').evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      pageScrollWidth: document.documentElement.scrollWidth,
      pageClientWidth: document.documentElement.clientWidth
    }));

    expect(bodyMetrics.scrollWidth).toBeLessThanOrEqual(bodyMetrics.clientWidth + 1);
    expect(bodyMetrics.pageScrollWidth).toBeLessThanOrEqual(
      bodyMetrics.pageClientWidth + 1
    );
  });

  test('note reading surface removes side rules and uses practical page width', async ({
    page
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`/${vaultName}/notes/project-plan`);

    await expectNoteHeaderId(page, 'project-plan');

    const metrics = await page.locator('.note-body').evaluate((el) => {
      const bodyStyle = getComputedStyle(el);
      const header = document.querySelector('.note-header');
      const headerStyle = header ? getComputedStyle(header) : null;
      const rect = el.getBoundingClientRect();
      return {
        width: rect.width,
        borderLeftWidth: bodyStyle.borderLeftWidth,
        borderRightWidth: bodyStyle.borderRightWidth,
        headerBorderLeftWidth: headerStyle?.borderLeftWidth ?? ''
      };
    });

    expect(metrics.width).toBeGreaterThan(900);
    expect(metrics.borderLeftWidth).toBe('0px');
    expect(metrics.borderRightWidth).toBe('0px');
    expect(metrics.headerBorderLeftWidth).toBe('0px');
  });

  test('note edit mode suggests notes and tags while typing inline wikilinks', async ({ page }) => {
    await page.goto(`/${vaultName}/notes/project-plan`);
    await page.getByRole('button', { name: 'Edit' }).click();
    const editor = page.locator('.cm-content');
    await editor.click();
    await page.keyboard.press('i');
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
    await page.keyboard.press('Backspace');
    await page.keyboard.type('See [[res');

    await expect(page.getByRole('option').first()).toContainText('research-note');
    await page.getByRole('option').first().click();
    await expect(editor).toContainText('See [[research-note]]');

    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+A' : 'Control+A');
    await page.keyboard.press('Backspace');
    await page.keyboard.type('Tag #pk');
    await expect(page.getByRole('option', { name: /#pkm/ })).toBeVisible();
    await page.getByRole('option', { name: /#pkm/ }).click();
    await expect(editor).toContainText('Tag #pkm');
  });

  test('command palette static commands never route to missing pages and render target content', async ({
    page
  }) => {
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState('networkidle').catch(() => {});

    await openCommandPalette(page);
    await page.getByRole('option', { name: /Jump to note/ }).click();
    await expectCommandPaletteFocused(page);
    await page.keyboard.press('Escape');

    await openCommandPalette(page);
    await page.getByRole('option', { name: /Open today's daily note/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/${today}$`));
    await expectNoteHeaderId(page, today);
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openCommandPalette(page);
    await page.locator('.cmdk-input').fill('ask routing');
    await page.getByRole('option', { name: /Ask/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/ask\\?q=ask%20routing$`));
    await expect(page.getByText('ask routing', { exact: true })).toBeVisible();
    await expect(page.getByText('Answer for ask routing')).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openCommandPalette(page);
    await page.getByRole('option', { name: /Switch vault/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}$`));
    await expectTopbar(page, vaultName, 'notes');
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]')
    ).toBeVisible();
    await expect(page.getByRole('option', { name: new RegExp(`^${vaultName}`) })).toBeVisible();
    await expect(page.getByRole('option', { name: new RegExp(`^${otherVaultName}`) })).toBeVisible();
    await page.getByRole('option', { name: new RegExp(`^${otherVaultName}`) }).click();
    await expect(page).toHaveURL(new RegExp(`/${otherVaultName}/logger$`));
    await expectTopbar(page, otherVaultName, 'logger');
    await expect(page.getByRole('heading', { name: 'Logger' })).toHaveCount(0);
    await expect(page.getByText('Morning planning checkpoint.')).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await page.evaluate(() => localStorage.removeItem('pkm.theme'));
    await openCommandPalette(page);
    await page.getByRole('option', { name: /Toggle theme/ }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await expect(page).toHaveURL(new RegExp(`/${vaultName}$`));
    await expectNoMissingPage(page);

    await openCommandPalette(page);
    await expect(page.getByRole('option', { name: /Open logger/ })).toBeVisible();
    await page.getByRole('option', { name: /Open logger/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/logger$`));
    await expectTopbar(page, vaultName, 'logger');
    await expect(page.getByRole('heading', { name: 'Logger' })).toHaveCount(0);
    await expect(page.getByText('Morning planning checkpoint.')).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openCommandPalette(page);
    await page.locator('.cmdk-input').fill('workflow');
    await expect(page.getByRole('option', { name: /Open workflows/ })).toBeVisible();
    await page.getByRole('option', { name: /Open workflows/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/workflows$`));
    await expectTopbar(page, vaultName, 'workflows');
    await expect(page.getByText('daily task summary')).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await page.getByRole('button', { name: 'Open navigation drawer' }).click();
    await expect(page.locator('button[aria-label="Graph"]')).toBeVisible();

    await openCommandPalette(page);
    await page.getByRole('option', { name: /Open graph/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/graph$`));
    await expect(page.getByText('3 nodes')).toBeVisible();
    await expect(
      page.locator('[role="dialog"][aria-label="Command palette"]')
    ).toBeHidden();
    await expectNoMissingPage(page);
  });

  test('configs route manages ask credentials without storing raw secrets', async ({ page }) => {
    const rawSecret = 'sk-live-raw-config-secret';
    await page.goto(`/${vaultName}/configs`);

    await expectTopbar(page, vaultName, 'configs');
    await expect(page.getByRole('heading', { name: 'Configs' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Global Settings' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Ask Model Credentials' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Vault Settings' })).toBeVisible();

    const openai = page.locator('[data-provider-id="openai"]');
    const anthropic = page.locator('[data-provider-id="anthropic"]');
    await expect(openai).toContainText('OpenAI');
    await expect(openai).toContainText('OPENAI_API_KEY');
    await expect(openai).toContainText('not configured');
    await expect(anthropic).toContainText('Anthropic');
    await expect(anthropic).toContainText('configured');
    await expect(anthropic).toContainText('fp_existing');

    const getCountBeforeSave = configGetCount;
    await openai.getByLabel('OpenAI API key').fill(rawSecret);
    await openai.getByRole('button', { name: 'Save OpenAI credential' }).click();
    await expect(openai.getByText('Saved', { exact: true })).toBeVisible();
    expect(configGetCount).toBeGreaterThan(getCountBeforeSave);
    await expect(openai.getByLabel('OpenAI API key')).toHaveValue('');
    await expect(openai).toContainText('configured');
    await expect(openai).toContainText('fp_openai_saved');

    const storageSnapshot = await page.evaluate((secret) => {
      const dump = (storage: Storage) =>
        Array.from({ length: storage.length }, (_, index) => {
          const key = storage.key(index) ?? '';
          return `${key}=${storage.getItem(key) ?? ''}`;
        }).join('\n');
      return {
        local: dump(localStorage),
        session: dump(sessionStorage)
      };
    }, rawSecret);
    expect(storageSnapshot.local).not.toContain(rawSecret);
    expect(storageSnapshot.session).not.toContain(rawSecret);

    failNextConfigSaveFor = 'openai';
    await openai.getByLabel('OpenAI API key').fill('sk-failing-secret');
    await openai.getByRole('button', { name: 'Save OpenAI credential' }).click();
    await expect(openai.getByText('Failed to save OpenAI credential.')).toBeVisible();
    await expect(openai.getByLabel('OpenAI API key')).toHaveValue('sk-failing-secret');
    await expect(anthropic.getByText('Failed to save OpenAI credential.')).toHaveCount(0);
  });

  test('command palette search, tag search, and empty states render deterministic content', async ({
    page
  }) => {
    await page.goto(`/${vaultName}`);
    await page.waitForLoadState('networkidle').catch(() => {});

    await openCommandPalette(page);
    await page.locator('.cmdk-input').fill('research');
    await expect(page.getByRole('option', { name: /Research Note/ })).toBeVisible();
    await page.getByRole('option', { name: /Research Note/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/research-note$`));
    await expectNoteHeaderId(page, 'research-note');
    await expect(page.getByText('Linked neighbor content.')).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openCommandPalette(page);
    await page.locator('.cmdk-input').fill('neighbor');
    await expect(page.getByRole('option', { name: /Research Note/ })).toBeVisible();
    await expect(page.getByText('Linked neighbor content.')).toBeVisible();
    await page.getByRole('option', { name: /Research Note/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/research-note$`));
    await expect(page.getByText('Linked neighbor content.')).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openCommandPalette(page);
    await page.locator('.cmdk-input').fill('#work');
    await expect(page.getByRole('option', { name: /Project Plan/ })).toBeVisible();
    await page.getByRole('option', { name: /Project Plan/ }).click();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}/notes/project-plan$`));
    await expect(page.getByText(/Expected rendered markdown body/)).toBeVisible();
    await expectNoMissingPage(page);

    await page.goto(`/${vaultName}`);
    await openCommandPalette(page);
    await page.locator('.cmdk-input').fill('#missing-tag');
    await expect(page.getByText('No matches.')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/${vaultName}$`));
    await expectNoMissingPage(page);
  });
});

async function mockPkmApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = decodeURIComponent(url.pathname);

    if (path === '/api/v1/vaults') {
      await json(route, [
        { name: vaultName, path: '/tmp/alpha', is_default: false },
        { name: otherVaultName, path: '/tmp/beta', is_default: true }
      ]);
      return;
    }

    const listMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/notes$/);
    if (listMatch) {
      await json(route, listMatch[1] === otherVaultName ? betaNotes : notes);
      return;
    }

    const dailyMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/daily$/);
    if (dailyMatch) {
      await json(route, [
        {
          note_id: today,
          date: today,
          kind: 'daily',
          title: "Today's Daily",
          todo_count: 1,
          snippet: 'Today entry'
        },
        {
          note_id: `${today}-standup`,
          date: today,
          kind: 'subnote',
          title: 'Standup Subnote',
          todo_count: 0,
          snippet: 'Daily subnote content.'
        },
        {
          note_id: '2026-05-02',
          date: '2026-05-02',
          kind: 'daily',
          title: 'Yesterday',
          todo_count: 0,
          snippet: 'Yesterday entry'
        }
      ]);
      return;
    }

    const workflowListMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/workflows$/);
    if (workflowListMatch && route.request().method() === 'GET') {
      await json(
        route,
        Object.values(workflowConfigs).map(({ body, jitter_type, ...summary }) => summary)
      );
      return;
    }

    const workflowDetailMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/workflows\/([^/]+)$/
    );
    if (workflowDetailMatch) {
      const id = workflowDetailMatch[2];
      const workflow = workflowConfigs[id];
      if (!workflow) {
        await route.fulfill({ status: 404, body: 'not found' });
        return;
      }
      if (route.request().method() === 'PATCH') {
        const payload = route.request().postDataJSON() as {
          enabled?: boolean;
          trigger_time?: string;
          schedule_hour?: number;
        };
        const triggerTime =
          payload.trigger_time ??
          (typeof payload.schedule_hour === 'number'
            ? `${String(payload.schedule_hour).padStart(2, '0')}:00`
            : workflow.trigger_time);
        workflowConfigs[id] = {
          ...workflow,
          enabled: payload.enabled ?? workflow.enabled,
          trigger_time: triggerTime,
          schedule_hour: Number(triggerTime.slice(0, 2))
        };
        await json(route, workflowConfigs[id]);
        return;
      }
      await json(route, workflow);
      return;
    }

    const configsMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/configs$/);
    if (configsMatch && route.request().method() === 'GET') {
      configGetCount += 1;
      await json(route, configPayload());
      return;
    }

    const credentialMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/configs\/ask\/credentials\/([^/]+)$/
    );
    if (credentialMatch) {
      const providerId = credentialMatch[2];
      if (route.request().method() === 'PUT') {
        if (failNextConfigSaveFor === providerId) {
          failNextConfigSaveFor = '';
          await route.fulfill({ status: 500, body: 'save failed' });
          return;
        }
        configCredentialStatus[providerId] = {
          configured: true,
          fingerprint: `fp_${providerId}_saved`
        };
        await json(route, configProviderPayload(providerId));
        return;
      }
      if (route.request().method() === 'DELETE') {
        configCredentialStatus[providerId] = {
          configured: false,
          fingerprint: null
        };
        await json(route, configProviderPayload(providerId));
        return;
      }
    }

    const dailyDateMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/daily\/(\d{4}-\d{2}-\d{2})$/);
    if (dailyDateMatch) {
      const note = noteBodies[dailyDateMatch[2]];
      if (note) {
        await json(route, note);
      } else {
        await route.fulfill({ status: 404, body: 'not found' });
      }
      return;
    }

    const searchMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/search$/);
    if (searchMatch) {
      const vaultNotes = searchMatch[1] === otherVaultName ? betaNotes : notes;
      const q = url.searchParams.get('q')?.toLowerCase() ?? '';
      if (!q) {
        await route.fulfill({ status: 400, body: 'missing q' });
        return;
      }
      const results = vaultNotes
        .filter((note) => {
          const body = noteBodyFor(note.note_id);
          return [
            note.note_id,
            note.title,
            note.path,
            ...note.tags,
            body
          ].some((value) => value.toLowerCase().includes(q));
        })
        .map((note) => {
          const body = noteBodyFor(note.note_id);
          return {
            note_id: note.note_id,
            title: note.title,
            snippet: snippetFor(q, body) || note.path,
            score: 0.99
          };
        });
      await json(route, {
        query: q,
        count: results.length,
        results
      });
      return;
    }

    const tagMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/tags\/search$/);
    if (tagMatch) {
      const vaultNotes = tagMatch[1] === otherVaultName ? betaNotes : notes;
      const pattern = url.searchParams.get('pattern')?.toLowerCase() ?? '';
      const results = vaultNotes.filter((note) =>
        note.tags.some((tag) => tag.toLowerCase().includes(pattern))
      );
      await json(route, {
        pattern,
        mode: 'glob',
        count: results.length,
        results
      });
      return;
    }

    const tagListMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/tags$/);
    if (tagListMatch) {
      const vaultNotes = tagListMatch[1] === otherVaultName ? betaNotes : notes;
      const counts = new Map<string, number>();
      for (const note of vaultNotes) {
        for (const tag of note.tags) {
          counts.set(tag, (counts.get(tag) ?? 0) + 1);
        }
      }
      await json(route, {
        tags: Array.from(counts.entries()).map(([tag, count]) => ({ tag, count })),
        count: counts.size
      });
      return;
    }

    const askOptionsMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/ask\/options$/);
    if (askOptionsMatch) {
      await json(route, {
        model: 'auto',
        resolved_model: 'test/default-model',
        reasoning_effort: 'medium'
      });
      return;
    }

    const askMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/ask$/);
    if (askMatch && route.request().method() === 'POST') {
      const payload = route.request().postDataJSON() as {
        query?: string;
        context?: string;
        ask_session_id?: string;
      };
      askPayloads.push(payload);
      await sse(route, payload.query ?? '');
      return;
    }

    const graphMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/graph$/);
    if (graphMatch) {
      await json(route, graphFixture);
      return;
    }

    const dailyTodayMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/daily\/today$/);
    if (dailyTodayMatch) {
      if (route.request().method() === 'GET') {
        await json(route, noteBodies[today]);
        return;
      }
      if (route.request().method() === 'POST') {
        const payload = route.request().postDataJSON() as { content?: string; type?: string };
        const content = payload.content ?? '';
        await json(route, { entry: `- [16:45:12] ${content}\n` }, 201);
        return;
      }
    }

    const graphEgoMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/graph\/ego\/(.+)$/
    );
    if (graphEgoMatch) {
      const id = graphEgoMatch[2];
      await json(route, {
        nodes: [
          { id, title: String(id) },
          { id: 'research-note', title: 'Research Note' }
        ],
        links: [{ source: id, target: 'research-note' }]
      });
      return;
    }

    const neighborMatch = path.match(
      /^\/api\/v1\/vault\/([^/]+)\/notes\/(.+)\/neighbors$/
    );
    if (neighborMatch) {
      const id = neighborMatch[2];
      if (id === 'tag:pkm') {
        await json(route, {
          note_id: id,
          outbound: [],
          inbound: [
            {
              note_id: 'project-plan',
              title: 'Project Plan',
              type: 'note',
              description: 'Project coordination summary and next actions.'
            },
            {
              note_id: 'research-note',
              title: 'Research Note',
              type: 'note',
              description: 'Research backlink context and related notes.'
            }
          ],
          semantic: []
        });
        return;
      }
      await json(route, {
        note_id: id,
        outbound: [
          {
            note_id: 'research-note',
            title: 'Research Note',
            type: 'wikilink',
            description: 'Research backlink context and related notes.'
          }
        ],
        inbound: [],
        semantic: [
          {
            note_id: 'project-plan',
            title: 'Project Plan',
            type: 'semantic',
            confidence: 0.91,
            description: 'Project coordination summary and next actions.'
          }
        ]
      });
      return;
    }

    const noteMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/notes\/(.+)$/);
    if (noteMatch) {
      const id = noteMatch[2];
      if (id.endsWith('/ensure') && route.request().method() === 'POST') {
        const ensuredId = id.replace(/\/ensure$/, '');
        const created = {
          note_id: ensuredId,
          title: ensuredId.replace(/-/g, ' '),
          body: '',
          frontmatter: { id: ensuredId, title: ensuredId.replace(/-/g, ' '), tags: [] },
          created: null,
          updated: null,
          tags: [],
          importance: null
        };
        noteBodies[ensuredId] = created;
        await json(route, created, 201);
        return;
      }
      if (/^\d{4}-\d{2}-\d{2}$/.test(id)) {
        await route.fulfill({ status: 404, body: 'not found' });
        return;
      }
      const note = noteBodies[id];
      if (note) {
        if (route.request().method() === 'PUT') {
          const payload = route.request().postDataJSON() as { body?: string };
          if (note && typeof note === 'object' && 'body' in note) {
            noteBodies[id] = {
              ...note,
              body: payload.body ?? String((note as { body?: unknown }).body ?? '')
            };
          }
          await json(route, noteBodies[id]);
          return;
        }
        await json(route, note);
      } else {
        await route.fulfill({ status: 404, body: 'not found' });
      }
      return;
    }

    await route.fulfill({ status: 404, body: `Unhandled mock route: ${path}` });
  });
}

async function expectCommandPaletteFocused(page: Page) {
  await expect(
    page.locator('[role="dialog"][aria-label="Command palette"]')
  ).toBeVisible();
  await expect(page.locator('.cmdk-input')).toBeFocused();
}

async function openCommandPalette(page: Page) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await expect(page.getByRole('button', { name: 'Open command palette' })).toBeVisible();
  await page.getByRole('button', { name: 'Open command palette' }).click();
  await expectCommandPaletteFocused(page);
}

async function expectNoteHeaderId(page: Page, noteId: string) {
  const noteHeader = page.locator('.note-header');
  await expect(noteHeader.locator('.meta-rail')).toContainText('NOTE');
  await expect(noteHeader.locator('.meta-rail')).toContainText(noteId);
  await expect(noteHeader.getByRole('heading')).toHaveCount(0);
}

async function expectTopbar(page: Page, vault: string, pageName: string) {
  const topbar = page.locator('.topbar');
  await expect(topbar.getByText(vault, { exact: true })).toBeVisible();
  await expect(topbar.getByText(pageName, { exact: true })).toBeVisible();
  await expect(topbar.getByText('station', { exact: true })).toHaveCount(0);
  await expect(topbar.getByText('signal desk', { exact: true })).toHaveCount(0);
  await expect(topbar.getByText(/vim:/)).toHaveCount(0);
}

async function expectNoMissingPage(
  page: Page,
  options: { allowTagNotFound?: boolean } = {}
) {
  await expect(page.getByText(/^404$/)).toHaveCount(0);
  if (!options.allowTagNotFound) {
    await expect(page.getByText(/not found/i)).toHaveCount(0);
  }
}

function noteBodyFor(noteId: string): string {
  const note = noteBodies[noteId];
  if (note && typeof note === 'object' && 'body' in note) {
    return String((note as { body?: unknown }).body ?? '');
  }
  return '';
}

function resetMockNotes() {
  const projectNote = noteBodies['project-plan'];
  if (projectNote && typeof projectNote === 'object') {
    noteBodies['project-plan'] = {
      ...projectNote,
      body: projectPlanBody
    };
  }
  const longNote = noteBodies['long-content'];
  if (longNote && typeof longNote === 'object') {
    noteBodies['long-content'] = {
      ...longNote,
      body: longContentBody
    };
  }
}

function resetMockWorkflows() {
  workflowConfigs = {
    zettelkasten_maintenance: {
      id: 'zettelkasten_maintenance',
      title: 'zettelkasten maintenance',
      schedule_hour: 2,
      trigger_time: '02:00',
      enabled: true,
      marker_file: 'zettel-last-run',
      pre_hook: null,
      post_hook: null,
      snippet: 'Execute the maintenance workflow.',
      body: workflowBodies.zettelkasten_maintenance,
      jitter_type: 'md5_hostname'
    },
    daily_task_summary: {
      id: 'daily_task_summary',
      title: 'daily task summary',
      schedule_hour: 8,
      trigger_time: '08:00',
      enabled: true,
      marker_file: 'summary-last-run',
      pre_hook: 'pkm.workflows.hooks:build_daily_summary',
      post_hook: null,
      snippet: "Create today's task summary subnote using create_daily_subnote.",
      body: workflowBodies.daily_task_summary,
      jitter_type: 'md5_hostname_suffix:summary'
    }
  };
}

function resetMockConfigs() {
  configCredentialStatus = {
    openai: {
      configured: false,
      fingerprint: null
    },
    anthropic: {
      configured: true,
      fingerprint: 'fp_existing'
    }
  };
}

function configPayload() {
  return {
    ask_credentials: {
      providers: [
        {
          id: 'openai',
          label: 'OpenAI',
          env_key: 'OPENAI_API_KEY',
          ...configCredentialStatus.openai
        },
        {
          id: 'anthropic',
          label: 'Anthropic',
          env_key: 'ANTHROPIC_API_KEY',
          ...configCredentialStatus.anthropic
        }
      ]
    }
  };
}

function configProviderPayload(providerId: string) {
  const providers = configPayload().ask_credentials.providers;
  return providers.find((provider) => provider.id === providerId) ?? providers[0];
}

function snippetFor(query: string, body: string): string {
  const foldedQuery = query.toLowerCase();
  const match = body
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line && line.toLowerCase().includes(foldedQuery));
  return match ?? '';
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body)
  });
}

async function sse(route: Route, query: string) {
  const safeQuery = query || 'empty query';
  if (safeQuery === 'slow animation check') {
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
  if (safeQuery === 'route carry check') {
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }
  if (safeQuery === 'result payload') {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: reasoning',
        `data: ${JSON.stringify({ type: 'reasoning', content: `Reasoning for ${safeQuery}` })}`,
        '',
        'event: result',
        `data: ${JSON.stringify({ response: `Response-only answer for ${safeQuery}` })}`,
        '',
        ''
      ].join('\n')
    });
    return;
  }
  const answer =
    safeQuery === 'markdown check'
      ? [
          '## Markdown reply',
          '',
          '**bold answer** with `inline_code`.',
          '',
          '- First item',
          '- Second item',
          '',
          '[reference link](https://example.com)'
        ].join('\n')
      : safeQuery === 'rendering check'
        ? `Answer for ${safeQuery} ${longToken}`
        : `Answer for ${safeQuery}`;
  await route.fulfill({
    status: 200,
    contentType: 'text/event-stream',
    body: [
      'event: reasoning',
      `data: ${JSON.stringify({ type: 'reasoning', text: `Reasoning for ${safeQuery}` })}`,
      '',
      ...(safeQuery === 'manage tasks check'
        ? [
            'event: tool_call',
            `data: ${JSON.stringify({
              type: 'tool_call',
              name: 'manage_tasks',
              arguments: {
                tasks: JSON.stringify([
                  { text: 'Review workflow schedule', status: 'done' },
                  { text: 'Write regression test', status: 'pending' },
                  { text: 'Run task parser', status: 'in_progress' }
                ])
              }
            })}`,
            ''
          ]
        : []),
      'event: tool_call',
      `data: ${JSON.stringify({ type: 'tool_call', name: 'search', arguments: { q: safeQuery } })}`,
      '',
      'event: task',
      `data: ${JSON.stringify({ type: 'task', text: `Queued ${safeQuery}` })}`,
      '',
      'event: content',
      `data: ${JSON.stringify({ type: 'content', text: answer })}`,
      '',
      'event: result',
      `data: ${JSON.stringify({ answer: `Final answer for ${safeQuery}` })}`,
      '',
      ''
    ].join('\n')
  });
}
