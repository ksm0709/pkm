import { Marked } from "marked";
import { rewriteRenderableDataLinkHref } from "$lib/data-viewer/paths";
import { wikilinksToMarkdownLinks } from "./wikilinks";

const pkmMarked = new Marked({ gfm: true });

pkmMarked.use({
  tokenizer: {
    del(src) {
      const cap =
        /^(~~)(?=[^\s~])((?:\\.|[^\\])*?(?:\\.|[^\s~\\]))\1(?=[^~]|$)/.exec(
          src,
        );
      if (!cap) return undefined;

      return {
        type: "del",
        raw: cap[0],
        text: cap[2],
        tokens: this.lexer.inlineTokens(cap[2]),
      };
    },
  },
});

const allowedTags = new Set([
  "a",
  "blockquote",
  "br",
  "button",
  "circle",
  "code",
  "del",
  "defs",
  "desc",
  "div",
  "em",
  "ellipse",
  "g",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "img",
  "li",
  "line",
  "marker",
  "ol",
  "p",
  "path",
  "polygon",
  "polyline",
  "pre",
  "rect",
  "span",
  "strong",
  "svg",
  "table",
  "tbody",
  "td",
  "tfoot",
  "th",
  "thead",
  "text",
  "title",
  "tr",
  "tspan",
  "ul",
]);

const droppedTags = new Set([
  "embed",
  "foreignobject",
  "iframe",
  "object",
  "script",
  "style",
]);

const globalAttributes = new Set(["aria-label", "class", "role", "title"]);
const svgTags = new Set([
  "circle",
  "defs",
  "desc",
  "ellipse",
  "g",
  "line",
  "marker",
  "path",
  "polygon",
  "polyline",
  "rect",
  "svg",
  "text",
  "title",
  "tspan",
]);
const svgAttributes = new Set([
  "aria-label",
  "class",
  "cx",
  "cy",
  "d",
  "dominant-baseline",
  "dx",
  "dy",
  "fill",
  "font-family",
  "font-size",
  "height",
  "id",
  "marker-end",
  "marker-height",
  "marker-mid",
  "marker-start",
  "marker-width",
  "markerheight",
  "markerunits",
  "markerwidth",
  "orient",
  "points",
  "r",
  "refx",
  "refy",
  "role",
  "rx",
  "ry",
  "stroke",
  "stroke-linecap",
  "stroke-linejoin",
  "stroke-width",
  "text-anchor",
  "title",
  "transform",
  "viewbox",
  "width",
  "x",
  "x1",
  "x2",
  "xmlns",
  "y",
  "y1",
  "y2",
]);
const svgPaintAttributes = new Set(["fill", "stroke"]);
const tagAttributes = new Map([
  ["a", new Set(["href", "rel", "target"])],
  ["button", new Set(["data-task-index", "data-task-state", "type"])],
  ["img", new Set(["alt", "decoding", "height", "loading", "src", "width"])],
  ["td", new Set(["align", "colspan", "rowspan"])],
  ["th", new Set(["align", "colspan", "rowspan"])],
]);

function isSafeUrl(value: string, kind: "href" | "src") {
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (
    trimmed.startsWith("#") ||
    trimmed.startsWith("/") ||
    trimmed.startsWith("./") ||
    trimmed.startsWith("../")
  ) {
    return true;
  }

  try {
    const url = new URL(trimmed, "https://pkm.local");
    if (url.protocol === "http:" || url.protocol === "https:") return true;
    return kind === "href" && url.protocol === "mailto:";
  } catch {
    return false;
  }
}

