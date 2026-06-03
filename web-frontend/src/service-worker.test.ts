import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";

describe("service worker lifecycle", () => {
  it("does not immediately take over a running installed PWA", async () => {
    const source = await readFile("src/service-worker.ts", "utf8");

    expect(source).not.toContain("skipWaiting");
    expect(source).not.toContain("clients.claim");
  });
});

describe("service worker routing", () => {
  it("bypasses vault data compatibility routes so authenticated files are not cached", async () => {
    const source = await readFile("src/service-worker.ts", "utf8");

    expect(source).toContain("isVaultDataRoute");
    expect(source).toContain("url.pathname");
    expect(source).toContain("return /^\\/[^/]+\\/data\\/.+/.test(pathname);");
  });
});
