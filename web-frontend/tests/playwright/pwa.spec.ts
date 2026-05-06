import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test.describe('PWA installability contract', () => {
  test('serves a web app manifest with install metadata and icons', async ({ request }) => {
    const response = await request.get('/manifest.webmanifest');
    expect(response.ok()).toBe(true);
    expect(response.headers()['content-type']).toContain('application/manifest+json');

    const manifest = await response.json();
    expect(manifest.name).toBe('pkm');
    expect(manifest.short_name).toBe('pkm');
    expect(manifest.start_url).toBe('/');
    expect(manifest.scope).toBe('/');
    expect(manifest.display).toBe('standalone');
    expect(manifest.orientation).toBe('portrait');
    expect(manifest.theme_color).toBe('#090b0d');
    expect(manifest.background_color).toBe('#090b0d');
    expect(manifest.icons).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          src: '/icons/pwa-192.png',
          sizes: '192x192',
          type: 'image/png',
          purpose: expect.stringContaining('maskable')
        }),
        expect.objectContaining({
          src: '/icons/pwa-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: expect.stringContaining('maskable')
        })
      ])
    );
  });

  test('document head advertises install metadata', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
      'href',
      '/manifest.webmanifest'
    );
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute(
      'content',
      '#090b0d'
    );
    await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
      'href',
      '/icons/pwa-192.png'
    );

    const registrationScript = await page.locator('script').evaluateAll((scripts) =>
      scripts.some((script) => script.textContent?.includes('service-worker.js'))
    );
    expect(registrationScript).toBe(true);
  });

  test('emits a service worker that caches the app shell and static assets', async ({
    request
  }) => {
    const response = await request.get('/service-worker.js');
    expect(response.ok()).toBe(true);
    expect(response.headers()['content-type']).toContain('javascript');

    const source = await response.text();
    expect(source).toContain('pkm-webapp');
    expect(source).toMatch(/service-worker\.ts|install/);

    const sourceFile = await readFile('src/service-worker.ts', 'utf8');
    expect(sourceFile).toContain('pkm-webapp');
    expect(sourceFile).toContain('install');
    expect(sourceFile).toContain('activate');
    expect(sourceFile).toContain('fetch');
    expect(sourceFile).toContain('manifest.webmanifest');
    expect(sourceFile).toContain('/icons/pwa-192.png');
  });

  test('keeps the app icon as a radial node graph without text', async () => {
    const source = await readFile('static/icons/pkm-node-graph.svg', 'utf8');

    expect(source).toContain('aria-label="PKM node graph icon"');
    expect(source).not.toMatch(/<text\b/i);
    expect(source.match(/<circle\b/g)?.length ?? 0).toBeGreaterThanOrEqual(6);
  });

  test('requests portrait orientation lock when supported', async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window.screen, 'orientation', {
        configurable: true,
        value: {
          lock: async (orientation: string) => {
            (window as typeof window & { __orientationLockCalls: string[] })
              .__orientationLockCalls.push(orientation);
          }
        }
      });
      (window as typeof window & { __orientationLockCalls: string[] }).__orientationLockCalls = [];
    });

    await page.goto('/');

    await expect
      .poll(() =>
        page.evaluate(
          () => (window as typeof window & { __orientationLockCalls: string[] }).__orientationLockCalls
        )
      )
      .toEqual(['portrait']);
  });
});
