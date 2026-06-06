import { marked } from "marked";
import { rewriteRenderableDataLinkHref } from "$lib/data-viewer/paths";
import { wikilinksToMarkdownLinks } from "./wikilinks";

const allowedTags = new Set([
  "a",
  "blockquote",
  "br",
  "button",
  "code",
  "del",
  "div",
  "em",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "img",
  "li",
  "ol",
  "p",
  "pre",
  "span",
  "strong",
  "table",
  "tbody",
  "td",
  "tfoot",
  "th",
  "thead",
  "tr",
  "ul",
]);

const droppedTags = new Set(["embed", "iframe", "object", "script", "style"]);

const globalAttributes = new Set(["aria-label", "class", "title"]);
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

function rewriteRenderableDataLinks(
  fragment: DocumentFragment,
  vault: string,
) {
  for (const link of Array.from(fragment.querySelectorAll("a[href]"))) {
    const href = link.getAttribute("href");
    if (!href) continue;
    const rewritten = rewriteRenderableDataLinkHref(href, vault);
    if (rewritten) link.setAttribute("href", rewritten);
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
  const parsed = await marked.parse(source, {
    async: true,
    gfm: true,
  });
  const sanitized = doc ? sanitizeRenderedHtml(parsed, doc) : parsed;
  return doc ? decorateRenderedHtml(sanitized, vault, doc) : sanitized;
}
