import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";

describe("service worker lifecycle", () => {
  it("does not immediately take over a running installed PWA", async () => {
    const source = await readFile("src/service-worker.ts", "utf8");

    expect(source).not.toContain("skipWaiting");
    expect(source).not.toContain("clients.claim");
  });
});
