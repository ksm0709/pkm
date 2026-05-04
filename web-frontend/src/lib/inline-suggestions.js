import { apiGet } from './api/client.js';

const MAX_ROWS = 8;

export function detectInlineTrigger(value, cursor = value.length) {
  const before = value.slice(0, cursor);
  const wiki = before.match(/\[\[([^\]\[\n]*)$/);
  if (wiki) {
    const query = wiki[1] ?? '';
    return {
      kind: 'note',
      query,
      from: cursor - query.length - 2,
      to: cursor
    };
  }

  const tag = before.match(/(^|[\s([{])#([\p{L}\p{N}_/-]*)$/u);
  if (tag) {
    const query = tag[2] ?? '';
    return {
      kind: 'tag',
      query,
      from: cursor - query.length - 1,
      to: cursor
    };
  }

  return null;
}

export async function fetchInlineSuggestions(vaultName, trigger) {
  if (!trigger || !vaultName) return [];
  if (trigger.kind === 'note') {
    const q = trigger.query.trim();
    const data = q
      ? await apiGet(
          `/api/v1/vault/${encodeURIComponent(vaultName)}/search?q=${encodeURIComponent(q)}`
        )
      : await apiGet(`/api/v1/vault/${encodeURIComponent(vaultName)}/notes`);
    const results = Array.isArray(data?.results) ? data.results : Array.isArray(data) ? data : [];
    return results
      .map((note, index) => ({
        kind: 'note',
        label: String(note.note_id ?? note.title ?? ''),
        title: String(note.title ?? note.note_id ?? ''),
        detail: String(note.snippet ?? note.description ?? note.path ?? 'note'),
        insert: `[[${String(note.note_id ?? note.title ?? '')}]]`,
        score: scoreCandidate(
          [note.note_id, note.title, note.path, note.snippet],
          trigger.query,
          index
        )
      }))
      .filter((item) => item.label)
      .sort(compareSuggestions)
      .slice(0, MAX_ROWS);
  }

  const data = await apiGet(`/api/v1/vault/${encodeURIComponent(vaultName)}/tags`);
  const tags = Array.isArray(data?.tags) ? data.tags : [];
  return tags
    .map((item, index) => ({
      kind: 'tag',
      label: `#${String(item.tag ?? '')}`,
      title: `#${String(item.tag ?? '')}`,
      detail: `${Number(item.count ?? 0)} note${Number(item.count ?? 0) === 1 ? '' : 's'}`,
      insert: `#${String(item.tag ?? '')}`,
      score: scoreCandidate([item.tag], trigger.query, index)
    }))
    .filter((item) => item.label.length > 1 && Number.isFinite(item.score))
    .sort(compareSuggestions)
    .slice(0, MAX_ROWS);
}

export function applyInlineSuggestion(value, trigger, suggestion) {
  const next = `${value.slice(0, trigger.from)}${suggestion.insert}${value.slice(trigger.to)}`;
  const cursor = trigger.from + suggestion.insert.length;
  return { value: next, cursor };
}

function compareSuggestions(a, b) {
  return a.score - b.score || a.label.localeCompare(b.label);
}

function scoreCandidate(fields, query, index) {
  const q = normalize(query);
  if (!q) return index / 100;
  let best = Number.POSITIVE_INFINITY;
  for (const field of fields) {
    const candidate = normalize(String(field ?? ''));
    if (!candidate) continue;
    if (candidate === q) best = Math.min(best, 0);
    else if (candidate.startsWith(q)) best = Math.min(best, 10);
    else {
      const at = candidate.indexOf(q);
      if (at >= 0) best = Math.min(best, 30 + at);
    }
  }
  return best + index / 100;
}

function normalize(text) {
  return String(text).toLowerCase().replace(/[_/-]+/g, ' ').replace(/\s+/g, ' ').trim();
}
