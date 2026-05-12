// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { mount, tick, unmount } from "svelte";
import MarkdownRenderer from "./MarkdownRenderer.svelte";

describe("MarkdownRenderer", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  async function waitFor(assertion: () => void | Promise<void>) {
    let lastError: unknown;
    for (let i = 0; i < 20; i += 1) {
      try {
        await assertion();
        return;
      } catch (error) {
        lastError = error;
        await Promise.resolve();
        await new Promise((resolve) => setTimeout(resolve, 0));
        await tick();
      }
    }
    throw lastError;
  }

  it("renders markdown, wikilinks, tags, and relation markers as decorated HTML", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const component = mount(MarkdownRenderer, {
      target,
      props: {
        vault: "main vault",
        markdown:
          "## Heading\n\nSee **bold** [[Target Note]] #pkm &depends_on [[Other]].",
      },
    });

    await waitFor(() => {
      expect(target.querySelector("h2")?.textContent).toBe("Heading");
    });

    expect(target.querySelector("strong")?.textContent).toBe("bold");
    expect(
      target.querySelector<HTMLAnchorElement>(
        'a[href="/main%20vault/notes/Target%20Note"]',
      )?.textContent,
    ).toBe("Target Note");
    expect(target.querySelector(".note-tag-chip")?.textContent).toBe("#pkm");
    expect(target.querySelector(".note-relation-chip")?.textContent).toBe(
      "&depends_on",
    );

    unmount(component);
  });
});
