import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { applyTheme, themeFromProject } from './fixtures/theme';

/**
 * Slice 4 a11y gate.
 *
 * For each project (chromium-light, chromium-dark) verify:
 *   1. Vault note view passes axe WCAG 2.1 AA with zero violations.
 *   2. Body paragraph contrast in BOTH editor render states:
 *      (a) cursor on the line — raw markdown shown in --text-faint.
 *      (b) cursor off the line — styled body text.
 *      Both must satisfy AA.
 */

test.describe('accessibility (WCAG 2.1 AA)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await applyTheme(page, themeFromProject(testInfo.project.name));
  });

  test('vault note view has no AA violations', async ({ page }) => {
    await page.goto('/');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });

  test('body paragraph contrast holds in cursor-on and cursor-off states', async ({
    page
  }) => {
    await page.goto('/');

    const editor = page.locator('[contenteditable="true"], .cm-content').first();
    const hasEditor = await editor.count();
    test.skip(!hasEditor, 'editor not present in this build');

    // (a) cursor ON line — raw markdown rendered in --text-faint.
    await editor.click();
    const onLineResults = await new AxeBuilder({ page })
      .withTags(['wcag2aa', 'wcag21aa'])
      .include('.cm-content, [contenteditable="true"]')
      .analyze();
    const onContrastViolations = onLineResults.violations.filter((v) =>
      v.id.includes('color-contrast')
    );
    expect(onContrastViolations).toEqual([]);

    // (b) cursor OFF line — move focus away so styled rendering kicks in.
    await page.keyboard.press('Escape');
    await page.locator('body').click({ position: { x: 0, y: 0 } });
    const offLineResults = await new AxeBuilder({ page })
      .withTags(['wcag2aa', 'wcag21aa'])
      .include('.cm-content, [contenteditable="true"]')
      .analyze();
    const offContrastViolations = offLineResults.violations.filter((v) =>
      v.id.includes('color-contrast')
    );
    expect(offContrastViolations).toEqual([]);
  });
});
