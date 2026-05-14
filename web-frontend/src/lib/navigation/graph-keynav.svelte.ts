export interface SemanticNeighbor {
  note_id: string;
  title?: string;
  type?: string;
  description?: string;
  confidence?: number | string | null;
}

export interface NavigationContext {
  vaultName: string;
  noteId: string;
  semantic: SemanticNeighbor[];
}

export interface NavigationTarget {
  vaultName: string;
  noteId: string;
}

export interface SemanticRankAction {
  key: string;
  description: string;
  rank: number;
  target: NavigationTarget;
}

const STACK_STORAGE_PREFIX = "pkm.graphKeyNavStack.";
const MAX_STACK_DEPTH = 100;
const MAX_RANK_ACTIONS = 9;

export function noteHref(target: NavigationTarget) {
  return `/${encodeURIComponent(target.vaultName)}/notes/${encodeURIComponent(target.noteId)}`;
}

export class GraphKeyNavigationState {
  current = $state<NavigationContext | null>(null);
  #stacks = $state<Record<string, NavigationTarget[]>>({});
  #hydratedVaults = new Set<string>();

  get rankedSemanticNeighbors() {
    return [...(this.current?.semantic ?? [])].sort(compareSemanticNeighbors);
  }

  get semanticRankActions() {
    const vaultName = this.current?.vaultName ?? "";
    return this.rankedSemanticNeighbors
      .slice(0, MAX_RANK_ACTIONS)
      .map((neighbor, index) => ({
        key: String(index + 1),
        description: semanticActionLabel(neighbor),
        rank: index + 1,
        target: { vaultName, noteId: neighbor.note_id },
      }));
  }

  get hasSemanticNeighbors() {
    return this.rankedSemanticNeighbors.length > 0;
  }

  get canGoBack() {
    const vaultName = this.current?.vaultName;
    return Boolean(vaultName && this.stackForVault(vaultName).length > 0);
  }

  setCurrentNoteNavigationContext(
    vaultName: string,
    noteId: string,
    semantic: SemanticNeighbor[] = [],
  ) {
    this.current = {
      vaultName,
      noteId,
      semantic: semantic.filter(isValidSemanticNeighbor),
    };
    this.stackForVault(vaultName);
  }

  clearCurrentNoteNavigationContext(vaultName?: string, noteId?: string) {
    if (!this.current) return;
    if (vaultName && this.current.vaultName !== vaultName) return;
    if (noteId && this.current.noteId !== noteId) return;
    this.current = null;
  }

  pushCurrent() {
    if (!this.current) return false;
    this.#push(this.current.vaultName, {
      vaultName: this.current.vaultName,
      noteId: this.current.noteId,
    });
    return true;
  }

  navigateToSemanticRank(rank: number) {
    const action = this.semanticRankActions[rank - 1];
    if (!action) return null;
    return this.#targetAfterPush(action.target);
  }

  navigateNextSemantic() {
    const target = this.#relativeSemanticTarget(1);
    if (!target) return null;
    return this.#targetAfterPush(target);
  }

  navigatePreviousSemantic() {
    const target = this.#relativeSemanticTarget(-1);
    if (!target) return null;
    return this.#targetAfterPush(target);
  }

  popNavigationStack(vaultName = this.current?.vaultName ?? "") {
    if (!vaultName) return null;
    const stack = this.stackForVault(vaultName);
    const target = stack.at(-1);
    if (!target) return null;
    this.#stacks[vaultName] = stack.slice(0, -1);
    this.#persist(vaultName);
    return target;
  }

  stackForVault(vaultName: string) {
    if (!vaultName) return [];
    this.#hydrate(vaultName);
    return this.#stacks[vaultName] ?? [];
  }

  resetForTests() {
    this.current = null;
    this.#stacks = {};
    this.#hydratedVaults.clear();
  }

  #targetAfterPush(target: NavigationTarget) {
    if (!this.current) return null;
    if (
      target.vaultName === this.current.vaultName &&
      target.noteId === this.current.noteId
    ) {
      return null;
    }
    this.pushCurrent();
    return target;
  }

  #relativeSemanticTarget(direction: 1 | -1) {
    if (!this.current) return null;
    const ranked = this.rankedSemanticNeighbors;
    if (ranked.length === 0) return null;
    const currentIndex = ranked.findIndex(
      (neighbor) => neighbor.note_id === this.current?.noteId,
    );
    const nextIndex =
      currentIndex === -1
        ? direction === 1
          ? 0
          : ranked.length - 1
        : (currentIndex + direction + ranked.length) % ranked.length;
    return {
      vaultName: this.current.vaultName,
      noteId: ranked[nextIndex].note_id,
    };
  }

  #push(vaultName: string, target: NavigationTarget) {
    const stack = this.stackForVault(vaultName);
    const last = stack.at(-1);
    if (last?.vaultName === target.vaultName && last.noteId === target.noteId) {
      return;
    }
    this.#stacks[vaultName] = [...stack, target].slice(-MAX_STACK_DEPTH);
    this.#persist(vaultName);
  }

  #hydrate(vaultName: string) {
    if (this.#hydratedVaults.has(vaultName)) return;
    this.#hydratedVaults.add(vaultName);
    if (typeof sessionStorage === "undefined") return;
    try {
      const raw = sessionStorage.getItem(this.#storageKey(vaultName));
      const parsed = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed)) return;
      this.#stacks[vaultName] = parsed
        .filter(isValidTarget)
        .slice(-MAX_STACK_DEPTH);
    } catch {
      this.#stacks[vaultName] = [];
    }
  }

  #persist(vaultName: string) {
    if (typeof sessionStorage === "undefined") return;
    try {
      sessionStorage.setItem(
        this.#storageKey(vaultName),
        JSON.stringify(this.#stacks[vaultName] ?? []),
      );
    } catch {
      // Ignore restricted or full browser storage.
    }
  }

  #storageKey(vaultName: string) {
    return `${STACK_STORAGE_PREFIX}${vaultName}`;
  }
}

export const graphKeyNav = new GraphKeyNavigationState();

function compareSemanticNeighbors(a: SemanticNeighbor, b: SemanticNeighbor) {
  const confidenceDelta =
    numericConfidence(b.confidence) - numericConfidence(a.confidence);
  if (confidenceDelta !== 0) return confidenceDelta;
  const titleDelta = compareText(semanticTitle(a), semanticTitle(b));
  if (titleDelta !== 0) return titleDelta;
  return compareText(a.note_id, b.note_id);
}

function semanticActionLabel(neighbor: SemanticNeighbor) {
  const title = semanticTitle(neighbor);
  const confidence = numericConfidence(neighbor.confidence);
  return `${title} ${confidence.toFixed(2)}`;
}

function semanticTitle(neighbor: SemanticNeighbor) {
  return neighbor.title || neighbor.note_id;
}

function compareText(a: string, b: string) {
  return a.toLocaleLowerCase().localeCompare(b.toLocaleLowerCase());
}

function numericConfidence(value: SemanticNeighbor["confidence"]) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : 0;
}

function isValidSemanticNeighbor(value: SemanticNeighbor) {
  return Boolean(value?.note_id && typeof value.note_id === "string");
}

function isValidTarget(value: unknown): value is NavigationTarget {
  if (!value || typeof value !== "object") return false;
  const target = value as Partial<NavigationTarget>;
  return (
    typeof target.vaultName === "string" && typeof target.noteId === "string"
  );
}
