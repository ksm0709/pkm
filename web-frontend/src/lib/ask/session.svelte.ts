import { apiGet } from "$lib/api/client.js";
import { streamSse } from "$lib/api/sse.js";

export type AskItem =
  | { kind: "tool_call"; tool: string; args: string }
  | { kind: "reasoning"; text: string }
  | { kind: "task"; text: string }
  | { kind: "content"; text: string }
  | { kind: "error"; message: string };

export interface AskTurn {
  question: string;
  items: AskItem[];
  answer: string;
  done: boolean;
  runId?: string;
}

export type ManagedTaskStatus =
  | "done"
  | "in_progress"
  | "cancelled"
  | "pending";

export type ManagedTask = {
  id: string;
  text: string;
  checked: boolean;
  status: ManagedTaskStatus;
};

type AskSessionSnapshot = {
  version: number;
  savedAt: number;
  sessionId: string;
  turns: AskTurn[];
  managedTasks: ManagedTask[];
};

type AskRunSnapshot = {
  run_id: string;
  status: "running" | "done" | "error" | string;
  chunks?: Array<{
    seq?: number;
    event?: string;
    data?: unknown;
  }>;
  result?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
};

const ASK_SESSION_VERSION = 3;
const ASK_SESSION_MAX_TURNS = 20;
const ASK_RUN_RECOVERY_ATTEMPTS = 120;
const ASK_RUN_RECOVERY_DELAY_MS = 2000;
const sessions = new Map<string, AskSessionState>();

export function getAskSession(vaultName: string) {
  let session = sessions.get(vaultName);
  if (!session) {
    session = new AskSessionState(vaultName);
    sessions.set(vaultName, session);
  }
  return session;
}

export class AskSessionState {
  turns = $state<AskTurn[]>([]);
  busy = $state(false);
  modelLabel = $state("auto");
  selectedModel = $state("auto");
  modelOptions = $state<string[]>(["auto"]);
  managedTasks = $state<ManagedTask[]>([]);
  submittedQueryParam = $state("");
  hydrated = $state(false);

  #sessionId = createAskSessionId();
  #activeRun: Promise<void> | null = null;

  constructor(readonly vaultName: string) {}

