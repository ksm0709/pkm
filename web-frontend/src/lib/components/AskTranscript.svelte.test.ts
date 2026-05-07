// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import AskTranscript from "./AskTranscript.svelte";

describe("AskTranscript", () => {
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("renders completed assistant turns with reasoning, tool, task, error, and markdown answer blocks", async () => {
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(AskTranscript, {
      target,
      props: {
        turns: [
          {
            question: "What changed?",
            answer: "**Coverage** improved with [tests](https://example.test).",
            done: true,
            items: [
              { kind: "reasoning", text: "Inspect coverage report" },
              { kind: "tool_call", tool: "vitest", args: "run coverage" },
              { kind: "task", text: "Add scenario tests" },
              { kind: "error", message: "Branch gate still low" },
            ],
          },
        ],
      },
    });
    await tick();

    expect(
      target.querySelector('[aria-label="User message"]')?.textContent,
    ).toContain("What changed?");
    expect(
      target.querySelector('[aria-label="Thinking details"]')?.textContent,
    ).toContain("thinking");
    expect(target.querySelector(".thinking pre")?.textContent).toBe(
      "Inspect coverage report",
    );
    expect(
      target.querySelector('[aria-label="Tool use details vitest"]')
        ?.textContent,
    ).toContain("vitest");
    expect(target.querySelector(".tool-use pre")?.textContent).toBe(
      "run coverage",
    );
    expect(target.querySelector(".task")?.textContent).toContain(
      "Add scenario tests",
    );
    expect(target.querySelector(".error")?.textContent).toContain(
      "Branch gate still low",
    );
    expect(
      target.querySelector('[aria-label="Assistant message"] strong')
        ?.textContent,
    ).toBe("Coverage");
    expect(
      target.querySelector<HTMLAnchorElement>(
        '[aria-label="Assistant message"] a',
      )?.href,
    ).toBe("https://example.test/");
    expect(target.querySelector(".agent-activity")).toBeNull();

    unmount(component);
  });

  it("shows and advances the in-progress activity indicator until unmounted", async () => {
    vi.useFakeTimers();
    const target = document.createElement("div");
    document.body.appendChild(target);

    const component = mount(AskTranscript, {
      target,
      props: {
        turns: [
          {
            question: "Still working?",
            answer: "",
            done: false,
            items: [],
          },
        ],
      },
    });
    await tick();

    expect(target.querySelector(".activity-frame")?.textContent).toBe("[=   ]");

    await vi.advanceTimersByTimeAsync(320);
    await tick();

    expect(target.querySelector(".activity-frame")?.textContent).toBe("[==  ]");

    unmount(component);
  });
});
