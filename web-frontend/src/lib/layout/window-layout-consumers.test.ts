import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function readSource(relativePath: string) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), {
    encoding: "utf-8",
  });
}

describe("window layout CSS consumers", () => {
  it("defines fallback layout tokens before vault config loads", () => {
    const tokens = readSource("../styles/tokens.css");

    expect(tokens).toContain("--window-padding-raw: 32px");
    expect(tokens).toContain("--page-content-width");
    expect(tokens).toContain("--readable-content-width");
    expect(tokens).toContain("--modal-available-width");
  });

  it("uses shared page width tokens for page shells", () => {
    const pageFiles = [
      "../../routes/[vault]/+page.svelte",
      "../../routes/[vault]/configs/+page.svelte",
      "../../routes/[vault]/logger/+page.svelte",
      "../../routes/[vault]/notes/[id]/+page.svelte",
    ];

    for (const file of pageFiles) {
      expect(readSource(file)).toContain("width: var(--page-content-width)");
    }
  });

  it("uses readable and modal width tokens where pages need narrower surfaces", () => {
    expect(readSource("../../routes/[vault]/tags/+page.svelte")).toContain(
      "width: var(--readable-content-width)",
    );
    expect(readSource("../../lib/components/CmdK.svelte")).toContain(
      "var(--modal-available-width)",
    );
  });

  it("keeps graph page opted out of centered page width constraints", () => {
    expect(readSource("../../routes/[vault]/graph/+page.svelte")).not.toContain(
      "--page-content-width",
    );
  });
});
