import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("PdfViewer styles", () => {
  it("uses non-layout-affecting chrome around PDF pages so fit zoom can show the full page", () => {
    const source = readFileSync("src/lib/data-viewer/PdfViewer.svelte", "utf8");
    const pageRule = source.match(
      /\.pdf-pages :global\(\.pdf-page\)\s*\{(?<body>[\s\S]*?)\n  \}/,
    )?.groups?.body;

    expect(pageRule).toContain("outline: 1px solid var(--border)");
    expect(pageRule).not.toContain("border:");
  });
});
