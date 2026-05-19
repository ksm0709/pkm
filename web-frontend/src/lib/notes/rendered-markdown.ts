import { marked } from "marked";
import { wikilinksToMarkdownLinks } from "./wikilinks";

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

  return template.innerHTML;
}

export async function renderMarkdownHtml(
  markdown: string,
  vault: string,
  doc: Document | undefined = typeof document === "undefined"
    ? undefined
    : document,
) {
  const markdownWithLinks = wikilinksToMarkdownLinks(markdown, vault);
  const parsed = await marked.parse(markdownWithLinks, {
    async: true,
    gfm: true,
  });
  return doc ? decorateRenderedHtml(parsed, vault, doc) : parsed;
}
