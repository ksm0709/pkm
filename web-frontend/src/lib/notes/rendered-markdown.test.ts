// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  decorateRenderedHtml,
  renderMarkdownHtml,
  sanitizeRenderedHtml,
} from "./rendered-markdown";

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

  it("preserves safe inline SVG while stripping active SVG content", async () => {
    const rendered = await renderMarkdownHtml(
      [
        '<svg viewBox="0 0 10 10" role="img" aria-label="demo" onload="alert(1)">',
        "<title>Demo diagram</title>",
        '<path d="M1 1h8v8H1z" fill="currentColor" onclick="alert(1)"></path>',
        '<a href="javascript:alert(1)"><text>bad link</text></a>',
        "<script>alert('xss')</script>",
        "</svg>",
      ].join(""),
      "main",
    );
    const host = document.createElement("div");
    host.innerHTML = rendered;

    const svg = host.querySelector<SVGSVGElement>("svg");
    const path = host.querySelector<SVGPathElement>("svg path");

    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("viewBox")).toBe("0 0 10 10");
    expect(svg?.getAttribute("role")).toBe("img");
    expect(svg?.getAttribute("aria-label")).toBe("demo");
    expect(svg?.querySelector("title")?.textContent).toBe("Demo diagram");
    expect(path?.getAttribute("d")).toBe("M1 1h8v8H1z");
    expect(path?.getAttribute("fill")).toBe("currentColor");
    expect(host.querySelector("[onload], [onclick], script")).toBeNull();
    expect(host.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it("preserves Mermaid-style SVG markers and text attributes safely", () => {
    const sanitized = sanitizeRenderedHtml(
      [
        '<svg viewBox="0 0 100 40">',
        '<defs><marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">',
        '<path d="M0,0 L10,3.5 L0,7 Z" fill="currentColor"></path>',
        "</marker></defs>",
        '<g class="edgePath"><path d="M10 20L90 20" marker-end="url(#arrowhead)" stroke="currentColor"></path></g>',
        '<path d="M0 0" marker-end="url(https://evil.example/marker)"></path>',
        '<text x="50" y="20" text-anchor="middle" dominant-baseline="central" font-family="sans-serif" font-size="16">Node</text>',
        "</svg>",
      ].join(""),
    );
    const host = document.createElement("div");
    host.innerHTML = sanitized;

    expect(host.querySelector("defs marker#arrowhead path")).not.toBeNull();
    expect(
      host
        .querySelector<SVGPathElement>("g.edgePath path")
        ?.getAttribute("marker-end"),
    ).toBe("url(#arrowhead)");
    expect(
      host.querySelectorAll<SVGPathElement>(
        'path[marker-end="url(https://evil.example/marker)"]',
      ),
    ).toHaveLength(0);
    expect(host.querySelector("text")?.getAttribute("text-anchor")).toBe(
      "middle",
    );
    expect(host.querySelector("text")?.getAttribute("dominant-baseline")).toBe(
      "central",
    );
  });

  it("renders Mermaid fences as diagram render targets", async () => {
    const rendered = await renderMarkdownHtml(
      ["```mermaid", "graph TD", "  A[Start] --> B[Done]", "```"].join("\n"),
      "main",
    );
    const host = document.createElement("div");
    host.innerHTML = rendered;

    const diagram = host.querySelector<HTMLElement>("pre.mermaid");

    expect(diagram).not.toBeNull();
    expect(diagram?.textContent).toContain("graph TD");
    expect(diagram?.textContent).toContain("A[Start] --> B[Done]");
    expect(host.querySelector("code.language-mermaid")).toBeNull();
  });

  it("keeps single-tilde ranges literal while rendering double-tilde strikethrough", async () => {
    const rendered = await renderMarkdownHtml(
      [
        "~2024~ should stay literal.",
        "foo ~bar~ baz should stay literal.",
        "2024~2026 and 09:00~10:30 should stay literal.",
        "foo ~~deleted~~ baz should render strikethrough.",
      ].join("\n\n"),
      "main",
    );
    const host = document.createElement("div");
    host.innerHTML = rendered;

    expect(host.textContent).toContain("~2024~ should stay literal.");
    expect(host.textContent).toContain("foo ~bar~ baz should stay literal.");
    expect(host.textContent).toContain("2024~2026 and 09:00~10:30");

    const deletions = Array.from(host.querySelectorAll("del"));
    expect(deletions).toHaveLength(1);
    expect(deletions[0]?.textContent).toBe("deleted");
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
      host.querySelector<HTMLAnchorElement>(
        'a[href="/taeho/view-data/reports/deep.md"]',
      )?.textContent,
    ).toBe("human md");
    expect(
      host.querySelector<HTMLAnchorElement>(
        'a[href="/taeho/view-data/reports/company%20page.html#summary"]',
      )?.textContent,
    ).toBe("api html");
    expect(
      host.querySelector<HTMLAnchorElement>(
        'a[href="/taeho/data/reports/raw.pdf"]',
      )?.textContent,
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
