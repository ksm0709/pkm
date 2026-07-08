import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";

describe("service worker lifecycle", () => {
  it("immediately activates and claims clients so installed PWAs do not keep stale app shells", async () => {
    const source = await readFile("src/service-worker.ts", "utf8");

    expect(source).toContain("skipWaiting");
    expect(source).toContain("clients.claim");
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
