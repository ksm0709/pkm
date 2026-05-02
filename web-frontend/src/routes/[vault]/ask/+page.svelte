<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { page } from '$app/stores';
  import AskTranscript from '$lib/components/AskTranscript.svelte';
  import type { Turn } from '$lib/components/AskTranscript.svelte';
  import AskInput from '$lib/components/AskInput.svelte';
  import { streamSse } from '$lib/api/sse.js';

  let vaultName = $derived($page.params.vault);

  let turns = $state<Turn[]>([]);
  let busy = $state(false);
  let inputValue = $state('');
  let scrollEl: HTMLDivElement | null = $state(null);

  onMount(() => {
    const q = $page.url.searchParams.get('q');
    if (q && q.trim()) {
      inputValue = q;
      // Auto-submit pre-filled query
      void submit(q.trim());
    }
  });

  function appendChunk(chunk: Record<string, unknown>, eventName: string) {
    const turn = turns[turns.length - 1];
    if (!turn) return;

    const type = (chunk.type as string) || eventName;

    if (type === 'content') {
      const text = (chunk.text ?? chunk.content ?? '') as string;
      turn.answer += text;
    } else if (
      type === 'tool_call_start' ||
      type === 'tool_call' ||
      type === 'tool_detail'
    ) {
      const tool = (chunk.name ?? chunk.tool ?? 'tool') as string;
      const argsRaw = chunk.arguments ?? chunk.args ?? '';
      const args =
        typeof argsRaw === 'string' ? argsRaw : JSON.stringify(argsRaw);
      turn.items.push({ kind: 'tool_call', tool, args });
    } else if (type === 'reasoning') {
      const text = (chunk.text ?? chunk.content ?? '') as string;
      turn.items.push({ kind: 'reasoning', text });
    } else if (type === 'error') {
      const msg = (chunk.message ?? chunk.reason ?? 'error') as string;
      turn.items.push({ kind: 'error', message: msg });
    }
    // tool_call_end and other types are silently consumed.

    void tick().then(() => {
      if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    });
  }

  async function submit(question: string) {
    if (busy) return;
    busy = true;

    const turn: Turn = {
      question,
      items: [],
      answer: '',
      done: false
    };
    turns = [...turns, turn];

    try {
      await streamSse(
        `/api/v1/vault/${vaultName}/ask`,
        { query: question },
        (eventName, data) => {
          if (eventName === 'result') {
            const payload = (data ?? {}) as Record<string, unknown>;
            const answer = (payload.answer ?? '') as string;
            // Prefer the canonical final answer if no streaming content arrived.
            if (answer && !turn.answer) turn.answer = answer;
            turn.done = true;
          } else if (eventName === 'error') {
            const payload = (data ?? {}) as Record<string, unknown>;
            const msg = (payload.message ?? payload.reason ?? 'error') as string;
            turn.items.push({ kind: 'error', message: msg });
            turn.done = true;
          } else {
            appendChunk((data ?? {}) as Record<string, unknown>, eventName);
          }
        }
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      turn.items.push({ kind: 'error', message: msg });
    } finally {
      turn.done = true;
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>ask — {vaultName} — pkm</title>
</svelte:head>

<div class="ask-page">
  <div bind:this={scrollEl} class="scroll-area">
    <div class="reading-column">
      <AskTranscript {turns} />
    </div>
  </div>
  <div class="reading-column">
    <AskInput bind:value={inputValue} {busy} onsubmit={submit} />
  </div>
</div>

<style>
  .ask-page {
    display: flex;
    flex-direction: column;
    height: calc(100vh - var(--topbar-height, 44px));
  }

  .scroll-area {
    flex: 1;
    overflow-y: auto;
  }
</style>
