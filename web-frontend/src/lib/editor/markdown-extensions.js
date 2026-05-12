/**
 * markdown-extensions — F4-1 (Maximalist).
 *
 * Augments @codemirror/lang-markdown with the GFM bundle from
 * @lezer/markdown. The GFM bundle includes Table, Strikethrough,
 * TaskList, and Autolink — together they enable inline rendering of
 * pipe tables (rows/cells visible as source text) without breaking the
 * cursor-line-reveal flow from live-styling.js, since the GFM parser
 * only adds syntax tree nodes — no decorations.
 *
 * Returns a single CM6 LanguageSupport extension. Wire BEFORE
 * liveStyling so the markdown highlighter installs a base style that
 * live-styling can override on the active line.
 */
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { GFM } from "@lezer/markdown";

// markdownLanguage already enables GFM-ish syntax (sub/sup/emoji); we
// pass GFM explicitly so Tables are guaranteed to be parsed regardless
// of base-language defaults.
export const markdownWithGfm = markdown({
  base: markdownLanguage,
  extensions: [GFM],
});
