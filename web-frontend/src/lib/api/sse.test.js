import { describe, expect, it, vi } from 'vitest';
import { streamSse } from './sse.js';

function responseFromChunks(chunks) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      }
    }),
    { status: 200 }
  );
}

describe('streamSse', () => {
  it('ignores heartbeat comments and parses result events', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        responseFromChunks([
          ': heartbeat\n\n',
          'event: content\ndata: {"type":"content","content":"hi"}\n\n',
          ': heartbeat\n\n',
          'event: result\ndata: {"response":"done"}\n\n'
        ])
      )
    );
    const events = [];

    await streamSse('/api/v1/vault/test/ask', { query: 'hi' }, (event, data) => {
      events.push({ event, data });
    });

    expect(events).toEqual([
      { event: 'content', data: { type: 'content', content: 'hi' } },
      { event: 'result', data: { response: 'done' } }
    ]);
    vi.unstubAllGlobals();
  });

  it('normalizes abrupt stream failures to an interrupted connection error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        let reads = 0;
        return new Response(
          new ReadableStream({
            pull(controller) {
              reads += 1;
              if (reads === 1) {
                controller.enqueue(new TextEncoder().encode(': heartbeat\n\n'));
                return;
              }
              throw new TypeError('network changed');
            }
          }),
          { status: 200 }
        );
      })
    );

    await expect(
      streamSse('/api/v1/vault/test/ask', { query: 'hi' }, () => {})
    ).rejects.toThrow('Ask stream interrupted');
    vi.unstubAllGlobals();
  });
});
