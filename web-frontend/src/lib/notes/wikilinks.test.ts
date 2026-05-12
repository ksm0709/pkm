import { describe, expect, it } from "vitest";
import { wikilinksToMarkdownLinks } from "./wikilinks";

describe("markdown wikilink conversion", () => {
  it("converts wikilinks whose target contains literal brackets", () => {
    const markdown =
      "See [[2026-04-14-[주식분석]-두산에너빌리티]] and [[[주식분석]xxx|alias]].";

    expect(wikilinksToMarkdownLinks(markdown, "main")).toBe(
      "See [2026-04-14-\\[주식분석\\]-두산에너빌리티](/main/notes/2026-04-14-%5B%EC%A3%BC%EC%8B%9D%EB%B6%84%EC%84%9D%5D-%EB%91%90%EC%82%B0%EC%97%90%EB%84%88%EB%B9%8C%EB%A6%AC%ED%8B%B0) and [alias](/main/notes/%5B%EC%A3%BC%EC%8B%9D%EB%B6%84%EC%84%9D%5Dxxx).",
    );
  });

  it("leaves embeds and code segments unchanged", () => {
    const markdown = [
      "![[2026-04-14-[주식분석]-두산에너빌리티]]",
      "`[[inline-[raw]]]`",
      "```",
      "[[fenced-[raw]]]",
      "```",
    ].join("\n");

    expect(wikilinksToMarkdownLinks(markdown, "main")).toBe(markdown);
  });
});
