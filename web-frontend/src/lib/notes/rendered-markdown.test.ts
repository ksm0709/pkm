// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { decorateRenderedHtml } from "./rendered-markdown";

describe("rendered markdown decoration", () => {
  it("renders relation vocabulary markers as square chips next to wikilinks", () => {
    const html =
      '<p>&depends_on <a href="/main/notes/target">Target</a> and #pkm [raw]</p>';

    const decorated = decorateRenderedHtml(html, "main");
    const host = document.createElement("div");
    host.innerHTML = decorated;

    const relation = host.querySelector<HTMLElement>(".note-relation-chip");
    const tag = host.querySelector<HTMLAnchorElement>(".note-tag-chip");
    const link = host.querySelector<HTMLAnchorElement>(
      'a[href="/main/notes/target"]',
    );

    expect(relation?.textContent).toBe("&depends_on");
    expect(relation?.dataset.relation).toBe("depends_on");
    expect(tag?.textContent).toBe("#pkm");
    expect(tag?.getAttribute("href")).toBe("/main/notes/tag%3Apkm");
    expect(link?.textContent).toBe("Target");
    expect(host.querySelector(".note-bracket-highlight")?.textContent).toBe(
      "[raw]",
    );
  });

  it("does not decorate relation-looking text in code or embedded words", () => {
    const html =
      "<p>R&amp;D and foo&amp;bar stay text.</p><pre>&source [[raw]] #tag</pre>";

    const decorated = decorateRenderedHtml(html, "main");
    const host = document.createElement("div");
    host.innerHTML = decorated;

    expect(host.querySelector(".note-relation-chip")).toBeNull();
    expect(host.querySelector(".note-tag-chip")).toBeNull();
    expect(host.querySelector("pre")?.textContent).toBe("&source [[raw]] #tag");
    expect(host.textContent).toContain("R&D");
    expect(host.textContent).toContain("foo&bar");
  });
});
