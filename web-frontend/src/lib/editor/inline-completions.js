import { EditorView } from '@codemirror/view';
import { detectInlineTrigger, fetchInlineSuggestions } from '../inline-suggestions.js';

/**
 * @param {import('@codemirror/autocomplete').CompletionContext} context
 */
export async function inlineCompletionSource(context) {
  const value = context.state.doc.toString();
  const trigger = detectInlineTrigger(value, context.pos);
  if (!trigger) return null;

  const vault = currentVault();
  if (!vault) return null;

  const suggestions = await fetchInlineSuggestions(vault, trigger);
  if (!suggestions.length) return null;

  return {
    from: trigger.from,
    to: context.pos,
    filter: false,
    options: suggestions.map((suggestion) => ({
      label: suggestion.label,
      detail: suggestion.kind === 'note' ? suggestion.title : suggestion.detail,
      type: suggestion.kind === 'tag' ? 'keyword' : 'text',
      apply: suggestion.insert
    }))
  };
}

function currentVault() {
  if (typeof location === 'undefined') return '';
  const seg = location.pathname.split('/').filter(Boolean);
  return seg[0] ?? '';
}

export const inlineCompletionTheme = EditorView.baseTheme({
  '.cm-tooltip.cm-tooltip-autocomplete': {
    backgroundColor: 'var(--surface, var(--bg))',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm, 2px)',
    boxShadow: 'none',
    color: 'var(--text)',
    fontFamily: 'var(--font-mono)'
  }
});
