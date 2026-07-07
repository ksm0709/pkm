import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("ScrollPositionOverlay styles", () => {
  it("renders as a non-interactive translucent right-side overlay", () => {
    const source = readFileSync(
      "src/lib/components/ScrollPositionOverlay.svelte",
      "utf8",
    );
    const overlayRule = source.match(
      /\.scroll-position-overlay\s*\{(?<body>[\s\S]*?)\n  \}/,
    )?.groups?.body;

    expect(overlayRule).toContain("position: fixed");
    expect(overlayRule).toContain("right:");
    expect(overlayRule).toContain("background: color-mix");
    expect(overlayRule).toContain("transparent");
    expect(overlayRule).toContain("pointer-events: none");
    expect(overlayRule).toContain("z-index: 30");
  });
});
