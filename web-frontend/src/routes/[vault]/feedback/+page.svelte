<script lang="ts">
  import { page } from "$app/stores";
  import { apiClient, apiGet } from "$lib/api/client.js";

  type FeedbackType = "requirement" | "bug" | "idea";

  interface FeedbackRecord {
    note_id: string;
    title: string;
    description: string;
    feedback_type: FeedbackType;
    created_at: string;
    email_status?: "sent" | "not_configured" | "failed";
    email_recipient?: string;
  }

  const feedbackTypeLabels: Record<FeedbackType, string> = {
    requirement: "Requirement",
    bug: "Problem",
    idea: "Idea",
  };

  let vaultName = $derived($page.params.vault);
  let records = $state<FeedbackRecord[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state("");
  let success = $state("");
  let title = $state("");
  let description = $state("");
  let feedbackType = $state<FeedbackType>("requirement");
  let loadedVault = "";

  async function loadFeedback(vault: string) {
    loading = true;
    error = "";
    try {
      const result = await apiGet<FeedbackRecord[]>(
        `/api/v1/vault/${encodeURIComponent(vault)}/feedback`,
      );
      if (vaultName !== vault) return;
      records = Array.isArray(result) ? result : [];
    } catch (cause) {
      if (vaultName !== vault) return;
      error =
        cause instanceof Error ? cause.message : "Failed to load feedback.";
      records = [];
    } finally {
      if (vaultName === vault) loading = false;
    }
  }

  async function responseMessage(response: Response) {
    try {
      const body = (await response.json()) as { message?: string };
      if (body.message) return body.message;
    } catch {
      // The server's standard HTTP error is plain text.
    }
    return `Feedback submission failed (${response.status}).`;
  }

  async function submitFeedback(event: SubmitEvent) {
    event.preventDefault();
    if (busy) return;

    const currentTitle = title.trim();
    const currentDescription = description.trim();
    if (!currentTitle || !currentDescription) {
      error = "Add both a concise title and the requirement details.";
      success = "";
      return;
    }

    const vault = vaultName;
    busy = true;
    error = "";
    success = "";
    try {
      const response = await apiClient(
        `/api/v1/vault/${encodeURIComponent(vault)}/feedback`,
        {
          method: "POST",
          body: JSON.stringify({
            title: currentTitle,
            description: currentDescription,
            feedback_type: feedbackType,
          }),
        },
      );
      if (response.status !== 201)
        throw new Error(await responseMessage(response));
      const record = (await response.json()) as FeedbackRecord;
      if (vaultName !== vault) return;
      records = [record, ...records];
      title = "";
      description = "";
      feedbackType = "requirement";
      if (record.email_status === "sent") {
        success = `Saved to this vault and emailed to ${record.email_recipient ?? "your inbox"}.`;
      } else if (record.email_status === "not_configured") {
        success = "Saved to this vault. Email delivery needs SMTP setup.";
      } else if (record.email_status === "failed") {
        success = "Saved to this vault, but email delivery failed.";
      } else {
        success = "Saved to this vault and linked from today's daily log.";
      }
    } catch (cause) {
      if (vaultName !== vault) return;
      error =
        cause instanceof Error ? cause.message : "Failed to save feedback.";
    } finally {
      if (vaultName === vault) busy = false;
    }
  }

  function formatTimestamp(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return value || "Unknown time";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  $effect(() => {
    const vault = vaultName;
    if (!vault || loadedVault === vault) return;
    loadedVault = vault;
    records = [];
    success = "";
    void loadFeedback(vault);
  });
</script>

<svelte:head>
  <title>Feedback — {vaultName} — pkm</title>
</svelte:head>

<main class="feedback-page">
  <header class="feedback-header">
    <div>
      <span class="meta-rail">VAULT INPUT</span>
      <h1>Feedback desk</h1>
      <p>
        Keep product requirements close to the work. Every entry becomes a
        tagged PKM subnote and is linked from today’s log.
      </p>
    </div>
    <div
      class="record-counter"
      aria-label={`${records.length} saved feedback records`}
    >
      <strong>{records.length}</strong>
      <span>saved<br />requests</span>
    </div>
  </header>

  <section class="submission-panel" aria-labelledby="feedback-form-heading">
    <div class="panel-heading">
      <span>NEW ENTRY</span>
      <h2 id="feedback-form-heading">What should change?</h2>
    </div>

    <form onsubmit={submitFeedback}>
      <div class="type-picker" aria-label="Feedback type">
        {#each Object.entries(feedbackTypeLabels) as [value, label]}
          <label class:chosen={feedbackType === value}>
            <input
              type="radio"
              name="feedback-type"
              {value}
              checked={feedbackType === value}
              onchange={() => (feedbackType = value as FeedbackType)}
            />
            <span>{label}</span>
          </label>
        {/each}
      </div>

      <label class="field">
        <span>Short title</span>
        <input
          bind:value={title}
          maxlength="120"
          placeholder="A clear, testable request"
          required
        />
      </label>

      <label class="field">
        <span>Context and desired outcome</span>
        <textarea
          bind:value={description}
          maxlength="8000"
          rows="6"
          placeholder="What happened, who needs this, and what a good result looks like."
          required
        ></textarea>
      </label>

      <div class="form-footer">
        <span class="field-limit"
          >{description.length.toLocaleString()} / 8,000</span
        >
        <button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save feedback"}
        </button>
      </div>
    </form>

    <div class="status-stack" aria-live="polite">
      {#if error}<p class="status error">{error}</p>{/if}
      {#if success}<p class="status success">{success}</p>{/if}
    </div>
  </section>

  <section class="feedback-ledger" aria-labelledby="saved-feedback-heading">
    <div class="ledger-heading">
      <span class="meta-rail">ARCHIVE</span>
      <h2 id="saved-feedback-heading">Saved feedback</h2>
    </div>

    {#if loading}
      <p class="empty-state">Loading the vault feedback ledger…</p>
    {:else if records.length === 0}
      <p class="empty-state">
        No feedback yet. Capture the first requirement above.
      </p>
    {:else}
      <ol class="feedback-list">
        {#each records as record (record.note_id)}
          <li class="feedback-record">
            <div class="record-rail">
              <span class="record-type"
                >{feedbackTypeLabels[record.feedback_type] ?? "Feedback"}</span
              >
              <time datetime={record.created_at}
                >{formatTimestamp(record.created_at)}</time
              >
            </div>
            <div class="record-body">
              <h3>{record.title}</h3>
              <p>{record.description}</p>
              <a
                href={`/${vaultName}/notes/${encodeURIComponent(record.note_id)}`}
              >
                Open source note <span aria-hidden="true">↗</span>
              </a>
            </div>
          </li>
        {/each}
      </ol>
    {/if}
  </section>
</main>

<style>
  .feedback-page {
    width: min(100% - 2 * var(--space-5, 24px), 980px);
    margin: 0 auto;
    padding: var(--space-7, 48px) 0 var(--space-8, 64px);
  }

  .feedback-header {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: end;
    gap: var(--space-6, 32px);
    padding: 0 0 var(--space-6, 32px);
    border-bottom: 1px solid var(--border);
  }

  .meta-rail,
  .panel-heading > span,
  .record-type,
  .field > span,
  .field-limit,
  .record-counter span {
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: 600;
    letter-spacing: 0.13em;
    text-transform: uppercase;
  }

  h1,
  h2,
  h3,
  p {
    margin: 0;
  }

  h1,
  h2,
  h3 {
    color: var(--text);
  }

  h1 {
    margin-top: var(--space-2, 8px);
    font-family: var(--font-serif);
    font-size: clamp(2.2rem, 5vw, 4.3rem);
    font-weight: 400;
    line-height: 0.95;
    letter-spacing: -0.045em;
  }

  .feedback-header p {
    max-width: 55ch;
    margin-top: var(--space-4, 16px);
    color: var(--text-muted);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.72);
  }

  .record-counter {
    display: flex;
    align-items: center;
    gap: var(--space-3, 12px);
    padding: var(--space-3, 12px) 0 var(--space-3, 12px) var(--space-4, 16px);
    border-left: 2px solid var(--signal);
  }

  .record-counter strong {
    color: var(--signal);
    font-family: var(--font-serif);
    font-size: 2.6rem;
    font-weight: 400;
    line-height: 0.8;
  }

  .record-counter span {
    line-height: 1.25;
  }

  .submission-panel {
    margin-top: var(--space-6, 32px);
    padding: clamp(20px, 4vw, 36px);
    background: var(--surface-prose);
    border: 1px solid var(--border);
    border-top: 2px solid var(--signal);
  }

  .panel-heading h2,
  .ledger-heading h2 {
    margin-top: var(--space-2, 8px);
    font-family: var(--font-serif);
    font-size: clamp(1.65rem, 3vw, 2.35rem);
    font-weight: 400;
    letter-spacing: -0.03em;
  }

  form {
    margin-top: var(--space-5, 24px);
  }

  .type-picker {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    margin-bottom: var(--space-5, 24px);
  }

  .type-picker label {
    cursor: pointer;
  }

  .type-picker input {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
  }

  .type-picker span {
    display: block;
    padding: 7px 10px;
    color: var(--text-muted);
    border: 1px solid var(--border);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .type-picker label.chosen span,
  .type-picker label:focus-within span {
    color: var(--accent-on);
    background: var(--signal);
    border-color: var(--signal);
    outline: none;
  }

  .field {
    display: block;
    margin-top: var(--space-4, 16px);
  }

  .field > span {
    display: block;
    margin-bottom: var(--space-2, 8px);
  }

  input,
  textarea {
    box-sizing: border-box;
    width: 100%;
    padding: 11px 12px;
    color: var(--text);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 0;
    font: inherit;
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.72);
  }

  textarea {
    resize: vertical;
    min-height: 154px;
  }

  input:focus-visible,
  textarea:focus-visible {
    border-color: var(--signal);
    outline: 1px solid var(--signal);
    outline-offset: 2px;
  }

  .form-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4, 16px);
    margin-top: var(--space-4, 16px);
  }

  button {
    min-height: 40px;
    padding: 0 16px;
    color: var(--accent-on);
    background: var(--signal);
    border: 1px solid var(--signal);
    border-radius: 0;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  button:hover:not(:disabled),
  button:focus-visible {
    filter: brightness(1.12);
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
  button:disabled {
    cursor: wait;
    opacity: 0.6;
  }

  .status-stack {
    min-height: 1.5rem;
    margin-top: var(--space-3, 12px);
  }
  .status {
    font-size: var(--type-chrome-size, 13px);
    line-height: 1.5;
  }
  .status.error {
    color: var(--danger, #e57373);
  }
  .status.success {
    color: var(--signal);
  }

  .feedback-ledger {
    margin-top: var(--space-8, 64px);
  }
  .ledger-heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: var(--space-4, 16px);
    padding-bottom: var(--space-4, 16px);
    border-bottom: 1px solid var(--border);
  }
  .empty-state {
    padding: var(--space-6, 32px) 0;
    color: var(--text-muted);
    font-size: var(--type-body-size, 15px);
  }

  .feedback-list {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .feedback-record {
    display: grid;
    grid-template-columns: minmax(130px, 0.28fr) minmax(0, 1fr);
    gap: var(--space-5, 24px);
    padding: var(--space-5, 24px) 0;
    border-bottom: 1px solid var(--border);
  }
  .record-rail {
    display: grid;
    align-content: start;
    gap: var(--space-2, 8px);
  }
  .record-type {
    color: var(--signal);
  }
  time {
    color: var(--text-faint);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    line-height: 1.4;
  }
  .record-body h3 {
    font-family: var(--font-serif);
    font-size: 1.45rem;
    font-weight: 400;
    letter-spacing: -0.02em;
  }
  .record-body p {
    margin-top: var(--space-2, 8px);
    white-space: pre-wrap;
    color: var(--text-muted);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.72);
  }
  .record-body a {
    display: inline-block;
    margin-top: var(--space-3, 12px);
    color: var(--signal);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: 600;
    letter-spacing: 0.07em;
    text-decoration-thickness: 1px;
    text-underline-offset: 3px;
    text-transform: uppercase;
  }
  .record-body a:hover,
  .record-body a:focus-visible {
    color: var(--text);
  }

  @media (max-width: 620px) {
    .feedback-page {
      width: min(100% - 2 * var(--space-4, 16px), 980px);
      padding-top: var(--space-5, 24px);
    }
    .feedback-header,
    .feedback-record {
      grid-template-columns: 1fr;
      gap: var(--space-4, 16px);
    }
    .record-counter {
      justify-self: start;
    }
    .feedback-record {
      padding: var(--space-4, 16px) 0;
    }
    .record-rail {
      grid-template-columns: auto 1fr;
      align-items: center;
    }
  }
</style>
