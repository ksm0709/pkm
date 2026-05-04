/**
 * SSE-over-fetch parser for POST endpoints (EventSource is GET-only).
 *
 * Yields {event, data} pairs as they stream in. The server emits standard
 * SSE blocks separated by blank lines:
 *
 *     event: <name>\n
 *     data: <json>\n
 *     \n
 */

import { apiClient } from './client.js';

/**
 * Stream SSE events from a POST endpoint. Calls onEvent(event, data) for
 * each parsed block. Resolves when the stream closes.
 *
 * @param {string} path
 * @param {unknown} body
 * @param {(event: string, data: unknown) => void} onEvent
 * @param {AbortSignal} [signal]
 */
export async function streamSse(path, body, onEvent, signal) {
  let res;
  try {
    res = await apiClient(path, {
      method: 'POST',
      body: JSON.stringify(body ?? {}),
      signal
    });
  } catch (error) {
    throw new Error(
      `Ask stream interrupted before it opened: ${error instanceof Error ? error.message : String(error)}`
    );
  }
  if (!res.ok || !res.body) {
    throw new Error(`POST ${path} → ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    let value;
    let done;
    try {
      ({ value, done } = await reader.read());
    } catch (error) {
      throw new Error(
        `Ask stream interrupted: ${error instanceof Error ? error.message : String(error)}`
      );
    }
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Split on the SSE block delimiter (blank line).
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);

      let eventName = 'message';
      const dataLines = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).replace(/^ /, ''));
        }
      }
      if (dataLines.length === 0) continue;

      const raw = dataLines.join('\n');
      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        data = raw;
      }
      onEvent(eventName, data);
    }
  }
}
