import { describe, expect, it } from "vitest";
import {
  reconcileTextQuoteAnchor,
  renderedSourceRevision,
} from "$lib/annotations/text-anchor";

describe("text annotation re-anchoring", () => {
  it("treats an empty quote as missing without looping", () => {
    const result = reconcileTextQuoteAnchor(
      { kind: "text_quote", quote: "", occurrence: 0 },
      [{ text: "Any rendered body" }],
    );

    expect(result).toMatchObject({ status: "orphaned", reason: "missing" });
  });

  it("does not recover an empty versioned quote from unrelated context", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "",
        occurrence: 0,
        selector_version: 1,
        prefix: "Before ",
        suffix: " after.",
      },
      [{ text: "Before unrelated phrase after." }],
    );

    expect(result).toMatchObject({ status: "orphaned", reason: "missing" });
  });

  it("fingerprints normalized rendered source deterministically", () => {
    const targets = [
      { text: "Alpha body", headingPath: ["One"] },
      { text: "Beta body", headingPath: ["Two"] },
    ];

    const first = renderedSourceRevision(targets);
    const second = renderedSourceRevision(
      targets.map((target) => ({ ...target })),
    );
    const changed = renderedSourceRevision([
      targets[0],
      { text: "Beta revised", headingPath: ["Two"] },
    ]);

    expect(first).toMatch(/^fnv1a:[0-9a-f]{8}$/);
    expect(second).toBe(first);
    expect(changed).not.toBe(first);
    expect(
      renderedSourceRevision([
        { text: "Alpha body", headingPath: ["Changed"] },
        targets[1],
      ]),
    ).not.toBe(first);
  });

  it("recovers changed text at a rendered block boundary", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "old phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "",
        suffix: " after.",
        start: 0,
        end: 10,
      },
      [{ text: "revised phrase after." }],
    );

    expect(result).toMatchObject({
      status: "active",
      reason: "context",
      anchor: { quote: "revised phrase", prefix: "", suffix: " after." },
    });
  });

  it("does not promote context found under a different heading", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "old phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "Before ",
        suffix: " after.",
        start: 7,
        end: 17,
        heading_path: ["Original"],
      },
      [
        {
          text: "Before revised phrase after.",
          headingPath: ["Different"],
        },
      ],
    );

    expect(result).toMatchObject({
      status: "needs_review",
      reason: "ambiguous",
    });
  });

  it("flags partial surviving context for review instead of declaring it orphaned", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "old phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "Before ",
        suffix: " after.",
        start: 7,
        end: 17,
        heading_path: ["Introduction"],
      },
      [
        {
          text: "Before revised phrase with a changed ending.",
          headingPath: ["Introduction"],
        },
      ],
    );

    expect(result).toMatchObject({
      status: "needs_review",
      confidence: 0,
      reason: "ambiguous",
    });
  });

  it("re-anchors a changed quote between stable context in one rendered block", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "old phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "Before ",
        suffix: " after.",
        start: 7,
        end: 17,
        heading_path: ["Introduction"],
      },
      [
        {
          text: "Before revised phrase after.",
          headingPath: ["Introduction"],
        },
      ],
    );

    expect(result).toMatchObject({
      status: "active",
      reason: "context",
      targetIndex: 0,
      occurrenceInTarget: 0,
      anchor: {
        quote: "revised phrase",
        occurrence: 0,
        prefix: "Before ",
        suffix: " after.",
        start: 7,
        end: 21,
      },
    });
  });

  it("uses saved context when an inserted duplicate shifts the old occurrence", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "target phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "Before ",
        suffix: " after.",
        start: 7,
        end: 20,
        heading_path: ["Introduction"],
      },
      [
        {
          text: "New target phrase first. Before target phrase after.",
          headingPath: ["Introduction"],
        },
      ],
    );

    expect(result).toMatchObject({
      status: "active",
      reason: "exact",
      targetIndex: 0,
      occurrenceInTarget: 1,
      anchor: {
        quote: "target phrase",
        occurrence: 1,
        prefix: "New target phrase first. Before ",
        suffix: " after.",
      },
    });
  });

  it("does not bridge context across rendered blocks", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "old phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "Before ",
        suffix: " after.",
      },
      [{ text: "Before " }, { text: "revised phrase after." }],
    );

    expect(result).toMatchObject({
      status: "needs_review",
      reason: "ambiguous",
    });
  });

  it("marks a selector with no surviving evidence as orphaned", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "removed phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "old prefix",
        suffix: "old suffix",
        heading_path: ["Removed section"],
      },
      [{ text: "Completely unrelated content", headingPath: ["Current"] }],
    );

    expect(result).toMatchObject({ status: "orphaned", reason: "missing" });
  });

  it("keeps indistinguishable exact duplicates for manual review", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "same phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "missing prefix",
        suffix: "missing suffix",
      },
      [{ text: "same phrase and same phrase" }],
    );

    expect(result).toMatchObject({
      status: "needs_review",
      reason: "ambiguous",
    });
  });

  it("enriches a legacy anchor when its quote has one exact rendered match", () => {
    const result = reconcileTextQuoteAnchor(
      {
        kind: "text_quote",
        quote: "target phrase",
        occurrence: 0,
      },
      [
        {
          text: "Before target phrase after.",
          headingPath: ["Introduction"],
        },
      ],
    );

    expect(result).toMatchObject({
      status: "active",
      confidence: 1,
      reason: "exact",
      targetIndex: 0,
      occurrenceInTarget: 0,
      anchor: {
        kind: "text_quote",
        quote: "target phrase",
        occurrence: 0,
        selector_version: 1,
        prefix: "Before ",
        suffix: " after.",
        start: 7,
        end: 20,
        heading_path: ["Introduction"],
      },
    });
  });
});
