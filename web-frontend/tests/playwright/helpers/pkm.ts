import { expect, type Page } from '@playwright/test';

type Vault = { name: string; path: string };
type NoteEntry = { note_id: string; title?: string };
type SearchResult = { note_id: string; title?: string };
type SearchResponse = { results?: SearchResult[] };

export async function loginAndFindNote(page: Page) {
  const login = await page.request.post('/api/v1/auth/login', {
    data: { password: 'pkm-local', remember: true }
  });
  testSkipUnless(login.ok(), `login unavailable: ${login.status()}`);

  const payload = await login.json();
  const vaults = (payload.vaults ?? []) as Vault[];
  testSkipUnless(vaults.length > 0, 'no vaults available');

  for (const vault of vaults) {
    const notesResponse = await page.request.get(
      `/api/v1/vault/${encodeURIComponent(vault.name)}/notes`
    );
    if (!notesResponse.ok()) continue;
    const notes = (await notesResponse.json()) as NoteEntry[];
    const note = notes.find((entry) => entry.note_id);
    if (note) return { vaultName: vault.name, noteId: note.note_id };
  }

  testSkipUnless(false, 'no notes available in discovered vaults');
  throw new Error('unreachable');
}

export async function loginAndFindVault(page: Page) {
  const login = await page.request.post('/api/v1/auth/login', {
    data: { password: 'pkm-local', remember: true }
  });
  testSkipUnless(login.ok(), `login unavailable: ${login.status()}`);

  const payload = await login.json();
  const vaults = (payload.vaults ?? []) as Vault[];
  testSkipUnless(vaults.length > 0, 'no vaults available');
  return vaults[0].name;
}

export async function loginAndFindSearchableNote(page: Page) {
  const login = await page.request.post('/api/v1/auth/login', {
    data: { password: 'pkm-local', remember: true }
  });
  testSkipUnless(login.ok(), `login unavailable: ${login.status()}`);

  const payload = await login.json();
  const vaults = (payload.vaults ?? []) as Vault[];
  testSkipUnless(vaults.length > 0, 'no vaults available');

  for (const vault of vaults) {
    const notesResponse = await page.request.get(
      `/api/v1/vault/${encodeURIComponent(vault.name)}/notes`
    );
    if (!notesResponse.ok()) continue;

    const notes = (await notesResponse.json()) as NoteEntry[];
    for (const note of notes.slice(0, 12)) {
      const label = note.title || note.note_id;
      const query = searchableToken(label);
      if (!query) continue;

      const searchResponse = await page.request.get(
        `/api/v1/vault/${encodeURIComponent(vault.name)}/search?q=${encodeURIComponent(query)}`
      );
      if (!searchResponse.ok()) continue;

      const search = (await searchResponse.json()) as SearchResponse;
      const result = search.results?.find((item) => item.note_id);
      if (result) {
        return {
          vaultName: vault.name,
          query,
          noteId: result.note_id,
          title: result.title || result.note_id
        };
      }
    }
  }

  testSkipUnless(false, 'no searchable notes available');
  throw new Error('unreachable');
}

export async function expectCommandPaletteFocused(page: Page) {
  await expect(
    page.locator('[role="dialog"][aria-label="Command palette"]')
  ).toBeVisible();
  await expect(page.locator('.cmdk-input')).toBeFocused();
}

function searchableToken(value: string) {
  return (
    value
      .split(/[^A-Za-z0-9가-힣_]+/)
      .find((part) => part.length >= 3 && !/^\d+$/.test(part))
      ?.slice(0, 32) ?? ''
  );
}

function testSkipUnless(condition: unknown, description: string): asserts condition {
  if (!condition) {
    // eslint-disable-next-line playwright/no-skipped-test
    throw new Error(`SKIP:${description}`);
  }
}
