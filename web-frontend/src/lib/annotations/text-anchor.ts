export type TextAnchorStatus = "active" | "needs_review" | "orphaned";

export interface TextQuoteAnchor {
  kind: "text_quote";
  quote: string;
  occurrence: number;
  selector_version?: 1;
  prefix?: string;
  suffix?: string;
  start?: number;
  end?: number;
  heading_path?: string[];
}

export interface TextAnchorTarget {
  text: string;
  headingPath?: string[];
}

export interface TextAnchorResolution {
  anchor: TextQuoteAnchor;
  status: TextAnchorStatus;
  confidence: number;
  reason: "exact" | "context" | "ambiguous" | "missing";
  targetIndex?: number;
  occurrenceInTarget?: number;
}

interface ExactMatch {
  globalOccurrence: number;
  targetIndex: number;
  occurrenceInTarget: number;
  startInTarget: number;
}

const CONTEXT_LENGTH = 48;

export function renderedSourceRevision(targets: TextAnchorTarget[]) {
  const source = targets
    .map(
      (target) =>
        `${(target.headingPath ?? []).join("\u001e")}\u001d${target.text}`,
    )
    .join("\u001f");
  let hash = 0x811c9dc5;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `fnv1a:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function exactMatches(quote: string, targets: TextAnchorTarget[]) {
  const matches: ExactMatch[] = [];
  if (!quote) return matches;
  let globalOccurrence = 0;
  targets.forEach((target, targetIndex) => {
    let from = 0;
    let occurrenceInTarget = 0;
    while (from <= target.text.length - quote.length) {
      const startInTarget = target.text.indexOf(quote, from);
      if (startInTarget < 0) break;
      matches.push({
        globalOccurrence,
        targetIndex,
        occurrenceInTarget,
        startInTarget,
      });
      globalOccurrence += 1;
      occurrenceInTarget += 1;
      from = startInTarget + quote.length;
    }
  });
  return matches;
}

function targetGlobalStart(targets: TextAnchorTarget[], targetIndex: number) {
  let start = 0;
  for (let index = 0; index < targetIndex; index += 1) {
    start += targets[index].text.length + 1;
  }
  return start;
}

function enrichedAnchor(
  anchor: TextQuoteAnchor,
  targets: TextAnchorTarget[],
  match: ExactMatch,
): TextQuoteAnchor {
  const target = targets[match.targetIndex];
  const start =
    targetGlobalStart(targets, match.targetIndex) + match.startInTarget;
  return {
    kind: "text_quote",
    quote: anchor.quote,
    occurrence: match.globalOccurrence,
    selector_version: 1,
    prefix: target.text.slice(
      Math.max(0, match.startInTarget - CONTEXT_LENGTH),
      match.startInTarget,
    ),
    suffix: target.text.slice(
      match.startInTarget + anchor.quote.length,
      match.startInTarget + anchor.quote.length + CONTEXT_LENGTH,
    ),
    start,
    end: start + anchor.quote.length,
    heading_path: [...(target.headingPath ?? [])],
  };
}

function commonSuffixRatio(saved: string | undefined, actual: string) {
  if (!saved) return 0;
  let matched = 0;
  while (
    matched < saved.length &&
    matched < actual.length &&
    saved[saved.length - 1 - matched] === actual[actual.length - 1 - matched]
  ) {
    matched += 1;
  }
  return matched / saved.length;
}

function commonPrefixRatio(saved: string | undefined, actual: string) {
  if (!saved) return 0;
  let matched = 0;
  while (
    matched < saved.length &&
    matched < actual.length &&
    saved[matched] === actual[matched]
  ) {
    matched += 1;
  }
  return matched / saved.length;
}

function sameHeading(
  saved: string[] | undefined,
  actual: string[] | undefined,
) {
  if (!saved?.length) return 0;
  const candidate = actual ?? [];
  return saved.length === candidate.length &&
    saved.every((heading, index) => heading === candidate[index])
    ? 1
    : 0;
}

function matchScore(
  anchor: TextQuoteAnchor,
  targets: TextAnchorTarget[],
  match: ExactMatch,
) {
  const target = targets[match.targetIndex];
  const actualPrefix = target.text.slice(
    Math.max(0, match.startInTarget - CONTEXT_LENGTH),
    match.startInTarget,
  );
  const actualSuffix = target.text.slice(
    match.startInTarget + anchor.quote.length,
    match.startInTarget + anchor.quote.length + CONTEXT_LENGTH,
  );
  const globalStart =
    targetGlobalStart(targets, match.targetIndex) + match.startInTarget;
  const sourceLength = targets.reduce(
    (total, item) => total + item.text.length + 1,
    0,
  );
  const positionScore =
    typeof anchor.start === "number"
      ? 1 -
        Math.min(
          1,
          Math.abs(globalStart - anchor.start) / Math.max(sourceLength, 1),
        )
      : 0;
  return (
    commonSuffixRatio(anchor.prefix, actualPrefix) * 0.4 +
    commonPrefixRatio(anchor.suffix, actualSuffix) * 0.4 +
    sameHeading(anchor.heading_path, target.headingPath) * 0.1 +
    positionScore * 0.1
  );
}

function chooseExactMatch(
  anchor: TextQuoteAnchor,
  targets: TextAnchorTarget[],
  matches: ExactMatch[],
) {
  if (matches.length === 0) return null;
  if (matches.length === 1) return { match: matches[0], confidence: 1 };
  const hasSelectors =
    anchor.selector_version === 1 &&
    Boolean(
      anchor.prefix ||
      anchor.suffix ||
      anchor.heading_path?.length ||
      typeof anchor.start === "number",
    );
  if (!hasSelectors) {
    const legacy = matches.find(
      (candidate) => candidate.globalOccurrence === anchor.occurrence,
    );
    return legacy ? { match: legacy, confidence: 0.75 } : null;
  }
  const ranked = matches
    .map((match) => ({ match, score: matchScore(anchor, targets, match) }))
    .sort((left, right) => right.score - left.score);
  const best = ranked[0];
  const runnerUp = ranked[1];
  if (best.score < 0.6 || best.score - runnerUp.score < 0.15) return null;
  return { match: best.match, confidence: best.score };
}

interface ContextMatch {
  quote: string;
  match: ExactMatch;
  confidence: number;
}

function allStarts(text: string, value: string) {
  if (value === "") return [0];
  const starts: number[] = [];
  let from = 0;
  while (from <= text.length - value.length) {
    const start = text.indexOf(value, from);
    if (start < 0) break;
    starts.push(start);
    from = start + value.length;
  }
  return starts;
}

function contextConfidence(
  anchor: TextQuoteAnchor,
  targets: TextAnchorTarget[],
  match: ExactMatch,
) {
  let confidence = 0.8;
  const target = targets[match.targetIndex];
  if (anchor.heading_path?.length) {
    confidence += sameHeading(anchor.heading_path, target.headingPath)
      ? 0.1
      : -0.4;
  }
  if (typeof anchor.start === "number") {
    const globalStart =
      targetGlobalStart(targets, match.targetIndex) + match.startInTarget;
    const sourceLength = targets.reduce(
      (total, item) => total + item.text.length + 1,
      0,
    );
    const positionWindow = Math.max(128, sourceLength * 0.25);
    if (Math.abs(globalStart - anchor.start) <= positionWindow)
      confidence += 0.1;
  }
  return Math.max(0, Math.min(1, confidence));
}

function contextMatches(anchor: TextQuoteAnchor, targets: TextAnchorTarget[]) {
  if (
    anchor.selector_version !== 1 ||
    anchor.prefix === undefined ||
    anchor.suffix === undefined
  ) {
    return [];
  }
  const candidates: ContextMatch[] = [];
  const maximumSpan = Math.min(512, Math.max(128, anchor.quote.length * 4));
  targets.forEach((target, targetIndex) => {
    const prefixStarts = allStarts(target.text, anchor.prefix!);
    for (const prefixStart of prefixStarts) {
      const quoteStart = prefixStart + anchor.prefix!.length;
      const suffixStarts =
        anchor.suffix === ""
          ? [target.text.length]
          : allStarts(target.text.slice(quoteStart), anchor.suffix!).map(
              (start) => quoteStart + start,
            );
      for (const suffixStart of suffixStarts) {
        if (
          suffixStart < quoteStart ||
          suffixStart - quoteStart > maximumSpan
        ) {
          continue;
        }
        const quote = target.text.slice(quoteStart, suffixStart);
        if (!quote) continue;
        const match = exactMatches(quote, targets).find(
          (candidate) =>
            candidate.targetIndex === targetIndex &&
            candidate.startInTarget === quoteStart,
        );
        if (!match) continue;
        candidates.push({
          quote,
          match,
          confidence: contextConfidence(anchor, targets, match),
        });
      }
    }
  });
  return candidates;
}

export function reconcileTextQuoteAnchor(
  anchor: TextQuoteAnchor,
  targets: TextAnchorTarget[],
): TextAnchorResolution {
  if (!anchor.quote.trim()) {
    return {
      anchor: { ...anchor },
      status: "orphaned",
      confidence: 0,
      reason: "missing",
    };
  }
  const matches = exactMatches(anchor.quote, targets);
  const choice = chooseExactMatch(anchor, targets, matches);
  if (choice) {
    return {
      anchor: enrichedAnchor(anchor, targets, choice.match),
      status: "active",
      confidence: choice.confidence,
      reason: "exact",
      targetIndex: choice.match.targetIndex,
      occurrenceInTarget: choice.match.occurrenceInTarget,
    };
  }
  if (matches.length > 0) {
    return {
      anchor: { ...anchor },
      status: "needs_review",
      confidence: 0,
      reason: "ambiguous",
    };
  }
  const contextual = contextMatches(anchor, targets).sort(
    (left, right) => right.confidence - left.confidence,
  );
  const bestContext = contextual[0];
  const nextContext = contextual[1];
  if (
    bestContext &&
    bestContext.confidence >= 0.75 &&
    (!nextContext || bestContext.confidence - nextContext.confidence >= 0.05)
  ) {
    const nextAnchor = { ...anchor, quote: bestContext.quote };
    return {
      anchor: enrichedAnchor(nextAnchor, targets, bestContext.match),
      status: "active",
      confidence: bestContext.confidence,
      reason: "context",
      targetIndex: bestContext.match.targetIndex,
      occurrenceInTarget: bestContext.match.occurrenceInTarget,
    };
  }
  if (contextual.length > 0) {
    return {
      anchor: { ...anchor },
      status: "needs_review",
      confidence: 0,
      reason: "ambiguous",
    };
  }
  const hasSurvivingContext =
    anchor.selector_version === 1 &&
    targets.some(
      (target) =>
        Boolean(anchor.prefix && target.text.includes(anchor.prefix)) ||
        Boolean(anchor.suffix && target.text.includes(anchor.suffix)) ||
        sameHeading(anchor.heading_path, target.headingPath) === 1,
    );
  if (hasSurvivingContext) {
    return {
      anchor: { ...anchor },
      status: "needs_review",
      confidence: 0,
      reason: "ambiguous",
    };
  }
  return {
    anchor: { ...anchor },
    status: "orphaned",
    confidence: 0,
    reason: "missing",
  };
}
