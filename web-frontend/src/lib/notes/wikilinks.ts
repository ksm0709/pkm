const WIKILINK_RE = /\[\[([^\n|]+?)(?:\|([^\n]*?))?\]\]/g;

function escapeMarkdownLabel(text: string) {
  return text.replace(/([\\[\]])/g, "\\$1");
}

function forMarkdownTextSegments(
  markdown: string,
  mapText: (segment: string) => string,
) {
  let inFence = false;
  let fenceMarker = "";

  return markdown
    .split("\n")
    .map((line) => {
      const trimmed = line.trimStart();
      const fence = trimmed.match(/^(```+|~~~+)/)?.[1];
      if (fence && (!inFence || fence.startsWith(fenceMarker[0]))) {
        inFence = !inFence;
        fenceMarker = inFence ? fence : "";
        return line;
      }
      if (inFence) return line;

      return line
        .split(/(`[^`]*`)/g)
        .map((segment) => {
          if (segment.startsWith("`") && segment.endsWith("`")) return segment;
          return mapText(segment);
        })
        .join("");
    })
    .join("\n");
}

export function wikilinksToMarkdownLinks(markdown: string, vault: string) {
  return forMarkdownTextSegments(markdown, (segment) =>
    segment.replace(WIKILINK_RE, (match, rawTarget, rawAlias, offset) => {
      if (segment[offset - 1] === "!") return match;

      const target = String(rawTarget ?? "").trim();
      const label =
        rawAlias === undefined ? target : String(rawAlias ?? "").trim();

      if (!target) return match;

      const href = `/${encodeURIComponent(vault)}/notes/${encodeURIComponent(target)}`;
      return `[${escapeMarkdownLabel(label || target)}](${href})`;
    }),
  );
}
