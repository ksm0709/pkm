import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("PdfViewer styles", () => {
  it("aligns zoomed PDF pages from the scrollable left edge while centering fit pages", () => {
    const source = readFileSync("src/lib/data-viewer/PdfViewer.svelte", "utf8");
    const pagesRule = source.match(/\.pdf-pages\s*\{(?<body>[\s\S]*?)\n  \}/)
      ?.groups?.body;
    const pageRule = source.match(
      /\.pdf-pages :global\(\.pdf-page\)\s*\{(?<body>[\s\S]*?)\n  \}/,
    )?.groups?.body;

    expect(pagesRule).toContain("align-items: flex-start");
    expect(pagesRule).not.toContain("align-items: center");
    expect(pageRule).toContain("margin-inline: auto");
  });

  it("uses non-layout-affecting chrome around PDF pages so fit zoom can show the full page", () => {
    const source = readFileSync("src/lib/data-viewer/PdfViewer.svelte", "utf8");
    const pageRule = source.match(
      /\.pdf-pages :global\(\.pdf-page\)\s*\{(?<body>[\s\S]*?)\n  \}/,
    )?.groups?.body;

    expect(pageRule).toContain("outline: 1px solid var(--border)");
    expect(pageRule).not.toContain("border:");
  });

  it("prevents the annotations panel from shrinking behind the PDF scrollport", () => {
    const source = readFileSync("src/lib/data-viewer/PdfViewer.svelte", "utf8");
    const panelRule = source.match(
      /\.pdf-annotations-panel\s*\{(?<body>[\s\S]*?)\n  \}/,
    )?.groups?.body;
    const pagesRule = source.match(/\.pdf-pages\s*\{(?<body>[\s\S]*?)\n  \}/)
      ?.groups?.body;

    expect(panelRule).toContain("box-sizing: border-box");
    expect(panelRule).toContain("flex: 0 0 auto");
    expect(panelRule).toContain("position: relative");
    expect(panelRule).toContain("z-index: 2");
    expect(pagesRule).toContain("flex: 1 1 0");
    expect(pagesRule).toContain("position: relative");
    expect(pagesRule).toContain("z-index: 1");
  });
});
