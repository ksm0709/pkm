/**
 * Wikilink widget — slice 4 / F4-2.
 *
 * A CM6 ViewPlugin + WidgetType that renders `[[id]]` tokens as resolved
 * note-title links. Implements:
 *   - Cursor-line-reveal: active line shows raw `[[id]]`, off-cursor lines
 *     replace the token with a clickable widget.
 *   - Loading & unresolved fallback: while title is pending the raw
 *     `[[id]]` text is shown in `--text-faint` italic; if the resolver
 *     returns "" (no such note) the same faint italic is shown so the
 *     reader knows the link is broken.
 *   - Click → navigates via `window.__pkmNav.gotoNote(id)`.
 *   - Hover (200ms delay) → `window.__pkmPreview.show({ id, x, y })` and
 *     `hide()` on mouseleave; the preview component lazily fetches body.
 *
 * The current vault is read from `window.location.pathname` (`/[vault]/...`).
 * This is the simplest source of truth — the editor host is always under a
 * vault route. A CM6 Facet was considered but rejected as overkill: the
 * resolver lives outside the editor lifecycle (cache survives editor
 * remounts) and would otherwise need to be passed through the host
 * configuration anyway.
 *
 * See WikilinkResolver singleton below.
 */
import {
  EditorView,
  ViewPlugin,
  Decoration,
  WidgetType,
} from "@codemirror/view";
import { RangeSetBuilder, StateEffect } from "@codemirror/state";
import { apiClient } from "../api/client.js";

// Single-line, single capture group. Disallow ']' and newline inside id.
const WIKILINK_RE = /\[\[([^\]\n]+)\]\]/g;

// Hover delay before requesting preview (ms).
const HOVER_DELAY_MS = 200;
const wikilinkRedecorate = StateEffect.define();

/* ----------------------------- Resolver ----------------------------- */

/**
 * Singleton wikilink resolver.
 *
 * Coalesces `[[id]]` lookups into batched POST /notes/batch-titles requests.
 * Per-vault cache: `Map<vault, Map<id, Promise<string>>>` where the
 * resolved string is the title or "" for unresolved (matches backend).
 *
 * Invalidates per-vault on `window.focus` so renames are picked up.
 */
class WikilinkResolver {
  constructor() {
    /** @type {Map<string, Map<string, Promise<string>>>} */
    this.cache = new Map();
    /** @type {Map<string, { ids: Set<string>, scheduled: boolean, resolvers: Map<string, {resolve:(v:string)=>void, reject:(e:any)=>void}> }>} */
    this.pending = new Map();
    this._installFocusInvalidator();
  }

  _installFocusInvalidator() {
    if (typeof window === "undefined") return;
    const win = /** @type {any} */ (window);
    if (win.__pkmWikilinkFocusInstalled) return;
    win.__pkmWikilinkFocusInstalled = true;
    window.addEventListener("focus", () => {
      // Drop all caches; pending in-flight batches still resolve their own
      // promises (callers waiting on them get the previous result).
      this.cache.clear();
    });
  }

  /**
   * Resolve a wikilink id to a note title.
   *
   * @param {string} vault
   * @param {string} id
   * @returns {Promise<string>} title, or "" if unresolved
   */
  resolve(vault, id) {
    let vmap = this.cache.get(vault);
    if (!vmap) {
      vmap = new Map();
      this.cache.set(vault, vmap);
    }
    const cached = vmap.get(id);
    if (cached) return cached;

    let pend = this.pending.get(vault);
    if (!pend) {
      pend = { ids: new Set(), scheduled: false, resolvers: new Map() };
      this.pending.set(vault, pend);
    }

    /** @type {Promise<string>} */
    const p = new Promise((resolve, reject) => {
      pend.resolvers.set(id, { resolve, reject });
    });
    vmap.set(id, p);
    pend.ids.add(id);

    if (!pend.scheduled) {
      pend.scheduled = true;
      // @batchAssert — All resolve(vault, id) calls made *synchronously*
      // during a CM6 decoration build land in the same `pend.ids` Set
      // before this microtask flush fires. queueMicrotask defers until
      // the current synchronous frame completes, so 50 widgets calling
      // resolve() in one decoration pass produce exactly ONE network
      // request. (Verified by inspection per F4-2 step 5; F4-8 will add
      // a Playwright assertion.)
      queueMicrotask(() => this._flush(vault));
    }
    return p;
  }