  hydrate() {
    if (this.hydrated) return;
    this.hydrated = true;
    if (typeof localStorage === "undefined") return;
    try {
      const raw = localStorage.getItem(this.#storageKey());
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<AskSessionSnapshot>;
      if (
        ![1, 2, ASK_SESSION_VERSION].includes(parsed.version ?? 0) ||
        !Array.isArray(parsed.turns)
      ) {
        return;
      }
      if (
        typeof parsed.sessionId === "string" &&
        parsed.sessionId.startsWith("web-")
      ) {
        this.#sessionId = parsed.sessionId;
      }
      this.turns = parsed.turns
        .filter(validTurn)
        .slice(-ASK_SESSION_MAX_TURNS)
        .map((turn) => ({
          ...turn,
          done: turn.runId ? Boolean(turn.done) : true,
        }));
      this.managedTasks = Array.isArray(parsed.managedTasks)
        ? parsed.managedTasks.filter(
            (task) => task && typeof task.text === "string",
          )
        : [];
      const pending = [...this.turns]
        .reverse()
        .find((turn) => turn.runId && !turn.done);
      if (pending?.runId) {
        this.busy = true;
        this.#activeRun = this.#recoverPendingRun(pending.runId);
      }
    } catch {
      // Ignore corrupt browser session cache.
    }
  }

  async loadOptions() {
    try {
      const options = (await apiGet(
        `/api/v1/vault/${this.vaultName}/ask/options`,
      )) as {
        model?: string;
        resolved_model?: string;
        model_options?: string[];
      };
      const choices = Array.isArray(options.model_options)
        ? options.model_options.filter((choice) => typeof choice === "string")
        : [];
      this.modelOptions = choices.length ? choices : ["auto"];
      this.selectedModel = this.modelOptions.includes(options.model || "")
        ? options.model || "auto"
        : "auto";
      this.modelLabel = modelLabelFromOptions(options);
    } catch {
      this.selectedModel = "auto";
      this.modelOptions = ["auto"];
      this.modelLabel = "auto";
    }
  }

  setModel(model: string) {
    this.selectedModel = this.modelOptions.includes(model) ? model : "auto";
    this.modelLabel =
      this.selectedModel === "auto" ? "auto" : this.selectedModel;
  }

  claimQueryParam(query: string) {
    if (!query || query === this.submittedQueryParam) return false;
    this.submittedQueryParam = query;
    return true;
  }

  clearQueryParam() {
    this.submittedQueryParam = "";
  }

  async submit(question: string) {
    if (this.busy) return this.#activeRun;
    if (question.trim() === "/new") {
      this.clear();
      return null;
    }
    this.busy = true;

    const context = this.#buildContext();
    const runId = createAskRunId();
    const turn: AskTurn = {
      question,
      items: [],
      answer: "",
      done: false,
      runId,
    };
    this.turns = [...this.turns, turn];
    this.#persist();

    this.#activeRun = this.#run(question, context, runId);
    return this.#activeRun;
  }

  clear() {
    this.#sessionId = createAskSessionId();
    this.turns = [];
    this.managedTasks = [];
    this.submittedQueryParam = "";
    this.#persist();
  }

  async #run(question: string, context: string, runId: string) {
    try {
      await streamSse(
        `/api/v1/vault/${this.vaultName}/ask`,
        {
          query: question,
          context,
          ask_session_id: this.#sessionId,
          ask_run_id: runId,
          model: this.selectedModel,
        },
        (eventName, data) => {
          if (eventName === "result") {
            const payload = (data ?? {}) as Record<string, unknown>;
            const answer = (payload.answer ??
              payload.response ??
              payload.content ??
              "") as string;
            // Prefer the canonical final answer if no streaming content arrived.
            this.#updateTurn(runId, (turn) => ({
              ...turn,
              answer: answer && !turn.answer ? answer : turn.answer,
              done: true,
            }));
          } else if (eventName === "error") {
            const payload = (data ?? {}) as Record<string, unknown>;
            const msg = (payload.message ??
              payload.reason ??
              payload.content ??
              "error") as string;
            this.#updateTurn(runId, (turn) => ({
              ...turn,
              items: [...turn.items, { kind: "error", message: msg }],
              done: true,
            }));
          } else if (eventName === "run") {
            // Run metadata is used for recovery, not rendered as transcript text.
          } else {
            this.#appendChunk(
              (data ?? {}) as Record<string, unknown>,
              eventName,
              runId,
            );
          }
        },
      );
      if (!this.#isTurnDone(runId)) {
        await this.#recoverRun(runId);
      }
    } catch (e) {
      const recovered = await this.#recoverRun(runId);
      if (!recovered) {
        const msg = e instanceof Error ? e.message : String(e);
        this.#updateTurn(runId, (turn) => ({
          ...turn,
          items: [...turn.items, { kind: "error", message: msg }],
        }));
      }
    } finally {
      if (!this.#isTurnDone(runId)) {
        this.#updateTurn(runId, (turn) => ({ ...turn, done: true }));
      }
      this.busy = false;
      this.#activeRun = null;
      this.#persist();
    }
  }

  async #recoverPendingRun(runId: string) {
    try {
      await this.#recoverRun(runId);
    } finally {
      this.busy = false;
      this.#activeRun = null;
      this.#persist();
    }
  }

  async #recoverRun(runId: string) {
    for (let attempt = 0; attempt < ASK_RUN_RECOVERY_ATTEMPTS; attempt += 1) {
      try {
        const snapshot = (await apiGet(
          `/api/v1/vault/${this.vaultName}/ask/runs/${encodeURIComponent(runId)}`,
        )) as AskRunSnapshot;
        this.#applyRunSnapshot(runId, snapshot);
        if (snapshot.status === "done" || snapshot.status === "error") {
          return true;
        }
      } catch {
        if (attempt >= 2) return false;
      }
      await sleep(ASK_RUN_RECOVERY_DELAY_MS);
    }
    return false;
  }

  #applyRunSnapshot(runId: string, snapshot: AskRunSnapshot) {
    const chunks = Array.isArray(snapshot.chunks) ? snapshot.chunks : [];
    this.#updateTurn(runId, (turn) => ({
      ...turn,
      items: [],
      answer: "",
      done: false,
    }));
    for (const chunk of chunks.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0))) {
      this.#appendChunk(
        (chunk.data ?? {}) as Record<string, unknown>,
        chunk.event || "stream",
        runId,
      );
    }
    if (snapshot.status === "done") {
      const payload = snapshot.result ?? {};
      const answer = (payload.answer ??
        payload.response ??
        payload.content ??
        "") as string;
      this.#updateTurn(runId, (turn) => ({
        ...turn,
        answer: answer && !turn.answer ? answer : turn.answer,
        done: true,
      }));
    } else if (snapshot.status === "error") {
      const payload = snapshot.error ?? {};
      const msg = (payload.message ?? payload.reason ?? "error") as string;
      this.#updateTurn(runId, (turn) => ({
        ...turn,
        items: [...turn.items, { kind: "error", message: msg }],
        done: true,
      }));
    }
  }

  #appendChunk(
    chunk: Record<string, unknown>,
    eventName: string,
    runId?: string,
  ) {
    const type = (chunk.type as string) || eventName;

    if (type === "content") {
      const text = (chunk.text ?? chunk.content ?? "") as string;
      this.#updateTurn(runId, (turn) => ({
        ...turn,
        answer: `${turn.answer}${text}`,
      }));
    } else if (
      type === "tool_call_start" ||
      type === "tool_call" ||
      type === "tool_detail"
    ) {
      const tool = (chunk.name ?? chunk.tool ?? "tool") as string;
      const argsRaw = chunk.arguments ?? chunk.args ?? "";
      if (tool === "manage_tasks") {
        const tasks = extractManagedTasks(argsRaw);
        if (tasks.length) {
          this.managedTasks = tasks;
          this.#persist();
        }
        return;
      }
      const args =
        typeof argsRaw === "string" ? argsRaw : JSON.stringify(argsRaw);
      this.#updateTurn(runId, (turn) => ({
        ...turn,
        items: [...turn.items, { kind: "tool_call", tool, args }],
      }));
    } else if (type === "reasoning") {
      const text = (chunk.text ?? chunk.content ?? "") as string;
      this.#updateTurn(runId, (turn) => ({
        ...turn,
        items: [...turn.items, { kind: "reasoning", text }],
      }));
    } else if (type === "task" || type === "tasks" || type === "todo") {
      const text = (chunk.text ??
        chunk.content ??
        chunk.message ??
        "") as string;
      this.#updateTurn(runId, (turn) => ({
        ...turn,
        items: [...turn.items, { kind: "task", text }],
      }));
    } else if (type === "error") {
      const msg = (chunk.message ?? chunk.reason ?? "error") as string;
      this.#updateTurn(runId, (turn) => ({
        ...turn,
        items: [...turn.items, { kind: "error", message: msg }],
      }));
    }
    // tool_call_end and other types are silently consumed.
  }

  #updateTurn(runId: string | undefined, updater: (turn: AskTurn) => AskTurn) {
    const targetIndex = runId
      ? this.turns.findIndex((turn) => turn.runId === runId)
      : this.turns.length - 1;
    if (targetIndex < 0) return;
    this.turns = this.turns.map((turn, index) =>
      index === targetIndex ? updater(turn) : turn,
    );
    this.#persist();
  }

  #isTurnDone(runId: string) {
    return Boolean(this.turns.find((turn) => turn.runId === runId)?.done);
  }

  #persist() {
    if (!this.hydrated || typeof localStorage === "undefined") return;
    try {
      if (!this.turns.length && !this.managedTasks.length) {
        localStorage.removeItem(this.#storageKey());
        return;
      }
      const snapshot: AskSessionSnapshot = {
        version: ASK_SESSION_VERSION,
        savedAt: Date.now(),
        sessionId: this.#sessionId,
        turns: this.turns.slice(-ASK_SESSION_MAX_TURNS),
        managedTasks: this.managedTasks,
      };
      localStorage.setItem(this.#storageKey(), JSON.stringify(snapshot));
    } catch {
      // Storage can be unavailable or full on mobile browsers.
    }
  }

  #storageKey() {
    return `pkm.askSession.${this.vaultName}`;
  }

  #buildContext() {
    const history = this.turns;
    if (!history.length) return "";
    return [
      "Web ask conversation history from this browser session.",
      "Use this as prior dialogue when answering the current query.",
      ...history.map((turn, index) => {
        const parts = [
          `Turn ${index + 1}`,
          `User: ${turn.question}`,
          ...turn.items.map(formatItem),
          `Assistant: ${turn.answer || "(no assistant answer recorded)"}`,
        ];
        return parts.join("\n");
      }),
    ].join("\n\n");
  }
}

