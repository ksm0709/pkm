// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { decorateRenderedHtml, renderMarkdownHtml } from "./rendered-markdown";

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

  it("wraps rendered markdown tables for horizontal scrolling", async () => {
    const rendered = await renderMarkdownHtml(
      [
        "| Column | Wide notes |",
        "| --- | --- |",
        "| A | long table content with spaces that should stay on one row<br>explicit break |",
      ].join("\n"),
      "main",
    );
    const host = document.createElement("div");
    host.innerHTML = rendered;

    const wrapper = host.querySelector<HTMLElement>(".markdown-table-scroll");
    const table = wrapper?.querySelector("table");
    const cell = wrapper?.querySelector("td:nth-child(2)");

    expect(wrapper).not.toBeNull();
    expect(table).not.toBeNull();
    expect(cell?.textContent).toContain(
      "long table content with spaces that should stay on one row",
    );
    expect(cell?.innerHTML).toContain("<br>");
  });

  it("rewrites renderable data-file links to the safe viewer route", async () => {
    const rendered = await renderMarkdownHtml(
      [
        "[human md](/taeho/data/reports/deep.md)",
        "[api html](/api/v1/vault/taeho/data/reports/company%20page.html#summary)",
        "[pdf](/taeho/data/reports/raw.pdf)",
        "[external](https://example.com/taeho/data/reports/deep.md)",
      ].join("\n\n"),
      "taeho",
    );
    const host = document.createElement("div");
    host.innerHTML = rendered;

    expect(
      host.querySelector<HTMLAnchorElement>('a[href="/taeho/view-data/reports/deep.md"]')
        ?.textContent,
    ).toBe("human md");
    expect(
      host.querySelector<HTMLAnchorElement>(
        'a[href="/taeho/view-data/reports/company%20page.html#summary"]',
      )?.textContent,
    ).toBe("api html");
    expect(
      host.querySelector<HTMLAnchorElement>('a[href="/taeho/data/reports/raw.pdf"]')
        ?.textContent,
    ).toBe("pdf");
    expect(
      host.querySelector<HTMLAnchorElement>(
        'a[href="https://example.com/taeho/data/reports/deep.md"]',
      )?.textContent,
    ).toBe("external");
  });

  it("strips active HTML from rendered markdown", async () => {
    const rendered = await renderMarkdownHtml(
      [
        "<script>alert('xss')</script>",
        '<img src="/api/v1/vault/main/data/photo.png" onerror="alert(\'xss\')">',
        '<a href="javascript:alert(1)">bad</a>',
        '<a href="/main/notes/Safe">good</a>',
      ].join("\n"),
      "main",
    );
    const host = document.createElement("div");
    host.innerHTML = rendered;

    expect(host.querySelector("script")).toBeNull();
    expect(host.querySelector("[onerror]")).toBeNull();
    expect(host.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(host.querySelector("img")?.getAttribute("src")).toBe(
      "/api/v1/vault/main/data/photo.png",
    );
    expect(
      host.querySelector<HTMLAnchorElement>('a[href="/main/notes/Safe"]'),
    ).not.toBeNull();
  });
});