  /** @param {string} vault */
  async _flush(vault) {
    const pend = this.pending.get(vault);
    if (!pend) return;
    const ids = Array.from(pend.ids);
    const resolvers = pend.resolvers;
    this.pending.delete(vault);
    if (ids.length === 0) return;

    try {
      const res = await apiClient(
        `/api/v1/vault/${encodeURIComponent(vault)}/notes/batch-titles`,
        {
          method: "POST",
          body: JSON.stringify({ ids }),
        },
      );
      if (res.status === 401 || res.status === 403) {
        // Treat auth failure as unresolved (apiClient already redirects on 401).
        for (const id of ids) {
          resolvers.get(id)?.resolve("");
        }
        return;
      }
      if (!res.ok) {
        const err = new Error(`batch-titles ${res.status}`);
        for (const id of ids) {
          resolvers.get(id)?.reject(err);
          // Drop from cache so a later attempt can retry.
          this.cache.get(vault)?.delete(id);
        }
        return;
      }
      /** @type {Record<string,string>} */
      const data = await res.json();
      for (const id of ids) {
        const title = typeof data[id] === "string" ? data[id] : "";
        resolvers.get(id)?.resolve(title);
      }
    } catch (err) {
      for (const id of ids) {
        resolvers.get(id)?.reject(err);
        this.cache.get(vault)?.delete(id);
      }
    }
  }
}

export const wikilinkResolver = new WikilinkResolver();

/* ----------------------------- Widget ------------------------------- */

/**
 * Resolved-title widget. Shows the title as a clickable link; while loading
 * or unresolved it shows raw `[[id]]` text in `--text-faint` italic.
 *
 * `eq()` returns true on identical (id, title, state) so DOM is reused on
 * cursor moves and re-decoration passes.
 */
class WikilinkWidget extends WidgetType {
  /**
   * @param {string} id
   * @param {string} title  resolved title; "" if unresolved
   * @param {'loading'|'resolved'|'unresolved'} state
   */
  constructor(id, title, state) {
    super();
    this.id = id;
    this.title = title;
    this.state = state;
  }
  /** @param {WikilinkWidget} other */
  eq(other) {
    return (
      other.id === this.id &&
      other.title === this.title &&
      other.state === this.state
    );
  }
  toDOM() {
    const span = document.createElement("span");
    span.className = "cm-wikilink";
    span.dataset.wikilinkId = this.id;
    if (this.state === "resolved") {
      span.classList.add("cm-wikilink-resolved");
      span.textContent = this.title;
    } else {
      span.classList.add("cm-wikilink-faint");
      span.textContent = `[[${this.id}]]`;
    }
    /** @type {ReturnType<typeof setTimeout>|null} */
    let hoverTimer = null;
    span.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const nav = /** @type {any} */ (window).__pkmNav;
      nav?.gotoNote?.(this.id);
    });
    span.addEventListener("mouseenter", (ev) => {
      const x = ev.clientX;
      const y = ev.clientY;
      hoverTimer = setTimeout(() => {
        const preview = /** @type {any} */ (window).__pkmPreview;
        preview?.show?.({
          id: this.id,
          title: this.state === "resolved" ? this.title : this.id,
          x,
          y,
        });
      }, HOVER_DELAY_MS);
    });
    span.addEventListener("mouseleave", () => {
      if (hoverTimer) {
        clearTimeout(hoverTimer);
        hoverTimer = null;
      }
      const preview = /** @type {any} */ (window).__pkmPreview;
      preview?.hide?.();
    });
    return span;
  }
  ignoreEvent() {
    return false;
  }
}

/* --------------------------- View plugin ---------------------------- */

