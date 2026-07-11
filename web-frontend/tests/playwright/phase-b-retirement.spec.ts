import { expect, test, type Page, type Route } from "@playwright/test";

const vaultName = "alpha";
const staleSessionKey = `pkm.askSession.${vaultName}`;
const staleSessionValue = JSON.stringify({
  sessionId: "legacy-session",
  transcript: [{ role: "user", content: "legacy prompt" }],
});

function isRetiredApiPath(pathname: string): boolean {
  return (
    /\/(?:ask|workflows|workflow-history)(?:\/|$)/.test(pathname) ||
    /\/(?:credentials|ask_credentials)(?:\/|$)/.test(pathname)
  );
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockRetainedApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = decodeURIComponent(url.pathname);

    if (path === "/api/v1/vaults") {
      await json(route, [{ name: vaultName, path: "/tmp/alpha" }]);
      return;
    }
    if (path === `/api/v1/vault/${vaultName}/notes`) {
      await json(route, []);
      return;
    }
    if (path === `/api/v1/vault/${vaultName}/search`) {
      await json(route, { results: [], graph_ready: true });
      return;
    }
    if (path === `/api/v1/vault/${vaultName}/configs`) {
      await json(route, {
        settings: [
          {
            key: "model",
            section: "defaults",
            internal_key: "model",
            description: "Legacy model setting",
            value: "auto",
            default_value: "auto",
            configured: false,
            source: "default",
            input_type: "select",
            options: ["auto"],
          },
          {
            key: "reasoning-effort",
            section: "defaults",
            internal_key: "reasoning_effort",
            description: "Legacy reasoning setting",
            value: "medium",
            default_value: "medium",
            configured: false,
            source: "default",
            input_type: "select",
            options: ["medium"],
          },
          {
            key: "web-window-padding",
            section: "web",
            internal_key: "window_padding",
            description: "Web window padding",
            value: "32",
            default_value: "32",
            configured: false,
            source: "default",
            input_type: "number",
            options: [],
          },
        ],
        ask_credentials: {
          providers: [{ id: "legacy", configured: true }],
        },
      });
      return;
    }

    await route.fulfill({
      status: 404,
      body: `Unhandled retained mock: ${path}`,
    });
  });
}

test.describe("Phase B retired Ask and Workflow surfaces", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(
      ({ key, value }) => localStorage.setItem(key, value),
      { key: staleSessionKey, value: staleSessionValue },
    );
    await mockRetainedApi(page);
  });

  test("retired routes render the missing-page state without retired API calls", async ({
    page,
  }) => {
    const retiredApiRequests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/") && isRetiredApiPath(url.pathname)) {
        retiredApiRequests.push(url.pathname);
      }
    });

    for (const path of [
      `/${vaultName}/ask`,
      `/${vaultName}/workflows`,
      `/${vaultName}/workflows/legacy-id`,
      `/${vaultName}/workflow-history`,
    ]) {
      await page.goto(path);
      await expect(page.getByText(/^404$/)).toBeVisible();
      await expect(page.getByText(/not found/i)).toBeVisible();
    }

    expect(retiredApiRequests).toEqual([]);
  });

  test("retained shell ignores stale Ask state and exposes no retired destinations", async ({
    page,
  }) => {
    const retiredApiRequests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname.startsWith("/api/") && isRetiredApiPath(url.pathname)) {
        retiredApiRequests.push(url.pathname);
      }
    });

    await page.goto(`/${vaultName}`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await expect(
      page.getByRole("button", { name: "Open navigation drawer" }),
    ).toBeVisible();
    const drawer = page.locator('aside[aria-label="App navigation"]');
    if ((await drawer.getAttribute("aria-hidden")) === "true") {
      await page
        .getByRole("button", { name: "Open navigation drawer" })
        .click();
    }
    await expect(drawer).toHaveAttribute("aria-hidden", "false");
    const navigation = drawer.locator("nav");
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole("button", { name: /Ask/i })).toHaveCount(
      0,
    );
    await expect(
      navigation.getByRole("button", { name: /Workflow/i }),
    ).toHaveCount(0);

    await page.getByRole("button", { name: "Open command palette" }).click();
    await page.locator(".cmdk-input").fill("ask");
    await expect(page.getByRole("option", { name: /Ask/i })).toHaveCount(0);
    await page.locator(".cmdk-input").fill("workflow");
    await expect(page.getByRole("option", { name: /Workflow/i })).toHaveCount(
      0,
    );
    await page.locator(".cmdk-input").press("Escape");

    await page.goto(`/${vaultName}/configs`);
    await expect(
      page.locator('input[aria-label="web-window-padding value"]'),
    ).toHaveValue("32");
    await expect(page.locator('[data-setting-key="model"]')).toHaveCount(0);
    await expect(
      page.locator('[data-setting-key="reasoning-effort"]'),
    ).toHaveCount(0);
    await expect(page.locator(".ask-credentials")).toHaveCount(0);

    expect(
      await page.evaluate((key) => localStorage.getItem(key), staleSessionKey),
    ).toBe(staleSessionValue);
    expect(retiredApiRequests).toEqual([]);
  });
});
