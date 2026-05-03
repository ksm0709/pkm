<script lang="ts">
  interface Props {
    value?: string;
    busy?: boolean;
    onsubmit: (text: string) => void;
  }

  let { value = $bindable(''), busy = false, onsubmit }: Props = $props();

  let textareaEl: HTMLTextAreaElement | null = $state(null);

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      const text = value.trim();
      if (!text || busy) return;
      onsubmit(text);
      value = '';
      // Reset visible height
      if (textareaEl) textareaEl.style.height = 'auto';
    }
    // Plain Enter inserts newline (default textarea behavior)
  }

  function autoresize() {
    if (!textareaEl) return;
    textareaEl.style.height = 'auto';
    textareaEl.style.height = `${Math.min(textareaEl.scrollHeight, 240)}px`;
  }
</script>

<form
  class="ask-input"
  onsubmit={(e) => {
    e.preventDefault();
    const text = value.trim();
    if (!text || busy) return;
    onsubmit(text);
    value = '';
    if (textareaEl) textareaEl.style.height = 'auto';
  }}
>
  <span class="prompt-mark" aria-hidden="true">ASK</span>
  <textarea
    bind:this={textareaEl}
    bind:value
    class="ask-textarea"
    placeholder={busy ? 'Streaming…' : 'Ask… (⌘↵ to submit, ↵ newline)'}
    rows="1"
    onkeydown={handleKeydown}
    oninput={autoresize}
    disabled={busy}
    spellcheck="false"
  ></textarea>
  <button
    type="submit"
    class="submit-btn"
    disabled={busy || !value.trim()}
    aria-label="Submit"
  >
    ⌘↵
  </button>
</form>

<style>
  .ask-input {
    position: sticky;
    bottom: 0;
    display: flex;
    align-items: center;
    gap: var(--space-2, 8px);
    min-height: 56px;
    padding: var(--space-2, 8px) var(--space-4, 16px);
    background-color: var(--surface, var(--bg));
    border-top: 1px solid var(--border);
    border-left: 2px solid var(--accent);
  }

  .prompt-mark {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.12em;
    color: var(--accent);
    flex-shrink: 0;
  }

  .ask-textarea {
    flex: 1;
    resize: none;
    min-height: 32px;
    max-height: 240px;
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.70);
    color: var(--text);
    background-color: transparent;
    border: none;
    border-left: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    padding: var(--space-1, 4px) var(--space-2, 8px) var(--space-1, 4px) var(--space-3, 12px);
    outline: none;
    caret-color: var(--accent);
  }

  .ask-textarea:focus {
    border-left-color: var(--accent);
  }

  .ask-textarea::placeholder {
    color: var(--text-faint);
  }

  .submit-btn {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--accent);
    background-color: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm, 2px);
    padding: var(--space-2, 8px) var(--space-3, 12px);
    cursor: pointer;
    flex-shrink: 0;
  }

  .submit-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .submit-btn:not(:disabled):hover {
    color: var(--bg);
    background: var(--accent);
    border-color: var(--accent);
  }

  @media (max-width: 640px) {
    .prompt-mark {
      display: none;
    }
  }
</style>