/** Read current vault from `/[vault]/...` URL. */
function currentVault() {
  if (typeof window === "undefined") return "";
  const m = window.location.pathname.match(/^\/([^/]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

/**
 * Decoration build per F4-2 step 5: every visible `[[id]]` triggers a
 * synchronous `resolver.resolve()` call so all ids in the viewport land
 * in ONE microtask-coalesced batch request.
 *
 * @param {EditorView} view
 * @param {(id:string) => 'loading'|'resolved'|'unresolved'} stateOf
 * @param {(id:string) => string} titleOf
 */
function buildWikilinkDecorations(view, stateOf, titleOf) {
  /** @type {RangeSetBuilder<Decoration>} */
  const builder = new RangeSetBuilder();
  const sel = view.state.selection.main;
  const activeLine = view.state.doc.lineAt(sel.head).number;

  /** @type {Array<{from:number, to:number, deco:Decoration}>} */
  const ranges = [];

  for (const { from, to } of view.visibleRanges) {
    let pos = from;
    while (pos <= to) {
      const line = view.state.doc.lineAt(pos);
      if (line.number !== activeLine) {
        WIKILINK_RE.lastIndex = 0;
        let m;
        while ((m = WIKILINK_RE.exec(line.text)) !== null) {
          const id = m[1].trim();
          if (!id) continue;
          const start = line.from + m.index;
          const end = start + m[0].length;
          const state = stateOf(id);
          const title = titleOf(id);
          ranges.push({
            from: start,
            to: end,
            deco: Decoration.replace({
              widget: new WikilinkWidget(id, title, state),
            }),
          });
        }
      }
      pos = line.to + 1;
      if (line.to >= view.state.doc.length) break;
    }
  }

  ranges.sort((a, b) => a.from - b.from || a.to - b.to);
  for (const r of ranges) {
    if (r.from === r.to) continue;
    builder.add(r.from, r.to, r.deco);
  }
  return builder.finish();
}

export const wikilinkWidget = ViewPlugin.fromClass(
  class {
    /** @param {EditorView} view */
    constructor(view) {
      this.view = view;
      this.vault = currentVault();
      /** @type {Map<string, 'loading'|'resolved'|'unresolved'>} */
      this.states = new Map();
      /** @type {Map<string, string>} */
      this.titles = new Map();
      this.decorations = this._build();
    }

    /** @param {string} id */
    _ensure(id) {
      if (this.states.has(id)) return;
      this.states.set(id, "loading");
      this.titles.set(id, "");
      if (!this.vault) {
        this.states.set(id, "unresolved");
        return;
      }
      wikilinkResolver
        .resolve(this.vault, id)
        .then((title) => {
          if (title) {
            this.states.set(id, "resolved");
            this.titles.set(id, title);
          } else {
            this.states.set(id, "unresolved");
          }
          // Trigger a re-decoration on the next animation frame.
          this._scheduleRedecorate();
        })
        .catch(() => {
          this.states.set(id, "unresolved");
          this._scheduleRedecorate();
        });
    }

    _scheduleRedecorate() {
      if (this._redecorateScheduled) return;
      this._redecorateScheduled = true;
      requestAnimationFrame(() => {
        this._redecorateScheduled = false;
        this.view.dispatch({ effects: wikilinkRedecorate.of(null) });
      });
    }

    _build() {
      return buildWikilinkDecorations(
        this.view,
        (id) => {
          this._ensure(id);
          return this.states.get(id) ?? "loading";
        },
        (id) => this.titles.get(id) ?? "",
      );
    }

    /** @param {import('@codemirror/view').ViewUpdate} update */
    update(update) {
      if (
        update.docChanged ||
        update.viewportChanged ||
        update.selectionSet ||
        update.transactions.some((tr) =>
          tr.effects.some((effect) => effect.is(wikilinkRedecorate)),
        )
      ) {
        this.decorations = this._build();
      }
    }
  },
  { decorations: (v) => v.decorations },
);

export const wikilinkWidgetTheme = EditorView.baseTheme({
  ".cm-wikilink": {
    cursor: "pointer",
  },
  ".cm-wikilink-resolved": {
    color: "var(--accent)",
    textDecoration: "underline",
    textDecorationColor: "var(--border)",
    textUnderlineOffset: "2px",
  },
  ".cm-wikilink-resolved:hover": {
    textDecorationColor: "var(--accent)",
  },
  ".cm-wikilink-faint": {
    color: "var(--text-faint)",
    fontStyle: "italic",
    fontFamily: "var(--font-mono)",
  },
});
