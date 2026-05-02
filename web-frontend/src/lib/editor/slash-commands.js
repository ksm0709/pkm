/**
 * Slash commands — F2-3.
 *
 * CM6 completion source triggered by `/` at line start. Items:
 *   /subnote — POST /daily/today, then insert wikilink to the new subnote
 *   /daily   — insert today's date wikilink (stub)
 *   /note    — insert a wikilink stub
 *   /link    — insert a markdown link template
 *   /tag     — insert a hashtag stub
 *
 * Menu styling: 32px rows, 30ms stagger reveal, --bg-elev background,
 * hairline border, no shadow.
 *
 * Returns CM6 extensions: a configured autocompletion + a baseTheme
 * for the menu look. Wire into CodeMirror.svelte's extensions array.
 */
import { autocompletion } from '@codemirror/autocomplete';
import { EditorView } from '@codemirror/view';
import { apiClient } from '../api/client.js';

/** Resolve the current vault from the route path: /{vault}/notes/... */
function currentVault() {
  if (typeof location === 'undefined') return '';
  const seg = location.pathname.split('/').filter(Boolean);
  return seg[0] ?? '';
}

/**
 * Build completion items. Each item returns an `apply` function so the
 * inserted text can be computed at selection time (including async ops
 * like /subnote which calls the daemon).
 */
const ITEMS = [
  {
    label: '/subnote',
    detail: 'create daily subnote',
    apply: async (
      /** @type {import('@codemirror/view').EditorView} */ view,
      /** @type {any} */ _completion,
      /** @type {number} */ from,
      /** @type {number} */ to
    ) => {
      const title =
        typeof window !== 'undefined' ? window.prompt('Subnote title') : null;
      if (!title) {
        // User cancelled — just remove the slash trigger.
        view.dispatch({ changes: { from, to, insert: '' } });
        return;
      }
      const vault = currentVault();
      let noteId = '';
      try {
        const res = await apiClient(`/api/v1/vault/${vault}/daily/today`, {
          method: 'POST',
          body: JSON.stringify({ type: 'subnote', title, content: '' })
        });
        if (!res.ok) throw new Error(`POST daily/today → ${res.status}`);
        const data = await res.json();
        noteId = data.note_id;
      } catch (err) {
        console.error('subnote create failed:', err);
        view.dispatch({ changes: { from, to, insert: '' } });
        return;
      }
      const insert = `[[${noteId}]]`;
      view.dispatch({
        changes: { from, to, insert },
        selection: { anchor: from + insert.length }
      });
    }
  },
  {
    label: '/daily',
    detail: 'insert today wikilink',
    apply: (
      /** @type {import('@codemirror/view').EditorView} */ view,
      /** @type {any} */ _c,
      /** @type {number} */ from,
      /** @type {number} */ to
    ) => {
      const today = new Date().toISOString().slice(0, 10);
      const insert = `[[${today}]]`;
      view.dispatch({
        changes: { from, to, insert },
        selection: { anchor: from + insert.length }
      });
    }
  },
  {
    label: '/note',
    detail: 'insert note wikilink',
    apply: (
      /** @type {import('@codemirror/view').EditorView} */ view,
      /** @type {any} */ _c,
      /** @type {number} */ from,
      /** @type {number} */ to
    ) => {
      const insert = '[[note-id]]';
      view.dispatch({
        changes: { from, to, insert },
        selection: { anchor: from + 2, head: from + 2 + 'note-id'.length }
      });
    }
  },
  {
    label: '/link',
    detail: 'insert markdown link',
    apply: (
      /** @type {import('@codemirror/view').EditorView} */ view,
      /** @type {any} */ _c,
      /** @type {number} */ from,
      /** @type {number} */ to
    ) => {
      const insert = '[text](url)';
      view.dispatch({
        changes: { from, to, insert },
        selection: { anchor: from + 1, head: from + 1 + 'text'.length }
      });
    }
  },
  {
    label: '/tag',
    detail: 'insert hashtag',
    apply: (
      /** @type {import('@codemirror/view').EditorView} */ view,
      /** @type {any} */ _c,
      /** @type {number} */ from,
      /** @type {number} */ to
    ) => {
      const insert = '#tag';
      view.dispatch({
        changes: { from, to, insert },
        selection: { anchor: from + 1, head: from + insert.length }
      });
    }
  }
];

/**
 * Completion source: only fires for `/...` typed at the start of a line.
 *
 * @param {import('@codemirror/autocomplete').CompletionContext} context
 */
function slashSource(context) {
  const line = context.state.doc.lineAt(context.pos);
  const col = context.pos - line.from;
  const before = line.text.slice(0, col);
  const m = before.match(/^\/(\w*)$/);
  if (!m) return null;
  return {
    from: line.from,
    to: context.pos,
    options: ITEMS,
    validFor: /^\/\w*$/
  };
}

/** Menu look: 32 px rows, --bg-elev background, hairline border, no shadow. */
const slashTheme = EditorView.baseTheme({
  '.cm-tooltip.cm-tooltip-autocomplete': {
    backgroundColor: 'var(--bg-elev)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm, 2px)',
    boxShadow: 'none',
    color: 'var(--text)',
    fontFamily: 'var(--font-mono)'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul': {
    fontFamily: 'var(--font-mono)',
    fontSize: 'var(--type-chrome-size, 13px)',
    maxHeight: '240px'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li': {
    height: '32px',
    lineHeight: '32px',
    padding: '0 12px',
    color: 'var(--text)',
    // 30ms stagger reveal — staggered fade-in by item index
    animation: 'pkm-slash-reveal 120ms var(--ease-out, ease-out) both'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]': {
    backgroundColor: 'var(--accent-bg)',
    color: 'var(--accent)'
  },
  // Stagger first 8 rows by 30ms each.
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(1)': {
    animationDelay: '0ms'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(2)': {
    animationDelay: '30ms'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(3)': {
    animationDelay: '60ms'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(4)': {
    animationDelay: '90ms'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(5)': {
    animationDelay: '120ms'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(6)': {
    animationDelay: '150ms'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(7)': {
    animationDelay: '180ms'
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li:nth-child(8)': {
    animationDelay: '210ms'
  },
  '.cm-completionDetail': {
    color: 'var(--text-muted)',
    fontStyle: 'italic',
    marginLeft: 'var(--space-3, 12px)'
  },
  '@keyframes pkm-slash-reveal': {
    from: { opacity: '0', transform: 'translateY(-2px)' },
    to: { opacity: '1', transform: 'translateY(0)' }
  }
});

export const slashCommands = [
  autocompletion({
    override: [slashSource],
    activateOnTyping: true,
    icons: false,
    defaultKeymap: true
  }),
  slashTheme
];