function modelLabelFromOptions(options: {
  model?: string;
  resolved_model?: string;
}) {
  const selected = options.model || "auto";
  const resolved = options.resolved_model || "";
  if (selected === "auto") return resolved ? `${resolved} (auto)` : "auto";
  return resolved || selected;
}

function createAskSessionId() {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `web-${random}`;
}

function createAskRunId() {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `web-run-${random}`;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatItem(item: AskItem) {
  if (item.kind === "tool_call")
    return `Tool ${item.tool}: ${item.args || "(no arguments)"}`;
  if (item.kind === "reasoning") return `Thinking: ${item.text}`;
  if (item.kind === "task") return `Task: ${item.text}`;
  if (item.kind === "content") return `Assistant content: ${item.text}`;
  return `Error: ${item.message}`;
}

function validTurn(value: unknown): value is AskTurn {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.question === "string" &&
    Array.isArray(record.items) &&
    typeof record.answer === "string"
  );
}

function parseJsonDeep(value: unknown) {
  let parsed = value;
  for (let depth = 0; depth < 4; depth += 1) {
    if (typeof parsed !== "string") return parsed;
    const trimmed = parsed.trim();
    if (!trimmed || !["{", "["].includes(trimmed[0])) return parsed;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return parsed;
    }
  }
  return parsed;
}

