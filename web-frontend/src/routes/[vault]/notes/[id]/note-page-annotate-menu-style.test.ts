import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("note page annotate menu styling", () => {
  it("styles the annotate action as a high-contrast accent button", () => {
    const source = readFileSync(
      "src/routes/[vault]/notes/[id]/+page.svelte",
      "utf8",
    );
    const buttonRule =
      source.match(/\.annotate-menu button\s*\{(?<body>[\s\S]*?)\n  \}/)?.groups
        ?.body ?? "";

    const hoverRule =
      source.match(
        /\.annotate-menu button:hover,\n  \.annotate-menu button:focus-visible\s*\{(?<body>[\s\S]*?)\n  \}/,
      )?.groups?.body ?? "";

    expect(buttonRule).toContain("background: var(--accent)");
    expect(buttonRule).toContain("color: var(--annotate-action-text)");
    expect(buttonRule).toContain("font-weight: 700");
    expect(hoverRule).toContain("background: var(--accent)");
    expect(hoverRule).toContain("color: var(--annotate-action-text)");
    expect(hoverRule).not.toMatch(
      /background:\s*color-mix\(in srgb, var\(--accent\)/,
    );
  });
});
