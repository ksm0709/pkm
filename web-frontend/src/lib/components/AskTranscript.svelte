<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { marked } from "marked";
  import type { AskItem, AskTurn } from "$lib/ask/session.svelte";

  export type Turn = AskTurn;

  interface Props {
    turns: Turn[];
  }

  let { turns = [] }: Props = $props();
  const activityFrames = [
    "[=   ]",
    "[==  ]",
    "[ ===]",
    "[  ==]",
    "[   =]",
    "[  ==]",
    "[ ===]",
    "[==  ]",
  ];
  let activityFrame = $state(0);
  let activityTimer: ReturnType<typeof setInterval> | null = null;

  onMount(() => {
    activityTimer = setInterval(() => {
      activityFrame = (activityFrame + 1) % activityFrames.length;
    }, 320);
  });

  onDestroy(() => {
    if (activityTimer) {
      clearInterval(activityTimer);
      activityTimer = null;
    }
  });

  function renderMarkdown(text: string) {
    return marked.parse(text, { async: false }) as string;
  }

  function toolLabel(item: Extract<AskItem, { kind: "tool_call" }>) {
    return item.tool;
  }
</script>

<div class="transcript">
  {#each turns as turn, ti (`${ti}-${turn.question}`)}
    <article class="turn">
      <section class="chat-message user" aria-label="User message">
        <div class="message-label">YOU</div>
        <p>{turn.question}</p>
      </section>

      <section class="assistant-stream" aria-label="Assistant events">
        {#each turn.items as item, ii (`${ii}-${item.kind}`)}
          {#if item.kind === "reasoning"}
            <details class="chat-event disclosure thinking">
              <summary aria-label="Thinking details">
                <span class="event-icon" aria-label="Thinking" title="Thinking"
                  >⋯</span
                >
                <span>thinking</span>
              </summary>
              <pre class="event-detail">{item.text}</pre>
            </details>
          {:else if item.kind === "tool_call"}
            <details class="chat-event disclosure tool-use">
              <summary aria-label={`Tool use details ${toolLabel(item)}`}>
                <span class="event-icon" aria-label="Tool use" title="Tool use"
                  >⌘</span
                >
                <span>{toolLabel(item)}</span>
              </summary>
              {#if item.args}
                <pre class="event-detail">{item.args}</pre>
              {/if}
            </details>
          {:else if item.kind === "task"}
            <div class="chat-event task">
              <span class="event-icon" aria-label="Task" title="Task">☑</span>
              <span>{item.text}</span>
            </div>
          {:else if item.kind === "error"}
            <div class="chat-event error">
              <span class="event-icon" aria-label="Error" title="Error">!</span>
              <span>{item.message}</span>
            </div>
          {/if}
        {/each}

        {#if turn.answer}
          <div class="chat-message assistant" aria-label="Assistant message">
            {@html renderMarkdown(turn.answer)}
          </div>
        {/if}

        {#if !turn.done}
          <div
            class="chat-event agent-activity"
            aria-live="polite"
            aria-label="Agent turn in progress"
          >
            <span class="event-icon" aria-hidden="true">::</span>
            <span>
              <span class="activity-frame">{activityFrames[activityFrame]}</span
              >
              <span class="activity-label">agent turn</span>
            </span>
          </div>
        {/if}
      </section>
    </article>
  {/each}
</div>

<style>
  .transcript {
    display: flex;
    flex-direction: column;
    gap: var(--space-7, 48px);
    width: 100%;
    max-width: 100%;
    padding-top: var(--space-6, 32px);
    padding-bottom: var(--space-7, 48px);
    overflow-wrap: anywhere;
  }

  .turn {
    display: flex;
    flex-direction: column;
    gap: var(--space-3, 12px);
    max-width: 100%;
  }

  .chat-message,
  .chat-event {
    max-width: 100%;
    background-color: transparent;
    border: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .chat-message.user {
    display: flex;
    flex-direction: column;
    gap: var(--space-1, 4px);
    color: var(--text);
  }

  .message-label {
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: var(--type-chrome-lh, 1.2);
    text-transform: uppercase;
  }

  .chat-message.user p {
    margin: 0;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    line-height: var(--type-chrome-lh, 1.35);
    white-space: pre-wrap;
  }

  .assistant-stream {
    display: flex;
    flex-direction: column;
    gap: var(--space-2, 8px);
    max-width: 100%;
  }

  .chat-event {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr);
    column-gap: var(--space-2, 8px);
    align-items: start;
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1.45;
  }

  .chat-event.error {
    color: var(--signal-danger, #c0392b);
  }

  .agent-activity {
    color: var(--text-muted);
  }

  .activity-frame {
    display: inline-block;
    min-width: 6ch;
    color: var(--accent);
  }

  .activity-label {
    color: var(--text-faint);
  }

  .chat-event.disclosure {
    display: block;
  }

  .chat-event.disclosure summary {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr);
    column-gap: var(--space-2, 8px);
    align-items: start;
    list-style: none;
    cursor: pointer;
  }

  .chat-event.disclosure summary::-webkit-details-marker {
    display: none;
  }

  .chat-event.disclosure summary:hover {
    color: var(--text-muted);
  }

  .event-detail {
    margin: var(--space-2, 8px) 0 0 26px;
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1.45;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .event-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1;
  }

  .chat-message.assistant {
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
  }

  .chat-message.assistant :global(*) {
    max-width: 100%;
  }

  .chat-message.assistant :global(p),
  .chat-message.assistant :global(ul),
  .chat-message.assistant :global(ol),
  .chat-message.assistant :global(pre),
  .chat-message.assistant :global(blockquote) {
    margin: 0 0 var(--space-3, 12px);
  }

  .chat-message.assistant :global(h1),
  .chat-message.assistant :global(h2),
  .chat-message.assistant :global(h3) {
    margin: var(--space-4, 16px) 0 var(--space-2, 8px);
    color: var(--text);
    font-family: var(--font-mono);
    font-weight: 650;
    line-height: 1.25;
  }

  .chat-message.assistant :global(h1:first-child),
  .chat-message.assistant :global(h2:first-child),
  .chat-message.assistant :global(h3:first-child),
  .chat-message.assistant :global(p:first-child) {
    margin-top: 0;
  }

  .chat-message.assistant :global(h2) {
    font-size: 1.08rem;
  }

  .chat-message.assistant :global(ul),
  .chat-message.assistant :global(ol) {
    padding-left: 1.35rem;
  }

  .chat-message.assistant :global(li + li) {
    margin-top: var(--space-1, 4px);
  }

  .chat-message.assistant :global(code) {
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 0.94em;
    overflow-wrap: anywhere;
  }

  .chat-message.assistant :global(a) {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .chat-message.assistant :global(pre) {
    overflow-x: auto;
    white-space: pre-wrap;
  }
</style>
