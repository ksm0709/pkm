import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$lib/api/sse.js', () => ({ streamSse: vi.fn() }));
vi.mock('$lib/api/client.js', () => ({ apiGet: vi.fn() }));

import { apiGet } from '$lib/api/client.js';
import { streamSse } from '$lib/api/sse.js';
import { getAskSession } from './session.svelte';

function installStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => store.set(key, value)),
    removeItem: vi.fn((key: string) => store.delete(key))
  });
}

describe('AskSessionState', () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    installStorage();
  });

  it('recovers a background-interrupted ask run instead of ending with a network error', async () => {
    const streamMock = vi.mocked(streamSse);
    const getMock = vi.mocked(apiGet);
    streamMock.mockImplementation(async (_path, body, onEvent) => {
      expect((body as { ask_run_id?: string }).ask_run_id).toMatch(/^web-run-/);
      onEvent('content', { type: 'content', content: 'partial' });
      throw new Error('Ask stream interrupted: network error');
    });
    getMock.mockResolvedValue({
      run_id: 'web-run-test',
      status: 'done',
      chunks: [{ seq: 0, event: 'content', data: { type: 'content', content: 'recovered' } }],
      result: { response: 'recovered' },
      error: null
    });

    const session = getAskSession(`recover-${Date.now()}`);
    session.hydrate();
    await session.submit('hello');

    expect(session.busy).toBe(false);
    expect(session.turns).toHaveLength(1);
    expect(session.turns[0].answer).toBe('recovered');
    expect(session.turns[0].done).toBe(true);
    expect(session.turns[0].items).toEqual([]);
    expect(getMock).toHaveBeenCalledWith(expect.stringContaining('/ask/runs/web-run-'));
  });

  it('labels auto model selections with the resolved model', async () => {
    const getMock = vi.mocked(apiGet);
    getMock.mockResolvedValue({
      model: 'auto',
      resolved_model: 'test/resolved-model',
      reasoning_effort: 'medium'
    });

    const session = getAskSession(`auto-model-${Date.now()}`);
    await session.loadOptions();

    expect(session.modelLabel).toBe('test/resolved-model (auto)');
  });

  it('labels explicit model selections without an auto suffix', async () => {
    const getMock = vi.mocked(apiGet);
    getMock.mockResolvedValue({
      model: 'test/explicit-model',
      resolved_model: 'test/explicit-model',
      reasoning_effort: 'medium'
    });

    const session = getAskSession(`explicit-model-${Date.now()}`);
    await session.loadOptions();

    expect(session.modelLabel).toBe('test/explicit-model');
  });
});
