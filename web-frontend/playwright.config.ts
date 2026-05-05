import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for pkm-webapp Slice 4 quality gates.
 *
 * Two projects render the SPA in light + dark mode. Both projects rely on
 * the `applyTheme` fixture (tests/playwright/fixtures/theme.ts) to inject
 * `document.documentElement.dataset.theme` before page scripts run.
 */
export default defineConfig({
  testDir: 'tests/playwright',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry'
  },
  projects: [
    {
      name: 'chromium-light',
      use: { ...devices['Desktop Chrome'], colorScheme: 'light' }
    },
    {
      name: 'chromium-dark',
      use: { ...devices['Desktop Chrome'], colorScheme: 'dark' }
    }
  ],
  webServer: {
    command: 'VITE_PKM_GRAPH_TEST_API=1 pnpm dev',
    url: process.env.BASE_URL || 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
});