function taskText(task: unknown, index: number) {
  if (typeof task === "string") return task;
  if (!task || typeof task !== "object") return `Task ${index + 1}`;
  const record = task as Record<string, unknown>;
  return String(
    record.text ??
      record.content ??
      record.title ??
      record.task ??
      record.description ??
      `Task ${index + 1}`,
  );
}

function taskStatus(task: unknown): ManagedTaskStatus {
  if (!task || typeof task !== "object") return "pending";
  const record = task as Record<string, unknown>;
  const raw = String(record.status ?? record.state ?? "")
    .toLowerCase()
    .replace(/[-\s]/g, "_");
  if (["done", "completed", "complete", "success", "checked"].includes(raw))
    return "done";
  if (
    ["in_progress", "progress", "running", "active", "doing", "wip"].includes(
      raw,
    )
  ) {
    return "in_progress";
  }
  if (["cancelled", "canceled", "cancel", "skipped"].includes(raw))
    return "cancelled";
  return "pending";
}

function taskChecked(task: unknown, status: ManagedTaskStatus) {
  if (task && typeof task === "object") {
    const record = task as Record<string, unknown>;
    if (typeof record.checked === "boolean") return record.checked;
    if (typeof record.completed === "boolean") return record.completed;
    if (typeof record.done === "boolean") return record.done;
  }
  return status === "done";
}

function taskSource(raw: unknown) {
  let source = parseJsonDeep(raw);
  for (let depth = 0; depth < 4; depth += 1) {
    source = parseJsonDeep(source);
    if (!source || typeof source !== "object" || Array.isArray(source))
      return source;
    const record = source as Record<string, unknown>;
    const nested =
      record.tasks ??
      record.items ??
      record.todos ??
      record.task_list ??
      record.taskList;
    if (nested === undefined) return source;
    source = nested;
  }
  return source;
}

function extractManagedTasks(raw: unknown) {
  const source = taskSource(raw);
  const list = Array.isArray(source) ? source : source ? [source] : [];
  return list
    .map((task, index) => {
      const status = taskStatus(task) || "pending";
      return {
        id:
          task && typeof task === "object" && "id" in task
            ? String((task as Record<string, unknown>).id)
            : `${index}-${taskText(task, index)}`,
        text: taskText(task, index),
        checked: taskChecked(task, status),
        status,
      };
    })
    .filter((task) => task.text.trim().length > 0);
}
