// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { apiGet } from "$lib/api/client.js";
import {
  applyInlineSuggestion,
  detectInlineTrigger,
  fetchInlineSuggestions,
} from "$lib/inline-suggestions.js";
import type { InlineTrigger } from "$lib/inline-suggestions.js";
import AskInput from "./AskInput.svelte";

vi.mock("$lib/api/client.js", () => ({ apiGet: vi.fn() }));
vi.mock("$lib/inline-suggestions.js", () => ({
  applyInlineSuggestion: vi.fn(),
  detectInlineTrigger: vi.fn(),
  fetchInlineSuggestions: vi.fn(),
}));

describe("AskInput", () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockResolvedValue([
      {
        id: "weekly-review",
        title: "Weekly Review",
        snippet: "summarize the week",
        pre_hook: "calendar",
        post_hook: "daily",
      },
    ]);
    vi.mocked(detectInlineTrigger).mockReturnValue(null);
    vi.mocked(fetchInlineSuggestions).mockResolvedValue([]);
    vi.mocked(applyInlineSuggestion).mockReset();
  });

  afterEach(() => {
    vi.mocked(apiGet).mockReset();
    vi.mocked(detectInlineTrigger).mockReset();
    vi.mocked(fetchInlineSuggestions).mockReset();
    vi.mocked(applyInlineSuggestion).mockReset();
    document.body.innerHTML = "";
  });

  async function flush() {
    await Promise.resolve();
    await tick();
  }

  function render(props = {}) {
    const target = document.createElement("div");
    document.body.appendChild(target);
    const onsubmit = vi.fn();
    const component = mount(AskInput, {
      target,
      props: {
        vaultName: "main",
        onsubmit,
        ...props,
      },
    });
    return { target, component, onsubmit };
  }

  it("submits trimmed text with the form button and clears the editor state", async () => {
    const { target, component, onsubmit } = render({
      value: "  explain coverage  ",
    });
    await flush();

    target.querySelector<HTMLButtonElement>(".submit-btn")?.click();
    await tick();

    expect(onsubmit).toHaveBeenCalledWith("explain coverage");
    expect(
      target.querySelector<HTMLTextAreaElement>(".ask-textarea")?.value,
    ).toBe("");
    expect(
      target.querySelector<HTMLButtonElement>(".submit-btn")?.disabled,
    ).toBe(true);

    unmount(component);
  });

  it("submits with command-enter while plain enter stays available for multiline input", async () => {
    const { target, component, onsubmit } = render({ value: "stream answer" });
    await flush();
    const textarea =
      target.querySelector<HTMLTextAreaElement>(".ask-textarea")!;

    textarea.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        bubbles: true,
        cancelable: true,
      }),
    );
    expect(onsubmit).not.toHaveBeenCalled();

    textarea.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        metaKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );
    await tick();

    expect(onsubmit).toHaveBeenCalledWith("stream answer");

    unmount(component);
  });

  it("locks input and submit affordances while a response is streaming", async () => {
    const { target, component, onsubmit } = render({
      value: "cannot submit",
      busy: true,
      modelLabel: "test-model",
    });
    await flush();

    const textarea = target.querySelector<HTMLTextAreaElement>(".ask-textarea");
    expect(textarea?.disabled).toBe(true);
    expect(textarea?.placeholder).toBe("Streaming…");
    expect(
      target.querySelector<HTMLButtonElement>(".submit-btn")?.disabled,
    ).toBe(true);
    const modelSelect =
      target.querySelector<HTMLSelectElement>(".model-select");
    expect(modelSelect?.disabled).toBe(true);
    expect(modelSelect?.title).toBe("Current model: test-model");

    target
      .querySelector<HTMLFormElement>("form")
      ?.dispatchEvent(
        new SubmitEvent("submit", { bubbles: true, cancelable: true }),
      );
    expect(onsubmit).not.toHaveBeenCalled();

    unmount(component);
  });

  it("emits model changes from the model dropdown", async () => {
    const onmodelchange = vi.fn();
    const { target, component } = render({
      selectedModel: "auto",
      modelOptions: ["auto", "gpt-4o-mini"],
      onmodelchange,
    });
    await flush();

    const modelSelect =
      target.querySelector<HTMLSelectElement>(".model-select")!;
    modelSelect.value = "gpt-4o-mini";
    modelSelect.dispatchEvent(new Event("change", { bubbles: true }));
    await tick();

    expect(onmodelchange).toHaveBeenCalledWith("gpt-4o-mini");

    unmount(component);
  });

  it("loads workflow slash commands and completes the selected workflow command", async () => {
    const { target, component } = render({ value: "/weekly" });
    await flush();

    expect(apiGet).toHaveBeenCalledWith("/api/v1/vault/main/workflows");
    const workflowRow = [
      ...target.querySelectorAll<HTMLElement>(".slash-row"),
    ].find((row) => row.textContent?.includes("Weekly Review"));
    expect(workflowRow?.textContent).toContain("/workflow weekly-review");

    workflowRow?.click();
    await tick();

    expect(
      target.querySelector<HTMLTextAreaElement>(".ask-textarea")?.value,
    ).toBe("/workflow weekly-review");
    expect(target.querySelector('[aria-label="Slash commands"]')).toBeNull();

    unmount(component);
  });

  it("ranks workflow title matches ahead of generic skill keywords", async () => {
    vi.mocked(apiGet).mockResolvedValueOnce([
      {
        id: "zettelkasten_maintenance",
        title: "Zettelkasten Maintenance",
        snippet: "Execute maintenance workflow",
        pre_hook: null,
        post_hook: null,
      },
    ]);

    const { target, component } = render({ value: "/zettel" });
    await flush();

    const firstRow = target.querySelector<HTMLElement>(".slash-row");
    expect(firstRow?.textContent).toContain(
      "/workflow zettelkasten_maintenance",
    );

    unmount(component);
  });

  it("supports keyboard navigation, completion, and escape for slash commands", async () => {
    const { target, component } = render({ value: "/pkm" });
    await flush();
    const textarea =
      target.querySelector<HTMLTextAreaElement>(".ask-textarea")!;

    textarea.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "ArrowDown",
        bubbles: true,
        cancelable: true,
      }),
    );
    await tick();
    textarea.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        bubbles: true,
        cancelable: true,
      }),
    );
    await tick();

    expect(textarea.value).toBe("/pkm:diagnosis");
    expect(target.querySelector('[aria-label="Slash commands"]')).toBeNull();

    textarea.value = "/pkm";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await tick();
    textarea.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      }),
    );
    await tick();

    expect(textarea.value).toBe("");

    unmount(component);
  });

  it("applies inline suggestions from click and keyboard selection", async () => {
    const trigger: InlineTrigger = {
      kind: "note",
      query: "pk",
      from: 4,
      to: 8,
    };
    vi.mocked(detectInlineTrigger).mockReturnValue(trigger);
    vi.mocked(fetchInlineSuggestions).mockResolvedValue([
      {
        kind: "note",
        label: "pkm-plan",
        title: "PKM Plan",
        detail: "note",
        insert: "[[pkm-plan]]",
        score: 0,
      },
    ]);
    vi.mocked(applyInlineSuggestion).mockReturnValue({
      value: "See [[pkm-plan]]",
      cursor: "See [[pkm-plan]]".length,
    });
    const { target, component } = render({ value: "See [[pk" });
    await flush();
    await flush();

    expect(fetchInlineSuggestions).toHaveBeenCalledWith("main", trigger);
    expect(target.querySelector(".inline-suggest-row")?.textContent).toContain(
      "pkm-plan",
    );

    target.querySelector<HTMLElement>(".inline-suggest-row")?.click();
    await tick();

    expect(applyInlineSuggestion).toHaveBeenCalledWith(
      "See [[pk",
      trigger,
      expect.objectContaining({ label: "pkm-plan" }),
    );
    expect(
      target.querySelector<HTMLTextAreaElement>(".ask-textarea")?.value,
    ).toBe("See [[pkm-plan]]");

    unmount(component);
  });
});
