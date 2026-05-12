/**
 * CM6 theme for the Signal Desk edit zone.
 *
 * The shell can use luminous rails and grid texture, but the editor stays a
 * texture-free graphite/off-white slab for sustained writing. CSS variables
 * resolve through tokens.css for dark/light mode without extra dependencies.
 */
import { EditorView } from "@codemirror/view";

export const pkmTheme = EditorView.theme(
  {
    "&": {
      color: "var(--text)",
      backgroundColor: "var(--surface-prose)",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--type-body-size, 15px)",
      lineHeight: "var(--type-body-lh, 1.72)",
      height: "100%",
    },
    ".cm-content": {
      caretColor: "var(--accent)",
      fontFamily: "var(--font-mono)",
      padding: "var(--space-4, 16px) var(--space-4, 16px) var(--space-6, 32px)",
      minHeight: "100%",
    },
    ".cm-line": {
      padding: "0 2px",
    },
    ".cm-cursor, .cm-dropCursor": {
      borderLeftColor: "var(--accent)",
      borderLeftWidth: "2px",
    },
    "&.cm-focused .cm-cursor": {
      borderLeftColor: "var(--accent)",
    },
    "&.cm-focused": {
      outline: "1px solid var(--focus-ring)",
      outlineOffset: "-1px",
    },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
      {
        backgroundColor: "var(--selection-bg)",
      },
    ".cm-activeLine": {
      backgroundColor: "var(--accent-bg)",
    },
    ".cm-activeLineGutter": {
      backgroundColor: "var(--accent-bg)",
    },
    ".cm-gutters": {
      backgroundColor: "var(--surface-prose)",
      color: "var(--text-faint)",
      borderRight: "1px solid var(--border)",
    },
    ".cm-lineNumbers .cm-gutterElement": {
      color: "var(--text-faint)",
      fontFamily: "var(--font-mono)",
      fontSize: "var(--type-caption-size, 12px)",
    },
    ".cm-scroller": {
      fontFamily: "var(--font-mono)",
      overflow: "auto",
      backgroundColor: "var(--surface-prose)",
    },
    ".cm-panels": {
      backgroundColor: "var(--surface-raised)",
      color: "var(--text)",
      borderColor: "var(--border)",
    },
    ".cm-tooltip": {
      backgroundColor: "var(--surface-raised)",
      borderColor: "var(--border)",
      color: "var(--text)",
    },
    ".cm-tooltip-autocomplete ul li[aria-selected]": {
      backgroundColor: "var(--accent-bg)",
      color: "var(--text)",
    },
  },
  { dark: true },
);