function isSafeSvgAttributeValue(name: string, value: string) {
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (/[<>\u0000-\u001f]/.test(trimmed)) return false;
  if (/javascript:|vbscript:|data:|expression\s*\(/i.test(trimmed))
    return false;
  if (/url\s*\(\s*(?!#[-\w:.]+\s*\))/i.test(trimmed)) return false;

  if (svgPaintAttributes.has(name)) {
    return (
      trimmed === "none" ||
      trimmed === "currentColor" ||
      /^#[0-9a-f]{3,8}$/i.test(trimmed) ||
      /^[a-z]+$/i.test(trimmed) ||
      /^url\(\s*#[-\w:.]+\s*\)$/i.test(trimmed) ||
      /^rgba?\([\d\s.,%]+\)$/i.test(trimmed)
    );
  }

  return true;
}

function isAllowedAttribute(element: Element, attribute: Attr) {
  const tag = element.tagName.toLowerCase();
  const name = attribute.name.toLowerCase();

  if (name.startsWith("on") || name === "style" || name === "srcdoc") {
    return false;
  }

  if (name === "href") return tag === "a" && isSafeUrl(attribute.value, "href");
  if (name === "src") return tag === "img" && isSafeUrl(attribute.value, "src");
  if (name === "target") return tag === "a";
  if (name === "rel") return tag === "a";

  if (svgTags.has(tag) && svgAttributes.has(name)) {
    return isSafeSvgAttributeValue(name, attribute.value);
  }

  return (
    globalAttributes.has(name) || (tagAttributes.get(tag)?.has(name) ?? false)
  );
}

export function sanitizeRenderedHtml(html: string, doc: Document = document) {
  const template = doc.createElement("template");
  template.innerHTML = html;
  const elements = Array.from(template.content.querySelectorAll("*"));

  for (const element of elements) {
    const tag = element.tagName.toLowerCase();

    if (droppedTags.has(tag)) {
      element.remove();
      continue;
    }

    if (!allowedTags.has(tag)) {
      element.replaceWith(...Array.from(element.childNodes));
      continue;
    }

    for (const attribute of Array.from(element.attributes)) {
      if (!isAllowedAttribute(element, attribute)) {
        element.removeAttribute(attribute.name);
      }
    }

    if (tag === "a") {
      const target = element.getAttribute("target");
      if (target?.toLowerCase() === "_blank") {
        element.setAttribute("rel", "noopener noreferrer");
      }
    }

    if (tag === "button" && !element.getAttribute("type")) {
      element.setAttribute("type", "button");
    }
  }

  return template.innerHTML;
}

export function tagHue(tag: string) {
  let hash = 0;
  for (const char of tag) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return String(hash % 360);
}

function hasExcludedAncestor(node: Node) {
  let current = node.parentElement;
  while (current) {
    if (
      ["A", "BUTTON", "CODE", "PRE", "SCRIPT", "STYLE"].includes(
        current.tagName,
      )
    ) {
      return true;
    }
    current = current.parentElement;
  }
  return false;
}

function appendDecoratedInlineSyntax(
  fragment: DocumentFragment,
  text: string,
  vault: string,
  doc: Document,
) {
  const pattern =
    /(^|[^\p{L}\p{N}_/-])#([\p{L}\p{N}_][\p{L}\p{N}_/-]*)|(^|[^A-Za-z0-9_&/-])&([A-Za-z][A-Za-z0-9_-]*)|\[([^\]\n]+)\]/gu;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text))) {
    const fullMatch = match[0];
    const tagPrefix = match[1] ?? "";
    const tagName = match[2];
    const relationPrefix = match[3] ?? "";
    const relationName = match[4];
    const bracketText = match[5];
    const syntaxStart =
      match.index + (tagName ? tagPrefix.length : relationPrefix.length);
    const syntaxText = tagName
      ? `#${tagName}`
      : relationName
        ? `&${relationName}`
        : fullMatch;

    if (syntaxStart > cursor) {
      fragment.append(doc.createTextNode(text.slice(cursor, syntaxStart)));
    }

    if (tagName) {
      const link = doc.createElement("a");
      link.className = "note-tag-chip";
      link.href = `/${encodeURIComponent(vault)}/notes/${encodeURIComponent(`tag:${tagName}`)}`;
      link.dataset.tag = tagName;
      link.style.setProperty("--tag-hue", tagHue(tagName));
      link.textContent = syntaxText;
      fragment.append(link);
    } else if (relationName) {
      const chip = doc.createElement("span");
      chip.className = "note-relation-chip";
      chip.dataset.relation = relationName;
      chip.title = `relation: ${relationName}`;
      chip.textContent = syntaxText;
      fragment.append(chip);
    } else if (bracketText) {
      const highlight = doc.createElement("span");
      highlight.className = "note-bracket-highlight";
      highlight.textContent = syntaxText;
      fragment.append(highlight);
    }

    cursor = match.index + fullMatch.length;
  }

  if (cursor < text.length) {
    fragment.append(doc.createTextNode(text.slice(cursor)));
  }
}

function wrapMarkdownTables(fragment: DocumentFragment, doc: Document) {
  for (const table of Array.from(fragment.querySelectorAll("table"))) {
    if (table.parentElement?.classList.contains("markdown-table-scroll")) {
      continue;
    }

    const wrapper = doc.createElement("div");
    wrapper.className = "markdown-table-scroll";
    table.replaceWith(wrapper);
    wrapper.append(table);
  }
}

function rewriteRenderableDataLinks(fragment: DocumentFragment, vault: string) {
  for (const link of Array.from(fragment.querySelectorAll("a[href]"))) {
    const href = link.getAttribute("href");
    if (!href) continue;
    const rewritten = rewriteRenderableDataLinkHref(href, vault);
    if (rewritten) link.setAttribute("href", rewritten);
  }
}

function promoteMermaidCodeBlocks(fragment: DocumentFragment, doc: Document) {
  for (const code of Array.from(
    fragment.querySelectorAll<HTMLElement>("pre > code.language-mermaid"),
  )) {
    const pre = code.parentElement;
    if (!pre) continue;

    const diagram = doc.createElement("pre");
    diagram.className = "mermaid";
    diagram.textContent = code.textContent ?? "";
    pre.replaceWith(diagram);
  }
}

export function decorateRenderedHtml(
  html: string,
  vault: string,
  doc: Document = document,
) {
  const template = doc.createElement("template");
  template.innerHTML = html;
  const walker = doc.createTreeWalker(template.content, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];

  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    if (
      !hasExcludedAncestor(node) &&
      /#[\p{L}\p{N}_]|\[[^\]\n]+\]|&[A-Za-z]/u.test(node.data)
    ) {
      textNodes.push(node);
    }
  }

  for (const node of textNodes) {
    const fragment = doc.createDocumentFragment();
    appendDecoratedInlineSyntax(fragment, node.data, vault, doc);
    node.replaceWith(fragment);
  }

  wrapMarkdownTables(template.content, doc);
  promoteMermaidCodeBlocks(template.content, doc);
  rewriteRenderableDataLinks(template.content, vault);

  return template.innerHTML;
}

export async function renderMarkdownHtml(
  markdown: string,
  vault: string,
  doc: Document | undefined = typeof document === "undefined"
    ? undefined
    : document,
  options: { transformMarkdown?: (markdown: string) => string } = {},
) {
  const markdownWithLinks = wikilinksToMarkdownLinks(markdown, vault);
  const source = options.transformMarkdown
    ? options.transformMarkdown(markdownWithLinks)
    : markdownWithLinks;
  const parsed = await pkmMarked.parse(source, {
    async: true,
  });
  const sanitized = doc ? sanitizeRenderedHtml(parsed, doc) : parsed;
  return doc ? decorateRenderedHtml(sanitized, vault, doc) : sanitized;
}
