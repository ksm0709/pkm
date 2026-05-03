<script lang="ts">
  type Item =
    | { kind: 'tool_call'; tool: string; args: string }
    | { kind: 'reasoning'; text: string }
    | { kind: 'content'; text: string }
    | { kind: 'error'; message: string };

  export interface Turn {
    question: string;
    items: Item[];
    answer: string;
    done: boolean;
  }

  interface Props {
    turns: Turn[];
  }

  let { turns }: Props = $props();

  let showReasoning = $state<Record<number, boolean>>({});

  function toggle(turnIdx: number) {
    showReasoning[turnIdx] = !showReasoning[turnIdx];
  }
</script>

<div class="transcript">
  {#each turns as turn, ti (ti)}
    <article class="turn">
      <div class="question">
        <span class="packet-label">QUERY PACKET</span>
        <p>{turn.question}</p>
      </div>

      <div class="stream">
        {#each turn.items as item, ii (ii)}
          {#if item.kind === 'tool_call'}
            <p class="tool-call"><span>tool</span>{item.tool} · {item.args}</p>
          {:else if item.kind === 'reasoning'}
            {#if showReasoning[ti]}
              <pre class="reasoning">{item.text}</pre>
            {/if}
          {:else if item.kind === 'error'}
            <p class="error">{item.message}</p>
          {/if}
        {/each}

        {#if turn.items.some((i) => i.kind === 'reasoning')}
          <button
            type="button"
            class="reasoning-toggle"
            onclick={() => toggle(ti)}
            aria-expanded={!!showReasoning[ti]}
          >
            {showReasoning[ti] ? '▾' : '▸'} reasoning
          </button>
        {/if}

        {#if turn.answer}
          <pre class="answer">{turn.answer}</pre>
        {/if}
      </div>
    </article>
  {/each}
</div>

<style>
  .transcript {
    display: flex;
    flex-direction: column;
    gap: var(--space-6, 32px);
    padding-top: var(--space-6, 32px);
    padding-bottom: var(--space-7, 48px);
  }

  .turn {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
    border-left: 1px solid var(--accent);
    padding-left: var(--space-4, 16px);
  }

  .question {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
    margin: 0;
  }

  .packet-label {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  .question p {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: 1.55;
    color: var(--text);
    margin: 0;
    padding: var(--space-2, 8px) 0;
  }

  .stream {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 8px);
  }

  .answer {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    margin: 0;
    white-space: pre-wrap;
    background: var(--surface-prose, transparent);
    border-top: 1px solid var(--border);
    padding: var(--space-3, 12px) 0 0;
  }

  .tool-call {
    display: flex;
    gap: var(--space-2, 8px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: var(--type-chrome-lh, 1.20);
    color: var(--text-muted);
    margin: 0;
    border-top: 1px solid var(--border);
    padding-top: var(--space-2, 8px);
  }

  .tool-call span {
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  .reasoning {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
    background-color: var(--surface-raised, var(--bg-elev));
    padding: var(--space-2, 8px) var(--space-3, 12px);
    margin: 0;
    border-left: 1px solid var(--border);
    white-space: pre-wrap;
    overflow-x: auto;
  }

  .reasoning-toggle {
    align-self: flex-start;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-faint);
  }

  .reasoning-toggle:hover {
    color: var(--accent);
  }

  .error {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--signal-danger, #c0392b);
    margin: 0;
  }
</style>
