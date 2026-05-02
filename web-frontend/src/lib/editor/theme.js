/**
 * CM6 theme that reads colors from the design tokens (CSS vars in tokens.css).
 * Active line uses --accent-bg. Caret + selection use --accent.
 *
 * Light/dark theming is handled by the CSS variable cascade — this single
 * theme works for both because every color resolves at paint time.
 */
import { EditorView } from '@codemirror/view';

export const pkmTheme = EditorView.theme(
  {
    '&': {
      color: 'var(--text)',
      backgroundColor: 'var(--bg)',
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--type-body-size, 15px)',
      lineHeight: 'var(--type-body-lh, 1.70)',
      height: '100%'
    },
    '.cm-content': {
      caretColor: 'var(--accent)',
      fontFamily: 'var(--font-mono)',
      padding: 'var(--space-3, 12px) 0'
    },
    '.cm-cursor, .cm-dropCursor': {
      borderLeftColor: 'var(--accent)'
    },
    '&.cm-focused .cm-cursor': {
      borderLeftColor: 'var(--accent)'
    },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection':
      {
        backgroundColor: 'var(--accent-bg)'
      },
    '.cm-activeLine': {
      backgroundColor: 'var(--accent-bg)'
    },
    '.cm-activeLineGutter': {
      backgroundColor: 'var(--accent-bg)'
    },
    '.cm-gutters': {
      backgroundColor: 'var(--bg)',
      color: 'var(--text-faint)',
      border: 'none'
    },
    '.cm-lineNumbers .cm-gutterElement': {
      color: 'var(--text-faint)',
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--type-caption-size, 12px)'
    },
    '.cm-scroller': {
      fontFamily: 'var(--font-mono)',
      overflow: 'auto'
    },
    '.cm-panels': {
      backgroundColor: 'var(--bg-elev)',
      color: 'var(--text)',
      borderColor: 'var(--border)'
    },
    '.cm-tooltip': {
      backgroundColor: 'var(--bg-elev)',
      borderColor: 'var(--border)',
      color: 'var(--text)'
    }
  },
  { dark: false }
);
