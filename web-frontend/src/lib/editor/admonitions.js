/**
 * admonitions — F4-1 (Maximalist).
 *
 * Decorates Obsidian-style callouts:
 *   > [!note]      ← marker line; replaced with styled label
 *   > [!warning]   (info | tip | caution also supported)
 *   > body line 1
 *   > body line 2
 *
 * Each blockquote line in the callout gets a 2px left rail in --accent
 * via a line decoration. The marker line itself is hidden (replaced by
 * a small icon + label widget) when not on the active line. On the
 * active line the raw `> [!type]` shows so the writer can edit it.
 */
import {
  ViewPlugin,
  Decoration,
  WidgetType,
  EditorView,
} from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";

const TYPES = {
  note: { icon: "i", label: "Note" },
  warning: { icon: "!", label: "Warning" },
  info: { icon: "i", label: "Info" },
  tip: { icon: "*", label: "Tip" },
  caution: { icon: "!", label: "Caution" },
};

/** @typedef {keyof typeof TYPES} AdmonitionType */

const MARKER_RE = /^>\s*\[!(\w+)\]\s*(.*)$/;
const QUOTE_RE = /^>\s?(.*)$/;

/** @param {string} value @returns {value is AdmonitionType} */
function isAdmonitionType(value) {
  return Object.prototype.hasOwnProperty.call(TYPES, value);
}

class AdmonitionLabelWidget extends WidgetType {
  /**
   * @param {AdmonitionType} type
   * @param {string} title
   */
  constructor(type, title) {
    super();
    this.type = type;
    this.title = title;
  }
  /** @param {AdmonitionLabelWidget} o */
  eq(o) {
    return o.type === this.type && o.title === this.title;
  }
  toDOM() {
    const host = document.createElement("span");
    host.className = `cm-md-admon-label cm-md-admon-label-${this.type}`;
    const meta = TYPES[this.type] ?? TYPES.note;
    const icon = document.createElement("span");
    icon.className = "cm-md-admon-icon";
    icon.textContent = meta.icon;
    const label = document.createElement("span");
    label.className = "cm-md-admon-text";
    label.textContent = this.title
      ? `${meta.label}: ${this.title}`
      : meta.label;
    host.appendChild(icon);
    host.appendChild(label);
    return host;
  }
  ignoreEvent() {
    return true;
  }
}

/**
 * @param {import('@codemirror/view').EditorView} view
 */
function buildDecorations(view) {
  /** @type {RangeSetBuilder<Decoration>} */
  const builder = new RangeSetBuilder();
  const sel = view.state.selection.main;
  const activeLine = view.state.doc.lineAt(sel.head).number;
  const doc = view.state.doc;

  for (const { from, to } of view.visibleRanges) {
    let pos = from;
    while (pos <= to) {
      const line = doc.lineAt(pos);
      const m = MARKER_RE.exec(line.text);
      if (m && isAdmonitionType(m[1])) {
        const type = m[1];
        const title = m[2];
        // Decorate marker line.
        builder.add(
          line.from,
          line.from,
          Decoration.line({
            attributes: { class: `cm-md-admon cm-md-admon-${type}` },
          }),
        );
        if (line.number !== activeLine) {
          builder.add(
            line.from,
            line.to,
            Decoration.replace({
              widget: new AdmonitionLabelWidget(type, title),
            }),
          );
        }
        // Walk subsequent quote lines; mark them with the same rail.
        let next = line.to + 1;
        while (next < doc.length) {
          const ln = doc.lineAt(next);
          if (!QUOTE_RE.test(ln.text) || MARKER_RE.test(ln.text)) break;
          builder.add(
            ln.from,
            ln.from,
            Decoration.line({
              attributes: { class: `cm-md-admon cm-md-admon-${type}` },
            }),
          );
          next = ln.to + 1;
          if (ln.to >= doc.length) break;
        }
        pos = next;
        continue;
      }
      pos = line.to + 1;
      if (line.to >= doc.length) break;
    }
  }
  return builder.finish();
}

export const admonitions = ViewPlugin.fromClass(
  class {
    /** @param {import('@codemirror/view').EditorView} view */
    constructor(view) {
      this.decorations = buildDecorations(view);
    }
    /** @param {import('@codemirror/view').ViewUpdate} update */
    update(update) {
      if (update.docChanged || update.viewportChanged || update.selectionSet) {
        this.decorations = buildDecorations(update.view);
      }
    }
  },
  { decorations: (v) => v.decorations },
);

export const admonitionsTheme = EditorView.baseTheme({
  ".cm-md-admon": {
    borderLeft: "2px solid var(--accent)",
    paddingLeft: "var(--space-3, 12px)",
    backgroundColor: "var(--bg-elev)",
  },
  ".cm-md-admon-label": {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    color: "var(--accent)",
    fontWeight: "600",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--type-caption-size, 12px)",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  },
  ".cm-md-admon-icon": {
    display: "inline-block",
    width: "14px",
    height: "14px",
    lineHeight: "14px",
    textAlign: "center",
    borderRadius: "50%",
    backgroundColor: "var(--accent)",
    color: "var(--bg)",
    fontSize: "10px",
    fontWeight: "700",
  },
  ".cm-md-admon-text": {
    color: "var(--accent)",
  },
});
