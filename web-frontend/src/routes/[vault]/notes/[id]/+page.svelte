<script lang="ts">
  import { onDestroy, onMount, tick, untrack } from "svelte";
  import { page } from "$app/stores";
  import { apiClient, apiGet } from "$lib/api/client.js";
  import MarkdownRenderer from "$lib/components/MarkdownRenderer.svelte";
  import NeighborPanel from "$lib/components/NeighborPanel.svelte";
  import ScrollPositionOverlay from "$lib/components/ScrollPositionOverlay.svelte";
  import CodeMirror from "$lib/editor/CodeMirror.svelte";
  import { tagHue } from "$lib/notes/rendered-markdown.js";
  import {
    reconcileTextQuoteAnchor,
    renderedSourceRevision,
    type TextAnchorStatus,
    type TextAnchorTarget,
    type TextQuoteAnchor,
  } from "$lib/annotations/text-anchor";
  import { graphKeyNav } from "$lib/navigation/graph-keynav.svelte";
  import {
    clampFloatingPosition,
    floatingSizeForViewport,
    floatingTopLeftFromAnchor,
    viewportSize,
  } from "$lib/ui/floating-position";
  import { rememberVault } from "$lib/vault/remembered-vault";

  interface Note {
    note_id: string;
    title: string;
    body: string;
    content_hash: string;
    frontmatter: Record<string, unknown>;
    created: string | null;
    updated: string | null;
    tags: string[];
    importance: number | null;
  }

  interface NeighborData {
    note_id: string;
    outbound: {
      note_id: string;
      title: string;
      type: string;
      description?: string;
    }[];
    inbound: {
      note_id: string;
      title: string;
      type: string;
      description?: string;
    }[];
    semantic: {
      note_id: string;
      title: string;
      type: string;
      description?: string;
      confidence?: number;
    }[];
  }

  let note = $state<Note | null>(null);
  let neighbors = $state<NeighborData | null>(null);
  let loadingNote = $state(true);
  let loadingNeighbors = $state(true);
  let error = $state("");
  let editMode = $state(false);
  let editorDoc = $state("");
  let savedDoc = $state("");
  let editorMode = $state<"vim" | "plain">("vim");
  let saving = $state(false);
  let saveError = $state("");
  let saveStatus = $state("");
  let notePageElement = $state<HTMLElement | null>(null);
  let noteScrollElement = $state<HTMLElement | null>(null);

  let vaultName = $derived($page.params.vault);
  let noteId = $derived($page.params.id);
  let editorDirty = $derived(editorDoc !== savedDoc);
  let noteAnnotationsPanelOpen = $state(false);
  let noteAnnotations = $state<SourceAnnotation[]>([]);
  let noteAnnotationSourceRevision = $state("");
  let noteAnnotationRevision = $state(0);
  let noteAnnotationStorageMode = $state<"none" | "legacy" | "v2">("none");
  let noteAnnotationLegacyRevision = $state("");
  let loadToken = 0;
  const dailyNoteIdPattern = /^\d{4}-\d{2}-\d{2}$/;
  const taskStateOrder = ["[ ]", "[>]", "[x]", "[~]"] as const;
  type TaskState = (typeof taskStateOrder)[number];
  const taskStatePattern = /\[(?: |>|x|~)\]/g;

  function isTagNoteId(id: string) {
    return id.startsWith("tag:");
  }

  function tagNameFromNoteId(id: string) {
    return isTagNoteId(id) ? id.slice(4) : "";
  }

  function tagHref(vault: string, tag: string) {
    return `/${encodeURIComponent(vault)}/notes/${encodeURIComponent(`tag:${tag}`)}`;
  }

  function closestScrollContainer(element: HTMLElement | null) {
    if (!element) return null;
    const vaultContent = element.closest<HTMLElement>(".vault-content");
    if (vaultContent) return vaultContent;

    let current = element.parentElement;
    while (current) {
      const overflowY = window.getComputedStyle(current).overflowY;
      if (
        (overflowY === "auto" || overflowY === "scroll") &&
        current.scrollHeight > current.clientHeight
      ) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }

  function taskStateKind(state: string) {
    if (state === "[>]") return "wip";
    if (state === "[x]") return "done";
    if (state === "[~]") return "cancel";
    return "todo";
  }

  function taskStateLabel(state: string) {
    if (state === "[>]") return ">";
    if (state === "[x]") return "✓";
    if (state === "[~]") return "~";
    return "";
  }

  function taskStateAriaLabel(state: string) {
    if (state === "[>]") return "Task status in progress";
    if (state === "[x]") return "Task status done";
    if (state === "[~]") return "Task status canceled";
    return "Task status todo";
  }

  function renderTaskStateButton(state: string, index: number) {
    const kind = taskStateKind(state);
    const label = taskStateLabel(state);
    const ariaLabel = taskStateAriaLabel(state);
    return `<button type="button" class="note-task-state note-task-state-${kind}" data-task-index="${index}" data-task-state="${state}" aria-label="${ariaLabel}">${label}</button>`;
  }

  function forMarkdownTextSegments(
    markdown: string,
    mapText: (segment: string) => string,
  ) {
    let inFence = false;
    let fenceMarker = "";

    return markdown
      .split("\n")
      .map((line) => {
        const trimmed = line.trimStart();
        const fence = trimmed.match(/^(```+|~~~+)/)?.[1];
        if (fence && (!inFence || fence.startsWith(fenceMarker[0]))) {
          inFence = !inFence;
          fenceMarker = inFence ? fence : "";
          return line;
        }
        if (inFence) return line;

        return line
          .split(/(`[^`]*`)/g)
          .map((segment) => {
            if (segment.startsWith("`") && segment.endsWith("`"))
              return segment;
            return mapText(segment);
          })
          .join("");
      })
      .join("\n");
  }

  function withTaskStateButtons(markdown: string) {
    let taskIndex = 0;

    return forMarkdownTextSegments(markdown, (segment) =>
      segment.replace(taskStatePattern, (state) =>
        renderTaskStateButton(state, taskIndex++),
      ),
    );
  }

  function nextTaskState(state: string): TaskState {
    const index = taskStateOrder.indexOf(state as TaskState);
    return taskStateOrder[(index + 1) % taskStateOrder.length];
  }

  function replaceTaskStateByIndex(
    markdown: string,
    targetIndex: number,
    nextState: TaskState,
  ) {
    let taskIndex = 0;
    let didReplace = false;

    const updated = forMarkdownTextSegments(markdown, (segment) =>
      segment.replace(taskStatePattern, (state) => {
        if (taskIndex === targetIndex) {
          didReplace = true;
          taskIndex += 1;
          return nextState;
        }
        taskIndex += 1;
        return state;
      }),
    );

    return didReplace ? updated : markdown;
  }

  async function saveTaskState(taskIndex: number, currentState: string) {
    if (!note) return;
    const updatedBody = replaceTaskStateByIndex(
      note.body ?? "",
      taskIndex,
      nextTaskState(currentState),
    );
    if (updatedBody === note.body) return;

    const response = await apiClient(
      `/api/v1/vault/${vaultName}/notes/${note.note_id}`,
      {
        method: "PUT",
        headers: note.content_hash
          ? { "If-Match": `"${note.content_hash}"` }
          : undefined,
        body: JSON.stringify({ body: updatedBody }),
      },
    );

    if (!response.ok) {
      throw new Error(`PUT note task state → ${response.status}`);
    }

    const updatedNote = (await response.json()) as Note;
    const body = updatedNote.body ?? updatedBody;
    note = { ...updatedNote, body };
    editorDoc = body;
    savedDoc = body;
  }

  function parseAnnotationSourceHash(hash: string) {
    const raw = hash.startsWith("#") ? hash.slice(1) : hash;
    const params = new URLSearchParams(raw);
    const quote = normalizeAnnotationQuote(params.get("quote") ?? "");
    const occurrence = Number(params.get("occ") ?? "0");
    if (!quote) return null;
    return {
      quote,
      occurrence: Number.isFinite(occurrence) ? Math.max(0, occurrence) : 0,
    };
  }

  function annotationHeading(container: HTMLElement) {
    return Array.from(
      container.querySelectorAll<HTMLElement>("h1,h2,h3,h4,h5,h6"),
    ).find(
      (heading) =>
        normalizeAnnotationQuote(heading.textContent ?? "") === "Annotations",
    );
  }

  function isInAnnotationSection(
    element: HTMLElement,
    heading: HTMLElement | undefined,
  ) {
    if (!heading) return false;
    return (
      element === heading ||
      Boolean(
        heading.compareDocumentPosition(element) &
        Node.DOCUMENT_POSITION_FOLLOWING,
      )
    );
  }

  interface SourceSearchTarget extends TextAnchorTarget {
    element: HTMLElement;
    text: string;
    headingPath: string[];
  }

  interface ParsedAnnotation {
    id: string;
    quote: string;
    sourceHref: string;
    memo: string;
    entryStartLine: number;
    entryEndLine: number;
  }

  interface ReanchorMetadata {
    confidence: number;
    reason: "exact" | "context" | "ambiguous" | "missing";
  }

  interface SourceAnnotation {
    id: string;
    quote: string;
    sourceHref: string;
    memo: string;
    entryStartLine: number;
    entryEndLine: number;
    anchor: TextQuoteAnchor;
    status: TextAnchorStatus;
    reanchor?: ReanchorMetadata;
    raw?: NoteAnnotationV2;
  }

  interface NoteAnnotationV2 {
    [key: string]: unknown;
    id: string;
    kind: "note";
    anchor: TextQuoteAnchor;
    status?: TextAnchorStatus;
    reanchor?: ReanchorMetadata;
    comment: string;
    created_at: string;
    updated_at: string;
  }

  interface NoteAnnotationDocumentV2 {
    version: 2;
    source_key: string;
    source: { kind: "note"; note_id: string };
    annotation_revision?: number;
    storage_mode?: "none" | "legacy" | "v2";
    legacy_revision?: string;
    source_revision?: string;
    annotations: NoteAnnotationV2[];
  }

  interface AnnotationPopup {
    x: number;
    y: number;
    annotations: SourceAnnotation[];
  }

  interface FloatingDragState {
    offsetX: number;
    offsetY: number;
  }

  function textExcludingNestedCandidates(
    element: HTMLElement,
    candidateSet: Set<HTMLElement>,
  ) {
    let text = "";
    const visit = (node: Node) => {
      node.childNodes.forEach((child) => {
        if (child instanceof HTMLElement && candidateSet.has(child)) return;
        if (child.nodeType === Node.TEXT_NODE) {
          text += child.textContent ?? "";
          return;
        }
        visit(child);
      });
    };
    visit(element);
    return text;
  }

  function sourceSearchTargets(container: HTMLElement): SourceSearchTarget[] {
    const heading = annotationHeading(container);
    const candidates = Array.from(
      container.querySelectorAll<HTMLElement>(
        "p,li,blockquote,h1,h2,h3,h4,h5,h6,td,th,pre",
      ),
    ).filter((element) => !isInAnnotationSection(element, heading));
    const candidateSet = new Set(candidates);
    const headingStack: Array<{ level: number; text: string }> = [];
    return candidates
      .map((element) => {
        const hasNestedCandidate = candidates.some(
          (other) => other !== element && element.contains(other),
        );
        const text = normalizeAnnotationQuote(
          hasNestedCandidate
            ? textExcludingNestedCandidates(element, candidateSet)
            : (element.textContent ?? ""),
        );
        const headingLevel = /^H([1-6])$/.exec(element.tagName)?.[1];
        if (headingLevel) {
          const level = Number(headingLevel);
          while (
            headingStack.length > 0 &&
            headingStack[headingStack.length - 1].level >= level
          ) {
            headingStack.pop();
          }
          headingStack.push({ level, text });
        }
        return {
          element,
          text,
          headingPath: headingStack.map((item) => item.text),
        };
      })
      .filter((target) => target.text.length > 0);
  }

  function annotationMemoLine(line: string) {
    const listItem = line.match(/^\s+-\s?(?<text>.*)$/)?.groups?.text;
    if (listItem !== undefined) return listItem.trimEnd();
    const continuation = line.match(/^\s{4,}(?<text>.*)$/)?.groups?.text;
    return continuation?.trimEnd() ?? "";
  }

  function parseAnnotationsFromBody(body: string): ParsedAnnotation[] {
    const lines = (body ?? "").split(/\r?\n/);
    const headingIndex = lines.findIndex(
      (line) => normalizeAnnotationQuote(line) === "## Annotations",
    );
    if (headingIndex < 0) return [];

    const annotations: ParsedAnnotation[] = [];
    let current: {
      quote: string;
      sourceHref: string;
      memoLines: string[];
      index: number;
    } | null = null;

    const flush = (endLine: number) => {
      if (!current) return;
      const memo = current.memoLines.join("\n").trim();
      if (memo) {
        annotations.push({
          id: `${current.sourceHref}\u0000${current.index}`,
          quote: current.quote,
          sourceHref: current.sourceHref,
          memo,
          entryStartLine: current.index,
          entryEndLine: endLine,
        });
      }
      current = null;
    };

    for (let index = headingIndex + 1; index < lines.length; index += 1) {
      const line = lines[index];
      if (/^#{1,6}\s+/.test(line)) {
        flush(index);
        break;
      }
      const entry = line.match(
        /^-\s+[“"]?(?<quote>.*?)[”"]?\s*\(\[↩ 원문\]\((?<href>#[^)]+)\)\)\s*$/,
      );
      if (entry?.groups?.href) {
        flush(index);
        const parsed = parseAnnotationSourceHash(entry.groups.href);
        if (!parsed) {
          current = null;
          continue;
        }
        current = {
          quote:
            parsed.quote || normalizeAnnotationQuote(entry.groups.quote ?? ""),
          sourceHref: entry.groups.href,
          memoLines: [],
          index,
        };
        continue;
      }
      if (!current) continue;
      if (/^-\s+/.test(line)) {
        flush(index);
        continue;
      }
      if (line.trim().length === 0) {
        current.memoLines.push("");
        continue;
      }
      current.memoLines.push(annotationMemoLine(line));
    }
    flush(lines.length);
    return annotations;
  }

  interface AnnotationSourceMatch {
    element: HTMLElement;
    quote: string;
    sourceHref: string;
    occurrenceInElement: number;
  }

  function annotationSourceMatch(
    hash: string,
    targets = noteBodyElement ? sourceSearchTargets(noteBodyElement) : [],
  ): AnnotationSourceMatch | null {
    const parsed = parseAnnotationSourceHash(hash);
    if (!parsed) return null;
    let seen = 0;
    for (const candidate of targets) {
      const count = countQuoteOccurrences(candidate.text, parsed.quote);
      if (count === 0) continue;
      if (seen + count > parsed.occurrence) {
        return {
          element: candidate.element,
          quote: parsed.quote,
          sourceHref: hash,
          occurrenceInElement: parsed.occurrence - seen,
        };
      }
      seen += count;
    }
    return null;
  }

  function annotationSourceTarget(
    hash: string,
    targets = noteBodyElement ? sourceSearchTargets(noteBodyElement) : [],
  ) {
    return annotationSourceMatch(hash, targets)?.element ?? null;
  }

  function textNodesInside(element: HTMLElement) {
    const nodes: Text[] = [];
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        if (parent.closest('[data-annotation-source-marked="true"]')) {
          return NodeFilter.FILTER_REJECT;
        }
        if (!node.textContent) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let node = walker.nextNode();
    while (node) {
      if (node instanceof Text) nodes.push(node);
      node = walker.nextNode();
    }
    return nodes;
  }

  function nthIndexOf(value: string, needle: string, occurrence: number) {
    let index = 0;
    for (let seen = 0; seen <= occurrence; seen += 1) {
      const found = value.indexOf(needle, index);
      if (found < 0) return -1;
      if (seen === occurrence) return found;
      index = found + needle.length;
    }
    return -1;
  }

  interface TextSegment {
    node: Text;
    start: number;
    end: number;
  }

  function appendTextSegment(segments: TextSegment[], segment: TextSegment) {
    const previous = segments.at(-1);
    if (previous?.node === segment.node && previous.end === segment.start) {
      previous.end = segment.end;
      return;
    }
    segments.push({ ...segment });
  }

  function normalizedTextMapping(textNodes: Text[]) {
    const mappings: TextSegment[][] = [];
    let normalizedText = "";
    let pendingWhitespace: TextSegment[] = [];

    const flushWhitespace = () => {
      if (pendingWhitespace.length === 0) return;
      normalizedText += " ";
      mappings.push(pendingWhitespace);
      pendingWhitespace = [];
    };

    for (const node of textNodes) {
      for (let index = 0; index < node.data.length; index += 1) {
        const char = node.data[index];
        if (/\s/.test(char)) {
          appendTextSegment(pendingWhitespace, {
            node,
            start: index,
            end: index + 1,
          });
          continue;
        }
        flushWhitespace();
        normalizedText += char;
        mappings.push([{ node, start: index, end: index + 1 }]);
      }
    }
    flushWhitespace();

    let start = 0;
    let end = normalizedText.length;
    while (start < end && normalizedText[start] === " ") start += 1;
    while (end > start && normalizedText[end - 1] === " ") end -= 1;
    return {
      text: normalizedText.slice(start, end),
      mappings: mappings.slice(start, end),
    };
  }

  function annotationTextSegments(
    element: HTMLElement,
    quote: string,
    occurrenceInElement: number,
  ): TextSegment[] {
    const textNodes = textNodesInside(element);
    const { text, mappings } = normalizedTextMapping(textNodes);
    const normalizedQuote = normalizeAnnotationQuote(quote);
    const start = nthIndexOf(text, normalizedQuote, occurrenceInElement);
    if (start < 0) return [];
    const end = start + normalizedQuote.length;
    const segments: TextSegment[] = [];
    for (const mappedSegments of mappings.slice(start, end)) {
      mappedSegments.forEach((segment) => appendTextSegment(segments, segment));
    }
    return segments;
  }

  interface AnnotationSegmentPlan {
    node: Text;
    start: number;
    end: number;
    annotations: SourceAnnotation[];
    sourceHref: string;
  }

  function createAnnotationSpan(
    text: string,
    annotations: SourceAnnotation[],
    sourceHref: string,
  ) {
    const span = document.createElement("span");
    span.className = "annotation-source-marked";
    span.dataset.annotationSourceMarked = "true";
    span.dataset.annotationSourceHref = sourceHref;
    span.tabIndex = 0;
    span.setAttribute("role", "button");
    span.setAttribute("aria-haspopup", "dialog");
    span.setAttribute(
      "aria-label",
      annotations.length === 1
        ? "View annotation memo"
        : `View ${annotations.length} annotation memos`,
    );
    span.textContent = text;
    annotationSourcesByElement.set(span, annotations);
    return span;
  }

  function wrapAnnotationSegmentPlans(plans: AnnotationSegmentPlan[]) {
    const byNode = new Map<Text, AnnotationSegmentPlan[]>();
    for (const plan of plans) {
      const group = byNode.get(plan.node) ?? [];
      group.push(plan);
      byNode.set(plan.node, group);
    }

    let wrapped = 0;
    byNode.forEach((nodePlans, node) => {
      const parent = node.parentNode;
      if (!parent) return;
      const text = node.data;
      const sorted = [...nodePlans].sort((a, b) => a.start - b.start);
      const fragment = document.createDocumentFragment();
      let cursor = 0;
      for (const plan of sorted) {
        if (plan.start < cursor || plan.end <= plan.start) continue;
        if (cursor < plan.start) {
          fragment.appendChild(
            document.createTextNode(text.slice(cursor, plan.start)),
          );
        }
        fragment.appendChild(
          createAnnotationSpan(
            text.slice(plan.start, plan.end),
            plan.annotations,
            plan.sourceHref,
          ),
        );
        cursor = plan.end;
        wrapped += 1;
      }
      if (cursor < text.length) {
        fragment.appendChild(document.createTextNode(text.slice(cursor)));
      }
      parent.replaceChild(fragment, node);
    });
    return wrapped;
  }

  function clearPersistentAnnotationMarks() {
    annotationSourcesByElement = new WeakMap<HTMLElement, SourceAnnotation[]>();
    noteBodyElement
      ?.querySelectorAll<HTMLElement>('[data-annotation-source-marked="true"]')
      .forEach((element) => {
        if (element.tagName.toLowerCase() === "span") {
          const parent = element.parentNode;
          element.replaceWith(
            document.createTextNode(element.textContent ?? ""),
          );
          parent?.normalize();
          return;
        }
        element.classList.remove("annotation-source-marked");
        element.removeAttribute("data-annotation-source-marked");
        element.removeAttribute("data-annotation-source-href");
        element.removeAttribute("tabindex");
        element.removeAttribute("role");
        element.removeAttribute("aria-haspopup");
        element.removeAttribute("aria-label");
      });
  }

  function sameReanchorState(
    current: SourceAnnotation,
    next: SourceAnnotation,
  ) {
    return (
      current.status === next.status &&
      JSON.stringify(current.anchor) === JSON.stringify(next.anchor) &&
      JSON.stringify(current.reanchor) === JSON.stringify(next.reanchor)
    );
  }

  function reconcilePersistentAnnotations(targets: SourceSearchTarget[]) {
    if (noteAnnotations.length === 0) return noteAnnotations;
    if (noteAnnotationStorageMode === "legacy") return noteAnnotations;
    const sourceRevision = renderedSourceRevision(targets);
    const requiresSelectorUpgrade = noteAnnotations.some(
      (annotation) =>
        annotation.anchor.selector_version !== 1 || !annotation.reanchor,
    );
    if (
      sourceRevision === noteAnnotationSourceRevision &&
      !requiresSelectorUpgrade
    ) {
      return noteAnnotations;
    }

    const nextAnnotations = noteAnnotations.map((annotation) => {
      const resolution = reconcileTextQuoteAnchor(annotation.anchor, targets);
      const sourceHref = annotationSourceHref(
        resolution.anchor.quote,
        resolution.anchor.occurrence,
      );
      return {
        ...annotation,
        quote: resolution.anchor.quote,
        sourceHref,
        anchor: resolution.anchor,
        status: resolution.status,
        reanchor: {
          confidence: resolution.confidence,
          reason: resolution.reason,
        },
      } satisfies SourceAnnotation;
    });
    const updates = nextAnnotations.filter(
      (annotation, index) =>
        !sameReanchorState(noteAnnotations[index], annotation),
    );
    noteAnnotations = nextAnnotations;
    noteAnnotationSourceRevision = sourceRevision;

    if (annotationPatchToken === null && note?.content_hash) {
      const targetVault = vaultName;
      const targetNoteId = note.note_id;
      const baseRevision = noteAnnotationRevision;
      const baseNoteRevision = note.content_hash;
      const mutationToken = ++annotationMutationEpoch;
      annotationPatchToken = mutationToken;
      annotationError = "";
      void patchNoteAnnotationAnchors(
        targetVault,
        targetNoteId,
        sourceRevision,
        baseRevision,
        baseNoteRevision,
        updates,
      )
        .then((savedDocument) => {
          if (
            !isCurrentAnnotationTarget(targetVault, targetNoteId) ||
            annotationMutationEpoch !== mutationToken ||
            annotationPatchToken !== mutationToken ||
            noteAnnotationSourceRevision !== sourceRevision
          ) {
            return;
          }
          noteAnnotations =
            savedDocument.annotations.length > 0
              ? savedDocument.annotations
              : nextAnnotations;
          noteAnnotationSourceRevision =
            savedDocument.sourceRevision || sourceRevision;
          noteAnnotationRevision = savedDocument.annotationRevision;
          noteAnnotationStorageMode = savedDocument.storageMode;
          noteAnnotationLegacyRevision = savedDocument.legacyRevision;
          annotationError = "";
          schedulePersistentAnnotationMarks();
        })
        .catch((patchError: unknown) => {
          if (
            !isCurrentAnnotationTarget(targetVault, targetNoteId) ||
            annotationMutationEpoch !== mutationToken ||
            annotationPatchToken !== mutationToken
          )
            return;
          annotationError =
            patchError instanceof Error
              ? patchError.message
              : "Failed to persist re-anchored annotations.";
        })
        .finally(() => {
          if (annotationPatchToken === mutationToken) {
            annotationPatchToken = null;
          }
        });
    }
    return nextAnnotations;
  }

  function applyPersistentAnnotationMarks() {
    clearPersistentAnnotationMarks();
    if (!noteBodyElement || !note?.body || editMode) return false;

    annotationSourcesByElement = new WeakMap<HTMLElement, SourceAnnotation[]>();
    const targets = sourceSearchTargets(noteBodyElement);
    const parsedAnnotations = reconcilePersistentAnnotations(targets).filter(
      (annotation) => annotation.status === "active",
    );
    const grouped = new Map<string, SourceAnnotation[]>();
    for (const annotation of parsedAnnotations) {
      const group = grouped.get(annotation.sourceHref) ?? [];
      group.push(annotation);
      grouped.set(annotation.sourceHref, group);
    }

    let markedGroups = 0;
    const segmentPlans: AnnotationSegmentPlan[] = [];
    grouped.forEach((annotations, sourceHref) => {
      const match = annotationSourceMatch(sourceHref, targets);
      if (!match) return;
      const segments = annotationTextSegments(
        match.element,
        match.quote,
        match.occurrenceInElement,
      );
      if (segments.length === 0) return;
      markedGroups += 1;
      segments.forEach((segment) => {
        segmentPlans.push({
          ...segment,
          annotations,
          sourceHref,
        });
      });
    });
    const wrappedCount = wrapAnnotationSegmentPlans(segmentPlans);
    return (
      parsedAnnotations.length === 0 || (markedGroups > 0 && wrappedCount > 0)
    );
  }

  function cancelPersistentAnnotationMarkSchedule() {
    persistentAnnotationMarkGeneration += 1;
    persistentAnnotationMarkTimers.forEach((timer) => clearTimeout(timer));
    persistentAnnotationMarkTimers.clear();
  }

  function schedulePersistentAnnotationMarks(attempt = 0, generation?: number) {
    let scheduleGeneration = generation;
    if (scheduleGeneration === undefined) {
      cancelPersistentAnnotationMarkSchedule();
      scheduleGeneration = persistentAnnotationMarkGeneration;
    }
    const timer = window.setTimeout(
      () => {
        persistentAnnotationMarkTimers.delete(timer);
        if (scheduleGeneration !== persistentAnnotationMarkGeneration) return;
        if (!applyPersistentAnnotationMarks() && attempt < 20) {
          schedulePersistentAnnotationMarks(attempt + 1, scheduleGeneration);
        }
      },
      attempt === 0 ? 0 : 50,
    );
    persistentAnnotationMarkTimers.add(timer);
  }

  function clearAnnotationSourceHighlight() {
    if (annotationSourceHighlightTimer !== null) {
      clearTimeout(annotationSourceHighlightTimer);
      annotationSourceHighlightTimer = null;
    }
    noteBodyElement
      ?.querySelectorAll(".annotation-source-highlight")
      .forEach((element) =>
        element.classList.remove("annotation-source-highlight"),
      );
  }

  function markedSourcesForHash(hash: string) {
    if (!noteBodyElement) return [];
    return Array.from(
      noteBodyElement.querySelectorAll<HTMLElement>(
        '[data-annotation-source-marked="true"]',
      ),
    ).filter((element) => element.dataset.annotationSourceHref === hash);
  }

  function scrollToAnnotationSource(hash: string) {
    const markedSources = markedSourcesForHash(hash);
    const target = markedSources[0] ?? annotationSourceTarget(hash);
    if (!target) return false;
    clearAnnotationSourceHighlight();
    const highlightTargets =
      markedSources.length > 0 ? markedSources : [target];
    highlightTargets.forEach((element) =>
      element.classList.add("annotation-source-highlight"),
    );
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    annotationSourceHighlightTimer = setTimeout(() => {
      highlightTargets.forEach((element) =>
        element.classList.remove("annotation-source-highlight"),
      );
      annotationSourceHighlightTimer = null;
    }, 2200);
    return true;
  }

  function scheduleAnnotationHashScroll(
    hash = window.location.hash,
    attempt = 0,
  ) {
    if (!hash.startsWith("#quote=")) return;
    window.setTimeout(
      () => {
        if (!scrollToAnnotationSource(hash) && attempt < 20) {
          scheduleAnnotationHashScroll(hash, attempt + 1);
        }
      },
      attempt === 0 ? 0 : 50,
    );
  }

  function handleNoteBodyClick(event: MouseEvent) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const sourceLink = target.closest('a[href^="#quote="]');
    if (sourceLink instanceof HTMLAnchorElement) {
      event.preventDefault();
      scrollToAnnotationSource(sourceLink.getAttribute("href") ?? "");
      return;
    }
    const button = target.closest("button.note-task-state");
    if (button instanceof HTMLButtonElement) {
      const taskIndex = Number(button.dataset.taskIndex);
      const currentState = button.dataset.taskState ?? "[ ]";
      if (!Number.isFinite(taskIndex)) return;

      event.preventDefault();
      void saveTaskState(taskIndex, currentState);
      return;
    }

    if (isInteractiveAnnotationClickTarget(target)) return;
    const marked = target.closest<HTMLElement>(".annotation-source-marked");
    if (!marked || !noteBodyElement?.contains(marked)) return;
    if (
      openAnnotationPopupForSource(marked, {
        x: event.clientX,
        y: event.clientY,
      })
    ) {
      event.preventDefault();
    }
  }

  function handleNoteBodyKeyDown(event: KeyboardEvent) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    if (isInteractiveAnnotationClickTarget(target)) return;
    const marked = target.closest<HTMLElement>(".annotation-source-marked");
    if (!marked || !noteBodyElement?.contains(marked)) return;
    if (openAnnotationPopupForSource(marked)) {
      event.preventDefault();
    }
  }

  function taskStateClickAction(node: HTMLElement) {
    node.addEventListener("click", handleNoteBodyClick);
    node.addEventListener("keydown", handleNoteBodyKeyDown);

    return {
      destroy() {
        node.removeEventListener("click", handleNoteBodyClick);
        node.removeEventListener("keydown", handleNoteBodyKeyDown);
      },
    };
  }

  interface SelectedAnnotation {
    quote: string;
    range: Range;
    key: string;
    occurrence: number;
  }

  interface AnnotateMenu {
    x: number;
    y: number;
    quote: string;
    selectionKey: string;
    occurrence: number;
  }

  let annotateMenu = $state<AnnotateMenu | null>(null);
  let annotateDialog = $state<{
    quote: string;
    occurrence: number;
    editingAnnotation?: SourceAnnotation;
  } | null>(null);
  let annotationText = $state("");
  let annotationAddToLog = $state(false);
  let annotationSaving = $state(false);
  let annotationError = $state("");
  let annotationMutationEpoch = 0;
  let annotationPatchToken: number | null = null;
  let annotateDialogElement = $state<HTMLElement | null>(null);
  let annotationTextareaElement = $state<HTMLTextAreaElement | null>(null);
  let annotationDialogReturnFocus: HTMLElement | null = null;
  let annotationPopup = $state<AnnotationPopup | null>(null);
  let annotationSourcesByElement = new WeakMap<
    HTMLElement,
    SourceAnnotation[]
  >();
  let persistentAnnotationMarkGeneration = 0;
  const persistentAnnotationMarkTimers = new Set<number>();
  let longPressTimer: ReturnType<typeof setTimeout> | null = null;
  let noteBodyElement = $state<HTMLElement | null>(null);
  let annotateMenuInteracting = false;
  let annotationSourceHighlightTimer: ReturnType<typeof setTimeout> | null =
    null;
  const annotateMenuOffset = 10;
  const annotateMenuEdgeInset = 8;
  const annotateMenuEstimatedWidth = 160;
  const annotateMenuEstimatedHeight = 40;
  const annotationPopupEdgeInset = 8;
  const annotationPopupMaxSize = { width: 360, height: 420 };
  let annotationPopupDrag = $state<FloatingDragState | null>(null);

  function normalizeAnnotationQuote(value: string) {
    return value.replace(/\s+/g, " ").trim();
  }

  function countQuoteOccurrences(haystack: string, needle: string) {
    if (!needle) return 0;
    let count = 0;
    let index = 0;
    while (index <= haystack.length) {
      const found = haystack.indexOf(needle, index);
      if (found < 0) break;
      count += 1;
      index = found + needle.length;
    }
    return count;
  }

  function annotationOccurrenceForRange(
    container: HTMLElement,
    range: Range,
    quote: string,
  ) {
    const normalizedQuote = normalizeAnnotationQuote(quote);
    if (!normalizedQuote) return 0;
    try {
      const beforeRange = document.createRange();
      beforeRange.selectNodeContents(container);
      beforeRange.setEnd(range.startContainer, range.startOffset);
      return countQuoteOccurrences(
        normalizeAnnotationQuote(beforeRange.toString()),
        normalizedQuote,
      );
    } catch {
      return 0;
    }
  }

  function annotationSourceHref(quote: string, occurrence: number) {
    const encodedQuote = encodeURIComponent(normalizeAnnotationQuote(quote));
    const safeOccurrence = Math.max(0, Math.trunc(occurrence));
    return `#quote=${encodedQuote}&occ=${safeOccurrence}`;
  }

  function noteAnnotationsHref(vault: string, id: string) {
    return `/api/v1/vault/${encodeURIComponent(vault)}/annotations/note/${encodeURIComponent(id)}`;
  }

  function emptyNoteAnnotationDocument(
    note_id: string,
  ): NoteAnnotationDocumentV2 {
    return {
      version: 2,
      source_key: `note:${note_id}`,
      source: { kind: "note", note_id },
      annotations: [],
    };
  }

  function sourceAnnotationFromV2(
    annotation: NoteAnnotationV2,
  ): SourceAnnotation {
    const anchor: TextQuoteAnchor = {
      ...annotation.anchor,
      quote: normalizeAnnotationQuote(annotation.anchor.quote),
      heading_path: annotation.anchor.heading_path
        ? [...annotation.anchor.heading_path]
        : undefined,
    };
    const sourceHref = annotationSourceHref(anchor.quote, anchor.occurrence);
    const status = ["active", "needs_review", "orphaned"].includes(
      annotation.status ?? "",
    )
      ? (annotation.status as TextAnchorStatus)
      : "active";
    return {
      id: annotation.id,
      quote: anchor.quote,
      sourceHref,
      memo: annotation.comment ?? "",
      entryStartLine: 0,
      entryEndLine: 0,
      anchor,
      status,
      reanchor: annotation.reanchor,
      raw: structuredClone(annotation),
    };
  }

  function sourceAnnotationToV2(
    annotation: SourceAnnotation,
  ): NoteAnnotationV2 {
    const raw = annotation.raw ?? ({} as Partial<NoteAnnotationV2>);
    const reanchor =
      annotation.reanchor ??
      (annotation.status === "active"
        ? ({ confidence: 1, reason: "exact" } satisfies ReanchorMetadata)
        : undefined);
    return {
      ...raw,
      id: annotation.id,
      kind: "note",
      anchor: {
        ...(raw.anchor ?? {}),
        ...annotation.anchor,
        heading_path: annotation.anchor.heading_path
          ? [...annotation.anchor.heading_path]
          : undefined,
      },
      status: annotation.status,
      reanchor: annotation.reanchor,
      comment: annotation.memo,
      created_at: typeof raw.created_at === "string" ? raw.created_at : "",
      updated_at: typeof raw.updated_at === "string" ? raw.updated_at : "",
    };
  }

  function noteAnnotationDocumentFromSources(
    note_id: string,
    annotations: SourceAnnotation[],
  ): NoteAnnotationDocumentV2 {
    const document = emptyNoteAnnotationDocument(note_id);
    if (noteAnnotationSourceRevision) {
      document.source_revision = noteAnnotationSourceRevision;
    }
    document.annotations = annotations.map(sourceAnnotationToV2);
    return document;
  }

  function sourceAnnotationsFromDocument(payload: unknown): SourceAnnotation[] {
    if (!payload || typeof payload !== "object") return [];
    const raw = (payload as { annotations?: unknown }).annotations;
    if (!Array.isArray(raw)) return [];
    return raw.flatMap((annotation) => {
      if (!annotation || typeof annotation !== "object") return [];
      const candidate = annotation as Partial<NoteAnnotationV2>;
      if (
        candidate.kind !== "note" ||
        !candidate.anchor ||
        candidate.anchor.kind !== "text_quote" ||
        typeof candidate.anchor.quote !== "string" ||
        typeof candidate.anchor.occurrence !== "number" ||
        typeof candidate.id !== "string"
      ) {
        return [];
      }
      return [sourceAnnotationFromV2(candidate as NoteAnnotationV2)];
    });
  }

  function annotationDocumentState(payload: unknown, fallbackRevision = 0) {
    const document =
      payload && typeof payload === "object"
        ? (payload as Partial<NoteAnnotationDocumentV2>)
        : {};
    const annotationRevision =
      typeof document.annotation_revision === "number" &&
      Number.isInteger(document.annotation_revision) &&
      document.annotation_revision >= 0
        ? document.annotation_revision
        : fallbackRevision;
    const storageMode = ["none", "legacy", "v2"].includes(
      document.storage_mode ?? "",
    )
      ? (document.storage_mode as "none" | "legacy" | "v2")
      : "v2";
    return {
      annotations: sourceAnnotationsFromDocument(payload),
      sourceRevision:
        typeof document.source_revision === "string"
          ? document.source_revision
          : "",
      annotationRevision,
      storageMode,
      legacyRevision:
        typeof document.legacy_revision === "string"
          ? document.legacy_revision
          : "",
    };
  }

  async function loadNoteAnnotationSources(vault: string, id: string) {
    const payload = await apiGet<NoteAnnotationDocumentV2>(
      noteAnnotationsHref(vault, id),
    );
    return annotationDocumentState(payload);
  }

  async function putNoteAnnotationSources(
    vault: string,
    id: string,
    annotations: SourceAnnotation[],
  ) {
    const mutationToken = ++annotationMutationEpoch;
    const baseRevision = noteAnnotationRevision;
    const storageMode = noteAnnotationStorageMode;
    const legacyRevision = noteAnnotationLegacyRevision;
    const document = {
      ...noteAnnotationDocumentFromSources(id, annotations),
      base_revision: baseRevision,
      ...(storageMode === "legacy" && legacyRevision
        ? { legacy_revision: legacyRevision }
        : {}),
    };
    const response = await apiClient(noteAnnotationsHref(vault, id), {
      method: "PUT",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "If-Match": `"${baseRevision}"`,
      },
      body: JSON.stringify(document),
    });
    if (!response.ok) throw new Error(`PUT annotation -> ${response.status}`);
    return {
      ...annotationDocumentState(await response.json(), baseRevision + 1),
      mutationToken,
    };
  }

  async function patchNoteAnnotationAnchors(
    vault: string,
    id: string,
    sourceRevision: string,
    baseRevision: number,
    baseNoteRevision: string,
    updates: SourceAnnotation[],
  ) {
    const response = await apiClient(noteAnnotationsHref(vault, id), {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "If-Match": `"${baseRevision}"`,
      },
      body: JSON.stringify({
        base_revision: baseRevision,
        base_note_revision: baseNoteRevision,
        source_revision: sourceRevision,
        updates: updates.map((annotation) => ({
          id: annotation.id,
          anchor: annotation.anchor,
          status: annotation.status,
          reanchor: annotation.reanchor,
        })),
      }),
    });
    if (!response.ok) throw new Error(`PATCH annotation -> ${response.status}`);
    return annotationDocumentState(await response.json(), baseRevision + 1);
  }

  function selectedAnnotationDraft(
    quote: string,
    occurrence: number,
    memo: string,
  ): SourceAnnotation {
    const anchor: TextQuoteAnchor = {
      kind: "text_quote",
      quote: normalizeAnnotationQuote(quote),
      occurrence,
    };
    const targets = noteBodyElement ? sourceSearchTargets(noteBodyElement) : [];
    const resolution = reconcileTextQuoteAnchor(anchor, targets);
    if (targets.length > 0) {
      noteAnnotationSourceRevision = renderedSourceRevision(targets);
    }
    const sourceHref = annotationSourceHref(
      resolution.anchor.quote,
      resolution.anchor.occurrence,
    );
    return {
      id: `note-ann-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
      quote: resolution.anchor.quote,
      sourceHref,
      memo,
      entryStartLine: 0,
      entryEndLine: 0,
      anchor: resolution.anchor,
      status: resolution.status,
      reanchor: {
        confidence: resolution.confidence,
        reason: resolution.reason,
      },
    };
  }

  function selectedAnnotationInside(
    container: HTMLElement,
  ): SelectedAnnotation | null {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      return null;
    }
    const range = selection.getRangeAt(0);
    if (!container.contains(range.commonAncestorContainer)) return null;
    const quote = selection.toString().trim();
    if (!quote) return null;
    return {
      quote,
      range,
      key: `${quote}\u0000${range.startOffset}\u0000${range.endOffset}`,
      occurrence: annotationOccurrenceForRange(container, range, quote),
    };
  }

  function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
  }

  function rectHasLayout(rect: DOMRect) {
    return rect.width > 0 || rect.height > 0;
  }

  function positionForSelection(
    range: Range,
    fallback: { x: number; y: number },
  ) {
    const measuredRange = range as Range & {
      getBoundingClientRect?: () => DOMRect;
    };
    const rect = measuredRange.getBoundingClientRect?.();
    if (!rect || !rectHasLayout(rect)) {
      return {
        x: Math.round(fallback.x),
        y: Math.round(fallback.y),
      };
    }

    const halfWidth = annotateMenuEstimatedWidth / 2;
    const viewportWidth =
      window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight =
      window.innerHeight || document.documentElement.clientHeight;
    const x = rect.left + rect.width / 2;
    const y = rect.bottom + annotateMenuOffset;

    return {
      x: Math.round(
        clamp(
          x,
          annotateMenuEdgeInset + halfWidth,
          viewportWidth - annotateMenuEdgeInset - halfWidth,
        ),
      ),
      y: Math.round(
        clamp(
          y,
          annotateMenuEdgeInset,
          viewportHeight - annotateMenuEdgeInset - annotateMenuEstimatedHeight,
        ),
      ),
    };
  }

  function showAnnotateMenu(
    selected: SelectedAnnotation,
    fallback: { x: number; y: number },
  ) {
    const position = positionForSelection(selected.range, fallback);
    annotateMenu = {
      ...position,
      quote: selected.quote,
      selectionKey: selected.key,
      occurrence: selected.occurrence,
    };
  }

  function dismissAnnotationPopup() {
    annotationPopup = null;
    annotationPopupDrag = null;
  }

  function isInteractiveAnnotationClickTarget(target: Element) {
    if (target.closest(".annotation-source-marked")) return false;
    return Boolean(
      target.closest(
        'a[href],button,input,textarea,select,summary,[role="button"]:not(.annotation-source-marked)',
      ),
    );
  }

  function annotationPopupSize() {
    return floatingSizeForViewport(
      annotationPopupMaxSize,
      viewportSize(),
      annotationPopupEdgeInset,
    );
  }

  function annotationPopupPosition(
    element: HTMLElement,
    fallback?: { x: number; y: number },
  ) {
    const rect = element.getBoundingClientRect();
    const viewport = viewportSize();
    const size = annotationPopupSize();
    if (rectHasLayout(rect)) {
      return floatingTopLeftFromAnchor(
        {
          x: rect.left + Math.min(rect.width, 280) / 2,
          y: rect.bottom + 8,
        },
        size,
        viewport,
        annotationPopupEdgeInset,
      );
    }
    return floatingTopLeftFromAnchor(
      { x: fallback?.x ?? 16, y: fallback?.y ?? 16 },
      size,
      viewport,
      annotationPopupEdgeInset,
    );
  }

  function startAnnotationPopupDrag(event: PointerEvent) {
    if (!annotationPopup) return;
    const target = event.target;
    if (target instanceof Element && target.closest("button")) return;
    const popup = (event.currentTarget as HTMLElement).closest<HTMLElement>(
      ".annotation-popover",
    );
    const rect = popup?.getBoundingClientRect();
    const currentLeft = rect && rect.width > 0 ? rect.left : annotationPopup.x;
    const currentTop = rect && rect.height > 0 ? rect.top : annotationPopup.y;
    annotationPopupDrag = {
      offsetX: event.clientX - currentLeft,
      offsetY: event.clientY - currentTop,
    };
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function dragAnnotationPopup(event: PointerEvent) {
    if (!annotationPopup || !annotationPopupDrag) return;
    const position = clampFloatingPosition(
      {
        x: event.clientX - annotationPopupDrag.offsetX,
        y: event.clientY - annotationPopupDrag.offsetY,
      },
      annotationPopupSize(),
      viewportSize(),
      annotationPopupEdgeInset,
    );
    annotationPopup = { ...annotationPopup, ...position };
  }

  function endAnnotationPopupDrag() {
    annotationPopupDrag = null;
  }

  function openAnnotationPopupForSource(
    element: HTMLElement,
    fallback?: { x: number; y: number },
  ) {
    const annotations = annotationSourcesByElement.get(element);
    if (!annotations?.length) return false;
    annotationPopup = {
      ...annotationPopupPosition(element, fallback),
      annotations,
    };
    return true;
  }

  function toggleNoteAnnotationsPanel() {
    noteAnnotationsPanelOpen = !noteAnnotationsPanelOpen;
    if (noteAnnotationsPanelOpen) {
      dismissAnnotateMenu();
      dismissAnnotationPopup();
    }
  }

  function openNoteAnnotationSource(annotation: SourceAnnotation) {
    dismissAnnotateMenu();
    dismissAnnotationPopup();
    scrollToAnnotationSource(annotation.sourceHref);
  }

  function openNoteAnnotationEditor(annotation: SourceAnnotation) {
    dismissAnnotateMenu();
    openEditAnnotation(annotation);
  }

  async function deleteNoteAnnotationFromPanel(annotation: SourceAnnotation) {
    dismissAnnotateMenu();
    await deleteAnnotation(annotation);
  }

  function handleNoteBodyContextMenu(event: MouseEvent) {
    const noteBodyEl = event.currentTarget as HTMLElement;
    const selected = selectedAnnotationInside(noteBodyEl);
    if (!selected) return;
    event.preventDefault();
    showAnnotateMenu(selected, { x: event.clientX, y: event.clientY });
  }

  function clearLongPressTimer() {
    if (longPressTimer !== null) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
    }
  }

  function dismissAnnotateMenu() {
    clearLongPressTimer();
    annotateMenu = null;
  }

  function handleNoteBodyPointerDown(event: PointerEvent) {
    if (event.pointerType !== "touch") return;
    const noteBodyEl = event.currentTarget as HTMLElement;
    const fallback = { x: event.clientX, y: event.clientY };
    clearLongPressTimer();
    longPressTimer = setTimeout(() => {
      const selected = selectedAnnotationInside(noteBodyEl);
      if (selected) {
        showAnnotateMenu(selected, fallback);
      }
      longPressTimer = null;
    }, 600);
  }

  function rememberAnnotationDialogTrigger() {
    annotationDialogReturnFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
  }

  function focusAnnotationDialog() {
    void tick().then(() => annotationTextareaElement?.focus());
  }

  function openAnnotateDialog() {
    if (!annotateMenu) return;
    rememberAnnotationDialogTrigger();
    annotateDialog = {
      quote: annotateMenu.quote,
      occurrence: annotateMenu.occurrence,
    };
    annotationText = "";
    annotationAddToLog = false;
    annotationError = "";
    annotateMenu = null;
    focusAnnotationDialog();
  }

  function closeAnnotateDialog() {
    const returnFocus = annotationDialogReturnFocus;
    annotationDialogReturnFocus = null;
    annotateDialog = null;
    annotationText = "";
    annotationAddToLog = false;
    annotationError = "";
    annotationSaving = false;
    void tick().then(() => {
      if (returnFocus && document.contains(returnFocus)) returnFocus.focus();
    });
  }

  function resetAnnotationState() {
    clearLongPressTimer();
    cancelPersistentAnnotationMarkSchedule();
    noteAnnotationsPanelOpen = false;
    noteAnnotations = [];
    noteAnnotationSourceRevision = "";
    noteAnnotationRevision = 0;
    noteAnnotationStorageMode = "none";
    noteAnnotationLegacyRevision = "";
    annotationMutationEpoch += 1;
    annotationPatchToken = null;
    annotateMenu = null;
    dismissAnnotationPopup();
    clearPersistentAnnotationMarks();
    annotationDialogReturnFocus = null;
    closeAnnotateDialog();
  }

  function isCurrentAnnotationTarget(
    targetVault: string,
    targetNoteId: string,
  ) {
    return (
      vaultName === targetVault &&
      noteId === targetNoteId &&
      note?.note_id === targetNoteId
    );
  }

  function openEditAnnotation(annotation: SourceAnnotation) {
    rememberAnnotationDialogTrigger();
    const parsed = parseAnnotationSourceHash(annotation.sourceHref);
    annotateDialog = {
      quote: annotation.quote,
      occurrence: parsed?.occurrence ?? 0,
      editingAnnotation: annotation,
    };
    annotationText = annotation.memo;
    annotationAddToLog = false;
    annotationError = "";
    dismissAnnotationPopup();
    focusAnnotationDialog();
  }

  async function deleteAnnotation(annotation: SourceAnnotation) {
    if (!note || annotationSaving) return;
    annotationSaving = true;
    annotationError = "";
    const targetVault = vaultName;
    const targetNoteId = note.note_id;
    const nextAnnotations = noteAnnotations.filter(
      (candidate) => candidate.id !== annotation.id,
    );

    try {
      const savedDocument = await putNoteAnnotationSources(
        targetVault,
        targetNoteId,
        nextAnnotations,
      );
      if (
        !isCurrentAnnotationTarget(targetVault, targetNoteId) ||
        annotationMutationEpoch !== savedDocument.mutationToken
      )
        return;
      noteAnnotations = savedDocument.annotations;
      noteAnnotationSourceRevision = savedDocument.sourceRevision;
      noteAnnotationRevision = savedDocument.annotationRevision;
      noteAnnotationStorageMode = savedDocument.storageMode;
      noteAnnotationLegacyRevision = savedDocument.legacyRevision;
      dismissAnnotationPopup();
      await tick();
      if (!applyPersistentAnnotationMarks()) {
        schedulePersistentAnnotationMarks();
      }
    } catch (e) {
      if (!isCurrentAnnotationTarget(targetVault, targetNoteId)) return;
      annotationError =
        e instanceof Error ? e.message : "Failed to delete annotation.";
    } finally {
      if (isCurrentAnnotationTarget(targetVault, targetNoteId)) {
        annotationSaving = false;
      }
    }
  }

  async function saveAnnotation() {
    if (!note || !annotateDialog || annotationSaving) return;
    const quote = annotateDialog.quote;
    const occurrence = annotateDialog.occurrence;
    const text = annotationText.trim();
    if (!text) {
      annotationError = "Annotation text is required.";
      return;
    }
    annotationSaving = true;
    annotationError = "";
    const shouldLog = !annotateDialog.editingAnnotation && annotationAddToLog;
    const targetVault = vaultName;
    const targetNoteId = note.note_id;
    const editingAnnotation = annotateDialog.editingAnnotation;
    const nextAnnotation = editingAnnotation
      ? { ...editingAnnotation, memo: text }
      : selectedAnnotationDraft(quote, occurrence, text);
    const nextAnnotations = editingAnnotation
      ? noteAnnotations.some(
          (annotation) => annotation.id === editingAnnotation.id,
        )
        ? noteAnnotations.map((annotation) =>
            annotation.id === editingAnnotation.id
              ? nextAnnotation
              : annotation,
          )
        : [...noteAnnotations, nextAnnotation]
      : [...noteAnnotations, nextAnnotation];

    try {
      const savedDocument = await putNoteAnnotationSources(
        targetVault,
        targetNoteId,
        nextAnnotations,
      );
      if (
        !isCurrentAnnotationTarget(targetVault, targetNoteId) ||
        annotationMutationEpoch !== savedDocument.mutationToken
      )
        return;
      noteAnnotations = savedDocument.annotations;
      noteAnnotationSourceRevision = savedDocument.sourceRevision;
      noteAnnotationRevision = savedDocument.annotationRevision;
      noteAnnotationStorageMode = savedDocument.storageMode;
      noteAnnotationLegacyRevision = savedDocument.legacyRevision;
      annotateDialog = {
        quote,
        occurrence,
        editingAnnotation:
          savedDocument.annotations.find(
            (annotation) => annotation.id === nextAnnotation.id,
          ) ?? nextAnnotation,
      };

      if (shouldLog) {
        const logResponse = await apiClient(
          `/api/v1/vault/${targetVault}/daily/today`,
          {
            method: "POST",
            body: JSON.stringify({
              type: "entry",
              content: `Annotated [[${targetNoteId}]]: “${quote.replace(/\s+/g, " ").trim()}” — ${text}`,
            }),
          },
        );
        if (!logResponse.ok) {
          throw new Error(`POST daily log -> ${logResponse.status}`);
        }
      }

      if (!isCurrentAnnotationTarget(targetVault, targetNoteId)) return;
      await tick();
      schedulePersistentAnnotationMarks();
      closeAnnotateDialog();
    } catch (e) {
      if (!isCurrentAnnotationTarget(targetVault, targetNoteId)) return;
      annotationError =
        e instanceof Error ? e.message : "Failed to save annotation.";
    } finally {
      if (isCurrentAnnotationTarget(targetVault, targetNoteId)) {
        annotationSaving = false;
      }
    }
  }

  async function loadNote(vault: string, id: string) {
    const token = ++loadToken;
    note = null;
    neighbors = null;
    loadingNote = true;
    loadingNeighbors = true;
    error = "";
    editorDoc = "";
    savedDoc = "";
    saveError = "";
    saveStatus = "";
    editMode = false;
    resetAnnotationState();
    graphKeyNav.clearCurrentNoteNavigationContext();

    const noteEndpoint = dailyNoteIdPattern.test(id)
      ? `/api/v1/vault/${vault}/daily/${id}`
      : `/api/v1/vault/${vault}/notes/${id}`;

    const [noteResult, neighborsResult, annotationsResult] =
      await Promise.allSettled([
        loadOrCreateNote(vault, id, noteEndpoint),
        apiGet<NeighborData>(`/api/v1/vault/${vault}/notes/${id}/neighbors`),
        loadNoteAnnotationSources(vault, id),
      ]);

    if (token !== loadToken) return;

    let loadedNote: Note | null = null;
    if (noteResult.status === "fulfilled") {
      loadedNote = noteResult.value;
      const loadedBody = loadedNote.body ?? "";
      if (token !== loadToken) return;
      note = loadedNote;
      editorDoc = loadedBody;
      savedDoc = loadedBody;
    } else {
      error = isTagNoteId(id) ? "Tag note not found." : "Note not found.";
    }
    loadingNote = false;

    if (neighborsResult.status === "fulfilled") {
      neighbors = neighborsResult.value;
    }
    if (annotationsResult.status === "fulfilled") {
      noteAnnotations = annotationsResult.value.annotations;
      noteAnnotationSourceRevision = annotationsResult.value.sourceRevision;
      noteAnnotationRevision = annotationsResult.value.annotationRevision;
      noteAnnotationStorageMode = annotationsResult.value.storageMode;
      noteAnnotationLegacyRevision = annotationsResult.value.legacyRevision;
    } else {
      noteAnnotations = [];
      noteAnnotationSourceRevision = "";
      noteAnnotationRevision = 0;
      noteAnnotationStorageMode = "none";
      noteAnnotationLegacyRevision = "";
    }
    loadingNeighbors = false;

    if (loadedNote && neighborsResult.status === "fulfilled") {
      graphKeyNav.setCurrentNoteNavigationContext(
        vault,
        loadedNote.note_id,
        neighborsResult.value.semantic ?? [],
      );
    } else {
      graphKeyNav.clearCurrentNoteNavigationContext(vault, id);
    }

    rememberVault(vault);
    await tick();
    if (token === loadToken) {
      schedulePersistentAnnotationMarks();
      scheduleAnnotationHashScroll(window.location.hash);
    }
  }

  async function loadOrCreateNote(vault: string, id: string, endpoint: string) {
    try {
      return await apiGet<Note>(endpoint);
    } catch (e) {
      if (
        dailyNoteIdPattern.test(id) ||
        isTagNoteId(id) ||
        !isNotFoundError(e)
      ) {
        throw e;
      }
      const response = await apiClient(
        `/api/v1/vault/${vault}/notes/${encodeURIComponent(id)}/ensure`,
        { method: "POST" },
      );
      if (!response.ok)
        throw new Error(`POST ensure note → ${response.status}`);
      return (await response.json()) as Note;
    }
  }

  function isNotFoundError(errorValue: unknown) {
    return (
      errorValue instanceof Error &&
      /(?:→|->)\s*404\b|404/.test(errorValue.message)
    );
  }

  async function saveNoteBody() {
    if (!note || saving || !editorDirty) return;
    saving = true;
    saveError = "";
    saveStatus = "Saving";

    try {
      const response = await apiClient(
        `/api/v1/vault/${vaultName}/notes/${encodeURIComponent(note.note_id)}`,
        {
          method: "PUT",
          headers: note.content_hash
            ? { "If-Match": `"${note.content_hash}"` }
            : undefined,
          body: JSON.stringify({ body: editorDoc }),
        },
      );
      if (!response.ok) throw new Error(`PUT note body -> ${response.status}`);

      const updatedNote = (await response.json()) as Note;
      const body = updatedNote.body ?? editorDoc;
      note = { ...updatedNote, body };
      editorDoc = body;
      savedDoc = body;
      saveStatus = "Saved";
    } catch (e) {
      saveError = e instanceof Error ? e.message : "Failed to save note.";
      saveStatus = "Unsaved";
    } finally {
      saving = false;
    }
  }

  $effect(() => {
    if (!vaultName || !noteId) return;
    untrack(() => {
      void loadNote(vaultName, noteId);
    });
  });

  $effect(() => {
    if (editMode && noteAnnotationsPanelOpen) {
      noteAnnotationsPanelOpen = false;
    }
  });

  $effect(() => {
    const body = note?.body ?? "";
    const annotationCount = noteAnnotations.length;
    const targetElement = noteBodyElement;
    const reading = !editMode;
    if (!targetElement || !body || !reading) {
      cancelPersistentAnnotationMarkSchedule();
      clearPersistentAnnotationMarks();
      dismissAnnotationPopup();
      return;
    }
    void tick().then(() => {
      if (
        noteBodyElement === targetElement &&
        note?.body === body &&
        noteAnnotations.length === annotationCount &&
        !editMode
      ) {
        schedulePersistentAnnotationMarks();
      }
    });
  });

  $effect(() => {
    const root = notePageElement;
    noteScrollElement = closestScrollContainer(root);
  });

  onMount(() => {
    const handleSelectionChange = () => {
      if (!annotateMenu || annotateMenuInteracting || !noteBodyElement) return;
      const selected = selectedAnnotationInside(noteBodyElement);
      if (!selected || selected.key !== annotateMenu.selectionKey) {
        annotateMenu = null;
      }
    };

    const handleGlobalPointerDown = (event: PointerEvent) => {
      const target = event.target;
      const isInsideMenu =
        target instanceof Element && Boolean(target.closest(".annotate-menu"));
      const isInsideAnnotationPopup =
        target instanceof Element &&
        Boolean(target.closest(".annotation-popover"));
      const isInsideNoteAnnotationsPanel =
        target instanceof Element &&
        Boolean(target.closest(".note-annotations-panel"));
      const isInsideMarkedSource =
        target instanceof Element &&
        Boolean(target.closest(".annotation-source-marked"));
      if (
        isInsideAnnotationPopup ||
        isInsideNoteAnnotationsPanel ||
        isInsideMarkedSource
      )
        return;
      if (annotationPopup) annotationPopup = null;
      if (isInsideMenu) {
        annotateMenuInteracting = true;
        window.setTimeout(() => {
          annotateMenuInteracting = false;
        }, 250);
        return;
      }
      if (annotateMenu) annotateMenu = null;
    };

    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      if (annotateDialog && annotateDialogElement) {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          closeAnnotateDialog();
          return;
        }
        if (event.key === "Tab") {
          const focusable = Array.from(
            annotateDialogElement.querySelectorAll<HTMLElement>(
              'textarea:not([disabled]), input:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])',
            ),
          );
          if (focusable.length > 0) {
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            const active = document.activeElement;
            if (
              event.shiftKey &&
              (active === first || !annotateDialogElement.contains(active))
            ) {
              event.preventDefault();
              last.focus();
            } else if (
              !event.shiftKey &&
              (active === last || !annotateDialogElement.contains(active))
            ) {
              event.preventDefault();
              first.focus();
            }
          }
          return;
        }
      }
      if (event.key === "Escape") {
        dismissAnnotateMenu();
        dismissAnnotationPopup();
      }
    };

    const handleHashChange = () => {
      scheduleAnnotationHashScroll(window.location.hash);
    };

    document.addEventListener("selectionchange", handleSelectionChange);
    document.addEventListener("pointerdown", handleGlobalPointerDown, true);
    document.addEventListener("keydown", handleGlobalKeyDown, true);
    window.addEventListener("hashchange", handleHashChange);
    window.addEventListener("scroll", dismissAnnotateMenu, true);
    window.addEventListener("wheel", dismissAnnotateMenu, { passive: true });
    window.addEventListener("touchmove", dismissAnnotateMenu, {
      passive: true,
    });
    scheduleAnnotationHashScroll();

    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
      document.removeEventListener(
        "pointerdown",
        handleGlobalPointerDown,
        true,
      );
      document.removeEventListener("keydown", handleGlobalKeyDown, true);
      window.removeEventListener("hashchange", handleHashChange);
      window.removeEventListener("scroll", dismissAnnotateMenu, true);
      window.removeEventListener("wheel", dismissAnnotateMenu);
      window.removeEventListener("touchmove", dismissAnnotateMenu);
    };
  });

  onDestroy(() => {
    resetAnnotationState();
    clearAnnotationSourceHighlight();
    graphKeyNav.clearCurrentNoteNavigationContext(vaultName, noteId);
  });
</script>

<svelte:head>
  <title>{note?.title ?? noteId} — pkm</title>
</svelte:head>

<div bind:this={notePageElement} class="note-page">
  {#if loadingNote}
    <p class="status">Loading…</p>
  {:else if error}
    <div class="missing-note">
      {#if isTagNoteId(noteId)}
        <header class="tag-header">
          <div class="meta-rail">
            <span>TAG HUB</span>
            <span>{neighbors?.inbound?.length ?? 0} linked notes</span>
          </div>
        </header>
      {/if}
      <p class="status error">{error}</p>
      {#if isTagNoteId(noteId)}
        <NeighborPanel
          {vaultName}
          data={neighbors}
          loading={loadingNeighbors}
        />
      {/if}
    </div>
  {:else if note}
    <article class="note-article">
      <header class="note-header">
        <div class="meta-rail">
          <span>NOTE</span>
          <span>{note.note_id}</span>
          {#if note.updated}
            <span>updated {note.updated}</span>
          {:else if note.created}
            <span>created {note.created}</span>
          {/if}
          {#if note.importance !== null}
            <span>imp {note.importance}</span>
          {/if}
        </div>
        <div class="note-header-actions">
          {#if !editMode}
            <button
              type="button"
              class="note-annotations-toggle"
              class:active={noteAnnotationsPanelOpen}
              data-testid="note-annotations-toggle"
              aria-expanded={noteAnnotationsPanelOpen}
              aria-controls="note-annotations-panel"
              onclick={toggleNoteAnnotationsPanel}
            >
              Annotations ({noteAnnotations.length})
            </button>
          {/if}
          <div class="mode-toggle" aria-label="Display mode">
            <button
              type="button"
              class:active={!editMode}
              onclick={() => (editMode = false)}
            >
              Read
            </button>
            <button
              type="button"
              class:active={editMode}
              onclick={() => (editMode = true)}
            >
              Edit
            </button>
          </div>
        </div>
        {#if note.tags?.length}
          <p class="note-tags">
            {#each note.tags as tag}
              <a
                class="note-tag-chip note-meta-tag-chip"
                href={tagHref(vaultName, tag)}
                data-tag={tag}
                style={`--tag-hue: ${tagHue(tag)}`}>#{tag}</a
              >
            {/each}
          </p>
        {/if}
      </header>

      {#if annotationError}
        <p class="annotation-sync-error" role="alert">{annotationError}</p>
      {/if}

      {#if !editMode && noteAnnotationsPanelOpen}
        <section
          id="note-annotations-panel"
          class="note-annotations-panel"
          data-testid="note-annotations-panel"
          aria-label="Note annotations"
        >
          {#if noteAnnotations.length === 0}
            <p
              class="note-annotations-empty"
              data-testid="note-annotations-empty"
            >
              No annotations yet. Select note text to add one.
            </p>
          {:else}
            <div class="note-annotation-card-list">
              {#each noteAnnotations as annotation (annotation.id)}
                <article
                  class="note-annotation-card"
                  data-testid="note-annotation-card"
                >
                  <div class="note-annotation-card-meta">
                    <span>Note annotation</span>
                    <span
                      class={`annotation-status annotation-status--${annotation.status}`}
                    >
                      {annotation.status === "needs_review"
                        ? "Needs review"
                        : annotation.status === "orphaned"
                          ? "Orphaned"
                          : "Active"}
                    </span>
                  </div>
                  <blockquote>{annotation.quote}</blockquote>
                  <p class="note-annotation-card-memo">{annotation.memo}</p>
                  <div class="note-annotation-card-actions">
                    <button
                      type="button"
                      data-testid="note-annotation-card-source"
                      disabled={annotationSaving ||
                        annotation.status !== "active"}
                      onclick={() => openNoteAnnotationSource(annotation)}
                    >
                      원문 보기
                    </button>
                    <button
                      type="button"
                      data-testid="note-annotation-card-edit"
                      disabled={annotationSaving}
                      onclick={() => openNoteAnnotationEditor(annotation)}
                    >
                      수정
                    </button>
                    <button
                      type="button"
                      class="danger"
                      data-testid="note-annotation-card-delete"
                      disabled={annotationSaving}
                      onclick={() =>
                        void deleteNoteAnnotationFromPanel(annotation)}
                    >
                      삭제
                    </button>
                  </div>
                </article>
              {/each}
            </div>
          {/if}
        </section>
      {/if}

      {#if editMode}
        <div class="editor-toolbar" aria-label="Editor controls">
          <div class="editor-mode-toggle" aria-label="Editor mode">
            <button
              type="button"
              class:active={editorMode === "vim"}
              aria-pressed={editorMode === "vim"}
              onclick={() => (editorMode = "vim")}
            >
              Vim
            </button>
            <button
              type="button"
              class:active={editorMode === "plain"}
              aria-pressed={editorMode === "plain"}
              onclick={() => (editorMode = "plain")}
            >
              Plain
            </button>
          </div>
          <span
            class:error={!!saveError}
            class="editor-save-status"
            aria-live="polite"
          >
            {saveError ||
              (saving
                ? "Saving"
                : editorDirty
                  ? "Unsaved"
                  : saveStatus || "Saved")}
          </span>
          <button
            type="button"
            class="save-note-button"
            aria-label="Save note"
            disabled={!editorDirty || saving}
            onclick={() => void saveNoteBody()}
          >
            Save
          </button>
        </div>
        <div class="note-editor">
          {#key editorMode}
            <CodeMirror
              bind:doc={editorDoc}
              vimMode={editorMode === "vim"}
              onSave={saveNoteBody}
            />
          {/key}
        </div>
      {:else}
        <!-- Rendered markdown body -->
        <div
          bind:this={noteBodyElement}
          class="note-body prose"
          role="region"
          aria-label="Note body"
          use:taskStateClickAction
          oncontextmenu={handleNoteBodyContextMenu}
          onpointerdown={handleNoteBodyPointerDown}
          onpointerup={clearLongPressTimer}
          onpointercancel={clearLongPressTimer}
          onpointerleave={clearLongPressTimer}
        >
          <MarkdownRenderer
            markdown={note.body ?? ""}
            vault={vaultName}
            transformMarkdown={withTaskStateButtons}
          />
        </div>
      {/if}

      {#if annotateMenu}
        <div
          class="annotate-menu"
          style="left:{annotateMenu.x}px;top:{annotateMenu.y}px;"
        >
          <button
            type="button"
            aria-label="Annotate selection"
            onclick={openAnnotateDialog}
          >
            Annotate
          </button>
        </div>
      {/if}

      {#if annotateDialog}
        <div
          bind:this={annotateDialogElement}
          role="dialog"
          aria-modal="true"
          aria-label={annotateDialog.editingAnnotation
            ? "Edit annotation"
            : "Annotate selection"}
          class="annotate-dialog"
        >
          <p class="annotate-quote">“{annotateDialog.quote}”</p>
          <label class="annotate-field">
            <span>Annotation</span>
            <textarea
              bind:this={annotationTextareaElement}
              aria-label="Annotation text"
              bind:value={annotationText}
              disabled={annotationSaving}
            ></textarea>
          </label>
          {#if annotationError}
            <p class="annotate-error" aria-live="polite">{annotationError}</p>
          {/if}
          <label class="annotate-checkbox">
            <input
              type="checkbox"
              aria-label="Add annotation to daily log"
              bind:checked={annotationAddToLog}
              disabled={annotationSaving}
            />
            <span>Add to daily log</span>
          </label>
          <div class="annotate-actions">
            <button
              type="button"
              onclick={closeAnnotateDialog}
              aria-label="Cancel annotation"
              disabled={annotationSaving}
            >
              Cancel
            </button>
            <button
              type="button"
              aria-label="Save annotation"
              onclick={() => void saveAnnotation()}
              disabled={annotationSaving}
            >
              {annotationSaving ? "Saving" : "Save"}
            </button>
          </div>
        </div>
      {/if}

      {#if annotationPopup}
        <div
          role="dialog"
          aria-label="Annotation memo"
          class="annotation-popover"
          style="left:{annotationPopup.x}px;top:{annotationPopup.y}px;"
        >
          <div
            class="annotation-popover-header"
            role="group"
            aria-label="Draggable annotation memo header"
            onpointerdown={startAnnotationPopupDrag}
            onpointermove={dragAnnotationPopup}
            onpointerup={endAnnotationPopupDrag}
            onpointercancel={endAnnotationPopupDrag}
          >
            <span>Annotation</span>
            <button
              type="button"
              aria-label="Close annotation memo"
              onclick={dismissAnnotationPopup}>×</button
            >
          </div>
          {#if annotationError}
            <p class="annotate-error" aria-live="polite">{annotationError}</p>
          {/if}
          <ul class="annotation-popover-list">
            {#each annotationPopup.annotations as annotation (annotation.id)}
              <li>
                <p class="annotation-popover-quote">“{annotation.quote}”</p>
                <p class="annotation-popover-memo">{annotation.memo}</p>
                <div class="annotation-popover-actions">
                  <button
                    type="button"
                    aria-label="Edit annotation"
                    disabled={annotationSaving}
                    onclick={() => openEditAnnotation(annotation)}
                  >
                    수정
                  </button>
                  <button
                    type="button"
                    aria-label="Delete annotation"
                    disabled={annotationSaving}
                    onclick={() => void deleteAnnotation(annotation)}
                  >
                    삭제
                  </button>
                </div>
              </li>
            {/each}
          </ul>
        </div>
      {/if}

      <!-- Signature NeighborPanel -->
      <NeighborPanel {vaultName} data={neighbors} loading={loadingNeighbors} />
    </article>
  {/if}
  {#if note && !editMode}
    <ScrollPositionOverlay
      scrollElement={noteScrollElement}
      testId="note-scroll-position-overlay"
    />
  {/if}
</div>

<style>
  .note-page {
    width: var(--page-content-width);
    max-width: none;
    margin: 0 auto;
    padding: var(--space-6, 32px) 0 var(--space-8, 64px);
  }

  .note-article {
    width: 100%;
  }

  .missing-note {
    width: 100%;
  }

  .note-header,
  .tag-header {
    margin-bottom: var(--space-5, 24px);
    border: 0;
    padding: 0;
  }

  .meta-rail {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3, 12px);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }

  .note-header-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-2, 8px);
    margin-top: var(--space-3, 12px);
  }

  .note-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    margin: var(--space-3, 12px) 0 0;
  }

  .mode-toggle {
    display: flex;
    align-items: center;
    width: 124px;
    flex-shrink: 0;
    border: 1px solid var(--border);
  }

  .note-annotations-toggle {
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text-muted);
    background: transparent;
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .note-annotations-toggle.active,
  .note-annotations-toggle:hover,
  .note-annotations-toggle:focus-visible {
    color: var(--bg);
    background: var(--accent);
    border-color: var(--accent);
    outline: none;
  }

  .note-annotations-panel {
    box-sizing: border-box;
    display: block;
    max-height: min(360px, 45vh);
    margin: 0 0 var(--space-5, 24px);
    padding: var(--space-3, 12px);
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface, var(--bg));
  }

  .note-annotation-card-list {
    display: grid;
    gap: var(--space-3, 12px);
  }

  .note-annotation-card {
    display: grid;
    gap: var(--space-2, 8px);
    padding: var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg);
  }

  .note-annotation-card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .annotation-status {
    padding: 2px 7px;
    border: 1px solid color-mix(in srgb, var(--text-muted) 45%, transparent);
    border-radius: 999px;
  }

  .annotation-status--active {
    border-color: color-mix(in srgb, #35c978 55%, var(--border));
    color: #35c978;
  }

  .annotation-status--needs_review {
    border-color: color-mix(in srgb, #e8a735 65%, var(--border));
    color: #e8a735;
  }

  .annotation-status--orphaned {
    border-color: color-mix(in srgb, #ff6b6b 65%, var(--border));
    color: #ff8c8c;
  }

  .note-annotation-card blockquote,
  .note-annotation-card p {
    margin: 0;
  }

  .note-annotation-card blockquote {
    padding-left: var(--space-2, 8px);
    border-left: 3px solid color-mix(in srgb, var(--accent) 68%, transparent);
    color: var(--text);
    font-family: var(--font-mono);
  }

  .note-annotation-card-memo {
    white-space: pre-wrap;
  }

  .note-annotations-empty {
    margin: 0;
    color: var(--text-muted);
  }

  .note-annotation-card-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2, 8px);
  }

  .note-annotation-card-actions button {
    min-height: 28px;
    padding: 0 var(--space-3, 12px);
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--text);
    background: var(--surface, transparent);
    cursor: pointer;
  }

  .note-annotation-card-actions button:hover,
  .note-annotation-card-actions button:focus-visible {
    border-color: var(--accent);
    outline: none;
  }

  .note-annotation-card-actions button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .note-annotation-card-actions button.danger {
    border-color: color-mix(in srgb, #ff5a5f 70%, var(--border));
    color: #ffb4b4;
  }

  .mode-toggle button {
    flex: 1;
    background: none;
    border: none;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 7px 8px;
    cursor: pointer;
  }

  .mode-toggle button + button {
    border-left: 1px solid var(--border);
  }

  .mode-toggle button.active,
  .mode-toggle button:hover {
    color: var(--bg);
    background: var(--accent);
  }

  .editor-toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-3, 12px);
    margin-bottom: var(--space-2, 8px);
    font-family: var(--font-mono);
  }

  .editor-mode-toggle {
    display: flex;
    border: 1px solid var(--border);
  }

  .editor-mode-toggle button,
  .save-note-button {
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    background: transparent;
    border: 0;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .editor-mode-toggle button + button {
    border-left: 1px solid var(--border);
  }

  .editor-mode-toggle button.active,
  .editor-mode-toggle button:hover,
  .save-note-button:not(:disabled):hover {
    color: var(--bg);
    background: var(--accent);
  }

  .editor-save-status {
    color: var(--text-faint);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .editor-save-status.error {
    color: var(--signal-danger, #c0392b);
  }

  .save-note-button {
    margin-left: auto;
    border: 1px solid var(--border);
  }

  .save-note-button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .note-editor {
    min-height: 60vh;
    border: 1px solid var(--border);
    margin-bottom: var(--space-5, 24px);
    background: var(--surface-prose, var(--bg-elev));
  }

  .note-body {
    background: transparent;
    border: 0;
    border-top: 0;
    max-width: none;
    padding: 0;
    padding-top: 0;
    margin-bottom: var(--space-5, 24px);
    min-width: 0;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .note-body :global(*) {
    max-width: 100%;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .annotate-menu {
    position: fixed;
    z-index: 40;
    transform: translateX(-50%);
    border: 1px solid color-mix(in srgb, var(--accent) 72%, var(--border));
    border-radius: 999px;
    background: var(--accent);
    --annotate-action-text: #090b0d;
    box-shadow:
      0 12px 30px color-mix(in srgb, #000 35%, transparent),
      0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
  }

  .annotate-menu button {
    min-height: 36px;
    padding: 0 var(--space-4, 16px);
    border: 0;
    border-radius: 999px;
    background: var(--accent);
    color: var(--annotate-action-text);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .annotate-actions button {
    min-height: 32px;
    padding: 0 var(--space-3, 12px);
    border: 0;
    background: transparent;
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .annotate-menu button:hover,
  .annotate-menu button:focus-visible {
    color: var(--annotate-action-text);
    background: var(--accent);
    outline: 2px solid color-mix(in srgb, var(--accent) 54%, transparent);
    outline-offset: 3px;
    box-shadow: inset 0 0 0 999px color-mix(in srgb, #fff 12%, transparent);
  }

  .annotate-actions button:hover,
  .annotate-actions button:focus-visible {
    color: var(--bg);
    background: var(--accent);
    outline: none;
  }

  .annotate-dialog {
    position: fixed;
    z-index: 50;
    right: var(--space-6, 32px);
    bottom: var(--space-6, 32px);
    width: min(420px, calc(100vw - 32px));
    border: 1px solid var(--border);
    padding: var(--space-4, 16px);
    background: var(--surface-raised, var(--bg));
    box-shadow: 0 18px 46px color-mix(in srgb, #000 42%, transparent);
  }

  .annotate-quote {
    margin: 0 0 var(--space-3, 12px);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
  }

  .annotate-field,
  .annotate-checkbox {
    display: grid;
    gap: var(--space-2, 8px);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .annotate-field textarea {
    min-height: 96px;
    resize: vertical;
    border: 1px solid var(--border);
    padding: var(--space-3, 12px);
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
    text-transform: none;
    letter-spacing: normal;
  }

  .annotate-field textarea:disabled,
  .annotate-checkbox input:disabled,
  .annotate-actions button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .annotation-sync-error,
  .annotate-error {
    margin: var(--space-2, 8px) 0 0;
    color: var(--signal-danger, #c0392b);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
  }

  .annotate-checkbox {
    grid-template-columns: auto 1fr;
    align-items: center;
    margin-top: var(--space-3, 12px);
  }

  .annotate-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2, 8px);
    margin-top: var(--space-4, 16px);
  }

  /* Prose styles for rendered markdown */
  .prose :global(h1) {
    font-family: var(--font-display);
    font-size: var(--type-h1-size, 28px);
    font-weight: var(--type-h1-weight, 600);
    line-height: var(--type-h1-lh, 1.2);
    color: var(--text);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(h2) {
    font-family: var(--font-display);
    font-size: var(--type-h2-size, 20px);
    font-weight: var(--type-h2-weight, 600);
    line-height: var(--type-h2-lh, 1.3);
    color: var(--text);
    margin-top: var(--space-6, 32px);
    margin-bottom: var(--space-3, 12px);
  }

  .prose :global(h3) {
    font-family: var(--font-display);
    font-size: var(--type-h3-size, 17px);
    font-weight: var(--type-h3-weight, 600);
    line-height: var(--type-h3-lh, 1.35);
    color: var(--text);
    margin-top: var(--space-5, 24px);
    margin-bottom: var(--space-2, 8px);
  }

  .prose :global(p) {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
    color: var(--text);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(a) {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .prose :global(.annotation-source-highlight) {
    border-radius: 4px;
    outline: 2px solid var(--accent);
    outline-offset: 4px;
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    transition:
      background-color 180ms ease,
      outline-color 180ms ease;
  }

  .prose :global(.annotation-source-marked) {
    border-radius: 3px;
    background: linear-gradient(
      transparent 18%,
      color-mix(in srgb, #ffe66d 42%, var(--accent) 10%) 18%,
      color-mix(in srgb, #ffe66d 42%, var(--accent) 10%) 86%,
      transparent 86%
    );
    -webkit-box-decoration-break: clone;
    box-decoration-break: clone;
    cursor: pointer;
  }

  .prose :global(.annotation-source-marked:hover),
  .prose :global(.annotation-source-marked:focus-visible) {
    background: color-mix(in srgb, #ffe66d 30%, var(--accent) 10%);
    outline: 2px solid color-mix(in srgb, #ffe66d 70%, var(--accent));
    outline-offset: 2px;
  }

  .annotation-popover {
    position: fixed;
    z-index: 55;
    width: min(360px, calc(100vw - 32px));
    max-height: min(420px, calc(100vh - 32px));
    overflow: auto;
    border: 1px solid color-mix(in srgb, var(--accent) 52%, var(--border));
    border-radius: 8px;
    padding: var(--space-3, 12px);
    background: var(--surface-raised, var(--bg));
    color: var(--text);
    box-shadow: 0 18px 44px color-mix(in srgb, #000 42%, transparent);
  }

  .annotation-popover-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3, 12px);
    margin-bottom: var(--space-2, 8px);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    cursor: grab;
    touch-action: none;
    user-select: none;
  }

  .annotation-popover-header button {
    border: 0;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
  }

  .annotation-popover-list {
    display: grid;
    gap: var(--space-3, 12px);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .annotation-popover-list li {
    list-style: none;
  }

  .annotation-popover-quote,
  .annotation-popover-memo {
    margin: 0;
    font-family: var(--font-mono);
  }

  .annotation-popover-quote {
    color: var(--text-muted);
    font-size: var(--type-chrome-size, 13px);
  }

  .annotation-popover-memo {
    margin-top: var(--space-1, 4px);
    white-space: pre-wrap;
    color: var(--text);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
  }

  .annotation-popover-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2, 8px);
    margin-top: var(--space-2, 8px);
  }

  .annotation-popover-actions button {
    min-height: 28px;
    border: 1px solid var(--border);
    padding: 0 var(--space-2, 8px);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--type-chrome-sm-size, 11px);
    cursor: pointer;
  }

  .annotation-popover-actions button:not(:disabled):hover {
    border-color: var(--accent);
    color: var(--bg);
    background: var(--accent);
  }

  .annotation-popover-actions button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  :global([data-theme="light"]) .prose :global(.annotation-source-highlight) {
    background: color-mix(in srgb, var(--accent) 14%, #fff);
  }

  .note-tag-chip,
  .prose :global(a.note-tag-chip) {
    --chip-bg: hsl(var(--tag-hue) 42% 28% / 0.32);
    --chip-border: hsl(var(--tag-hue) 42% 46% / 0.68);
    --chip-text: hsl(var(--tag-hue) 58% 74%);
    display: inline-flex;
    align-items: center;
    min-height: 1.55em;
    padding: 0 0.68em;
    border: 1px solid var(--chip-border);
    border-radius: 999px;
    background: var(--chip-bg);
    color: var(--chip-text);
    font-family: var(--font-mono);
    font-size: 0.84em;
    font-weight: 600;
    line-height: 1;
    text-decoration: none;
    white-space: nowrap;
  }

  :global([data-theme="light"]) .note-tag-chip,
  :global([data-theme="light"]) .prose :global(a.note-tag-chip) {
    --chip-bg: hsl(var(--tag-hue) 72% 92% / 0.88);
    --chip-border: hsl(var(--tag-hue) 48% 43% / 0.58);
    --chip-text: hsl(var(--tag-hue) 58% 26%);
  }

  .note-meta-tag-chip {
    font-size: 12px;
  }

  .note-meta-tag-chip:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .note-meta-tag-chip:hover,
  .note-meta-tag-chip:focus-visible,
  .prose :global(a.note-tag-chip:hover),
  .prose :global(a.note-tag-chip:focus-visible) {
    color: hsl(var(--tag-hue) 66% 84%);
    border-color: hsl(var(--tag-hue) 48% 54% / 0.88);
    background: hsl(var(--tag-hue) 44% 32% / 0.42);
    outline: none;
  }

  :global([data-theme="light"]) .note-meta-tag-chip:hover,
  :global([data-theme="light"]) .note-meta-tag-chip:focus-visible,
  :global([data-theme="light"]) .prose :global(a.note-tag-chip:hover),
  :global([data-theme="light"]) .prose :global(a.note-tag-chip:focus-visible) {
    color: hsl(var(--tag-hue) 62% 20%);
    border-color: hsl(var(--tag-hue) 52% 35% / 0.76);
    background: hsl(var(--tag-hue) 76% 87% / 0.95);
  }

  .prose :global(.note-relation-chip) {
    display: inline-flex;
    align-items: center;
    min-height: 1.45em;
    padding: 0 0.52em;
    border: 1px solid color-mix(in srgb, var(--accent) 48%, var(--border));
    border-radius: 2px;
    background: color-mix(
      in srgb,
      var(--accent) 14%,
      var(--surface-raised, var(--bg))
    );
    color: color-mix(in srgb, var(--accent) 72%, var(--text) 28%);
    font-family: var(--font-mono);
    font-size: 0.8em;
    font-weight: 750;
    line-height: 1;
    white-space: nowrap;
    vertical-align: 0.08em;
    box-shadow: inset 0 -1px 0 color-mix(in srgb, #000 18%, transparent);
  }

  :global([data-theme="light"]) .prose :global(.note-relation-chip) {
    border-color: color-mix(in srgb, var(--accent) 48%, var(--border));
    background: color-mix(in srgb, var(--accent) 11%, #fff);
    color: color-mix(in srgb, var(--accent) 70%, #111827 30%);
    box-shadow: inset 0 -1px 0 color-mix(in srgb, #000 8%, transparent);
  }

  .prose :global(.note-bracket-highlight) {
    color: color-mix(in srgb, var(--accent) 76%, var(--text) 24%);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-bottom: 1px solid color-mix(in srgb, var(--accent) 38%, transparent);
    padding: 0 0.15em;
  }

  .prose :global(.note-task-state) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.28em;
    height: 1.28em;
    margin: 0 0.48em 0 0;
    padding: 0;
    border: 1px solid #6b7280;
    border-radius: 3px;
    background: #3f454d;
    color: #d7dbe0;
    font-family: var(--font-mono);
    font-size: 0.9em;
    font-weight: 800;
    line-height: 1;
    cursor: pointer;
    vertical-align: -0.12em;
  }

  .prose :global(.note-task-state:hover),
  .prose :global(.note-task-state:focus-visible) {
    outline: 2px solid color-mix(in srgb, var(--accent) 72%, transparent);
    outline-offset: 2px;
  }

  .prose :global(.note-task-state-wip) {
    border-color: #d8b84c;
    background: #f4df8b;
    color: #5d4a00;
  }

  .prose :global(.note-task-state-done) {
    border-color: #237a3b;
    background: #2f9d4c;
    color: #f5fff7;
  }

  .prose :global(.note-task-state-cancel) {
    border-color: #9c2f2f;
    background: #c94b4b;
    color: #fff5f5;
  }

  .prose :global(code) {
    font-family: var(--font-mono);
    font-size: 0.9em;
    background-color: var(--surface-raised, var(--bg));
    padding: 1px 4px;
  }

  .prose :global(pre) {
    font-family: var(--font-mono);
    font-size: 13px;
    background-color: var(--surface-raised, var(--bg));
    padding: var(--space-4, 16px);
    overflow-x: hidden;
    white-space: pre-wrap;
    margin-bottom: var(--space-4, 16px);
    border: 0;
  }

  .prose :global(pre code) {
    background: none;
    padding: 0;
  }

  .prose :global(blockquote) {
    --callout-bg: color-mix(
      in srgb,
      var(--surface-raised, var(--bg)) 82%,
      #000 18%
    );
    --callout-text: color-mix(
      in srgb,
      var(--text-muted) 76%,
      var(--text-faint) 24%
    );
    border: 1px solid color-mix(in srgb, var(--border) 76%, transparent);
    border-left: 3px solid color-mix(in srgb, var(--accent) 38%, var(--border));
    border-radius: 6px;
    padding: var(--space-3, 12px) var(--space-4, 16px);
    margin: 0 0 var(--space-4, 16px);
    background: var(--callout-bg);
    color: var(--callout-text);
    font-style: normal;
  }

  :global([data-theme="light"]) .prose :global(blockquote) {
    --callout-bg: color-mix(
      in srgb,
      var(--surface-raised, var(--bg)) 88%,
      var(--accent) 12%
    );
    --callout-text: color-mix(in srgb, var(--text-muted) 76%, var(--text) 24%);
  }

  .prose :global(blockquote p),
  .prose :global(blockquote li) {
    color: inherit;
  }

  @media (prefers-color-scheme: light) {
    :global(:root:not([data-theme="dark"])) .note-tag-chip,
    :global(:root:not([data-theme="dark"])) .prose :global(a.note-tag-chip) {
      --chip-bg: hsl(var(--tag-hue) 72% 92% / 0.88);
      --chip-border: hsl(var(--tag-hue) 48% 43% / 0.58);
      --chip-text: hsl(var(--tag-hue) 58% 26%);
    }

    :global(:root:not([data-theme="dark"])) .note-meta-tag-chip:hover,
    :global(:root:not([data-theme="dark"])) .note-meta-tag-chip:focus-visible,
    :global(:root:not([data-theme="dark"]))
      .prose
      :global(a.note-tag-chip:hover),
    :global(:root:not([data-theme="dark"]))
      .prose
      :global(a.note-tag-chip:focus-visible) {
      color: hsl(var(--tag-hue) 62% 20%);
      border-color: hsl(var(--tag-hue) 52% 35% / 0.76);
      background: hsl(var(--tag-hue) 76% 87% / 0.95);
    }

    :global(:root:not([data-theme="dark"])) .prose :global(blockquote) {
      --callout-bg: color-mix(
        in srgb,
        var(--surface-raised, var(--bg)) 88%,
        var(--accent) 12%
      );
      --callout-text: color-mix(
        in srgb,
        var(--text-muted) 76%,
        var(--text) 24%
      );
    }

    :global(:root:not([data-theme="dark"]))
      .prose
      :global(.note-relation-chip) {
      border-color: color-mix(in srgb, var(--accent) 48%, var(--border));
      background: color-mix(in srgb, var(--accent) 11%, #fff);
      color: color-mix(in srgb, var(--accent) 70%, #111827 30%);
      box-shadow: inset 0 -1px 0 color-mix(in srgb, #000 8%, transparent);
    }
  }

  .prose :global(blockquote p:last-child) {
    margin-bottom: 0;
  }

  .prose :global(ul),
  .prose :global(ol) {
    padding-left: var(--space-5, 24px);
    margin-bottom: var(--space-4, 16px);
  }

  .prose :global(li) {
    font-family: var(--font-mono);
    font-size: var(--type-body-size, 15px);
    line-height: var(--type-body-lh, 1.7);
    color: var(--text);
    list-style: disc;
  }

  .prose :global(ol li) {
    list-style: decimal;
  }

  .prose :global(hr) {
    border: none;
    border-top: 1px solid var(--border);
    margin: var(--space-6, 32px) 0;
  }

  .status {
    font-family: var(--font-mono);
    font-size: var(--type-chrome-size, 13px);
    color: var(--text-muted);
  }

  .status.error {
    color: #c0392b;
  }

  @media (max-width: 640px) {
    .mode-toggle {
      width: 100%;
    }

    .note-page {
      padding-right: var(--space-4, 16px);
      padding-left: var(--space-4, 16px);
    }
  }
</style>
