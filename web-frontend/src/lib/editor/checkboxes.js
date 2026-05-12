/**
 * checkboxes — F4-1 (Maximalist).
 *
 * Interactive task-list checkboxes. Recognises `- [ ]` and `- [x]` at
 * the start of a (optionally indented) bullet line. The `[ ]` / `[x]`
 * range is replaced with a clickable widget on non-active lines; on the
 * active line a CSS class applies so the raw `[ ]`/`[x]` remains
 * editable but is also clickable via a transparent hit area.
 *
 * Click toggles the underlying markdown character via a doc transaction.
 */
import {
  ViewPlugin,
  Decoration,
  WidgetType,
  EditorView,
} from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";

// Capture indent + bullet + checkbox span. The checkbox start offset
// inside the line is computed from match indices.
const TASK_RE = /^(\s*[-*]\s+)(\[[ xX]\])(\s)/;

class CheckboxWidget extends WidgetType {
  /**
   * @param {boolean} checked
   * @param {number} pos absolute doc offset of the `[`
   */
  constructor(checked, pos) {
    super();
    this.checked = checked;
    this.pos = pos;
  }
  /** @param {CheckboxWidget} o */
  eq(o) {
    return o.checked === this.checked && o.pos === this.pos;
  }
  toDOM() {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.className = "cm-md-checkbox";
    input.checked = this.checked;
    // The actual click-to-toggle is dispatched in the plugin's DOM
    // event handler so it has access to the EditorView. Mark the
    // element with the offset for the handler to read.
    input.dataset.cmCheckboxPos = String(this.pos);
    return input;
  }
  ignoreEvent() {
    return false;
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

  for (const { from, to } of view.visibleRanges) {
    let pos = from;
    while (pos <= to) {
      const line = view.state.doc.lineAt(pos);
      const m = TASK_RE.exec(line.text);
      if (m) {
        const cbStart = line.from + m[1].length;
        const cbEnd = cbStart + m[2].length;
        const checked = m[2][1].toLowerCase() === "x";
        if (line.number === activeLine) {
          // Mark only — keep raw text editable.
          builder.add(
            cbStart,
            cbEnd,
            Decoration.mark({ class: "cm-md-checkbox-raw" }),
          );
        } else {
          builder.add(
            cbStart,
            cbEnd,
            Decoration.replace({
              widget: new CheckboxWidget(checked, cbStart),
            }),
          );
        }
      }
      pos = line.to + 1;
      if (line.to >= view.state.doc.length) break;
    }
  }
  return builder.finish();
}

/**
 * Toggle the markdown character at `pos` between space and 'x'.
 * `pos` is the offset of the `[` so the char to toggle is at pos+1.
 *
 * @param {import('@codemirror/view').EditorView} view
 * @param {number} pos
 */
function toggleAt(view, pos) {
  const charPos = pos + 1;
  if (charPos + 1 > view.state.doc.length) return;
  const current = view.state.doc.sliceString(charPos, charPos + 1);
  const next = current.toLowerCase() === "x" ? " " : "x";
  view.dispatch({
    changes: { from: charPos, to: charPos + 1, insert: next },
  });
}

export const checkboxes = ViewPlugin.fromClass(
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
  {
    decorations: (v) => v.decorations,
    eventHandlers: {
      mousedown(e, view) {
        const t = /** @type {HTMLElement} */ (e.target);
        if (
          t &&
          t instanceof HTMLInputElement &&
          t.classList.contains("cm-md-checkbox")
        ) {
          e.preventDefault();
          const posStr = t.dataset.cmCheckboxPos;
          if (!posStr) return false;
          toggleAt(view, Number(posStr));
          return true;
        }
        // Active-line raw `[ ]` / `[x]`: detect click on the marker
        // span so users can also click it without first leaving the
        // line.
        if (t && t.classList && t.classList.contains("cm-md-checkbox-raw")) {
          // Resolve the doc position from the click coordinates.
          const docPos = view.posAtCoords({ x: e.clientX, y: e.clientY });
          if (docPos == null) return false;
          const line = view.state.doc.lineAt(docPos);
          const m = TASK_RE.exec(line.text);
          if (!m) return false;
          const cbStart = line.from + m[1].length;
          e.preventDefault();
          toggleAt(view, cbStart);
          return true;
        }
        return false;
      },
    },
  },
);

export const checkboxesTheme = EditorView.baseTheme({
  ".cm-md-checkbox": {
    cursor: "pointer",
    margin: "0 4px 0 0",
    accentColor: "var(--accent)",
    verticalAlign: "middle",
  },
  ".cm-md-checkbox-raw": {
    cursor: "pointer",
    color: "var(--accent)",
  },
});
