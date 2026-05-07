import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("$lib/api/sse.js", () => ({ streamSse: vi.fn() }));
vi.mock("$lib/api/client.js", () => ({ apiGet: vi.fn() }));

import { apiGet } from "$lib/api/client.js";
import { streamSse } from "$lib/api/sse.js";
import { getAskSession } from "./session.svelte";

function installStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => store.set(key, value)),
    removeItem: vi.fn((key: string) => store.delete(key)),
  });
}

describe("AskSessionState", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    installStorage();
  });

  it("recovers a background-interrupted ask run instead of ending with a network error", async () => {
    const streamMock = vi.mocked(streamSse);
    const getMock = vi.mocked(apiGet);
    streamMock.mockImplementation(async (_path, body, onEvent) => {
      expect((body as { ask_run_id?: string }).ask_run_id).toMatch(/^web-run-/);
      onEvent("content", { type: "content", content: "partial" });
      throw new Error("Ask stream interrupted: network error");
    });
    getMock.mockResolvedValue({
      run_id: "web-run-test",
      status: "done",
      chunks: [
        {
          seq: 0,
          event: "content",
          data: { type: "content", content: "recovered" },
        },
      ],
      result: { response: "recovered" },
      error: null,
    });

    const session = getAskSession(`recover-${Date.now()}`);
    session.hydrate();
    await session.submit("hello");

    expect(session.busy).toBe(false);
    expect(session.turns).toHaveLength(1);
    expect(session.turns[0].answer).toBe("recovered");
    expect(session.turns[0].done).toBe(true);
    expect(session.turns[0].items).toEqual([]);
    expect(getMock).toHaveBeenCalledWith(
      expect.stringContaining("/ask/runs/web-run-"),
    );
  });

  it("labels auto model selections with the resolved model", async () => {
    const getMock = vi.mocked(apiGet);
    getMock.mockResolvedValue({
      model: "auto",
      resolved_model: "test/resolved-model",
      reasoning_effort: "medium",
    });

    const session = getAskSession(`auto-model-${Date.now()}`);
    await session.loadOptions();

    expect(session.modelLabel).toBe("test/resolved-model (auto)");
  });

  it("labels explicit model selections without an auto suffix", async () => {
    const getMock = vi.mocked(apiGet);
    getMock.mockResolvedValue({
      model: "test/explicit-model",
      resolved_model: "test/explicit-model",
      reasoning_effort: "medium",
    });

    const session = getAskSession(`explicit-model-${Date.now()}`);
    await session.loadOptions();

    expect(session.modelLabel).toBe("test/explicit-model");
  });

  it("streams one ask turn into transcript items, managed tasks, and persisted context", async () => {
    const streamMock = vi.mocked(streamSse);
    streamMock.mockImplementation(async (_path, body, onEvent) => {
      expect(body).toMatchObject({
        query: "What changed?",
        ask_session_id: expect.stringMatching(/^web-/),
        ask_run_id: expect.stringMatching(/^web-run-/),
      });
      expect((body as { context?: string }).context).toContain(
        "Previous answer",
      );
      onEvent("content", { type: "content", content: "Answer part." });
      onEvent("tool_call", { name: "search", arguments: { query: "pkm" } });
      onEvent("tool_call", {
        name: "manage_tasks",
        arguments: JSON.stringify({
          tasks: [
            { id: "read", text: "Read coverage report", status: "in-progress" },
            { text: "Patch tests", done: true },
          ],
        }),
      });
      onEvent("reasoning", { text: "Inspect likely bottlenecks." });
      onEvent("task", { message: "Run focused tests." });
      onEvent("error", { reason: "Recoverable warning" });
      onEvent("result", { response: "Final fallback answer" });
    });

    const session = getAskSession(`stream-${Date.now()}`);
    session.hydrate();
    session.turns = [
      {
        question: "Previous question",
        items: [],
        answer: "Previous answer",
        done: true,
      },
    ];

    await session.submit("What changed?");

    expect(streamSse).toHaveBeenCalledTimes(1);
    expect(session.busy).toBe(false);
    expect(session.turns).toHaveLength(2);
    expect(session.turns[0]).toMatchObject({
      question: "Previous question",
      answer: "Previous answer",
      done: true,
    });
    expect(session.turns[1]).toMatchObject({
      question: "What changed?",
      answer: "Answer part.",
      done: true,
    });
    expect(session.turns[1].items).toEqual([
      {
        kind: "tool_call",
        tool: "search",
        args: JSON.stringify({ query: "pkm" }),
      },
      { kind: "reasoning", text: "Inspect likely bottlenecks." },
      { kind: "task", text: "Run focused tests." },
      { kind: "error", message: "Recoverable warning" },
    ]);
    expect(session.managedTasks).toEqual([
      {
        id: "read",
        text: "Read coverage report",
        checked: false,
        status: "in_progress",
      },
      {
        id: "1-Patch tests",
        text: "Patch tests",
        checked: true,
        status: "pending",
      },
    ]);
    expect(localStorage.setItem).toHaveBeenCalledWith(
      expect.stringContaining("pkm.askSession.stream-"),
      expect.stringContaining("What changed?"),
    );
  });

  it("treats /new as a local reset without starting an ask stream", async () => {
    const session = getAskSession(`reset-${Date.now()}`);
    session.hydrate();
    session.turns = [
      {
        question: "old",
        items: [],
        answer: "old answer",
        done: true,
      },
    ];
    session.managedTasks = [
      {
        id: "old-task",
        text: "Old task",
        checked: false,
        status: "pending",
      },
    ];

    await expect(session.submit("/new")).resolves.toBeNull();

    expect(streamSse).not.toHaveBeenCalled();
    expect(session.turns).toEqual([]);
    expect(session.managedTasks).toEqual([]);
    expect(localStorage.removeItem).toHaveBeenCalledWith(
      expect.stringContaining("pkm.askSession.reset-"),
    );
  });

  it("hydrates recent valid turns and ignores malformed cached entries", () => {
    const turns = Array.from({ length: 22 }, (_, index) => ({
      question: `q${index}`,
      items: [],
      answer: `a${index}`,
      done: true,
    }));
    vi.mocked(localStorage.getItem).mockReturnValueOnce(
      JSON.stringify({
        version: 3,
        savedAt: Date.now(),
        sessionId: "web-existing",
        turns: [...turns, { question: 1, items: [], answer: "bad" }],
        managedTasks: [
          { text: "keep task", status: "pending" },
          { nope: true },
        ],
      }),
    );

    const session = getAskSession(`hydrate-${Date.now()}`);
    session.hydrate();

    expect(session.turns).toHaveLength(20);
    expect(session.turns[0].question).toBe("q2");
    expect(session.turns.at(-1)?.question).toBe("q21");
    expect(session.managedTasks).toEqual([
      { text: "keep task", status: "pending" },
    ]);
  });

  it("tracks submitted query parameters and falls back to auto on options load failure", async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error("offline"));
    const session = getAskSession(`query-param-${Date.now()}`);

    expect(session.claimQueryParam("hello")).toBe(true);
    expect(session.claimQueryParam("hello")).toBe(false);
    session.clearQueryParam();
    expect(session.claimQueryParam("hello")).toBe(true);

    await session.loadOptions();
    expect(session.modelLabel).toBe("auto");
  });
});
