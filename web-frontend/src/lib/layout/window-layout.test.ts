// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  DEFAULT_WINDOW_PADDING,
  applyWindowLayoutVars,
  clearWindowLayoutVars,
  parseWindowPadding,
  windowLayoutVars,
} from "./window-layout";

describe("window layout vars", () => {
  it("parses configured window padding with safe fallback", () => {
    expect(parseWindowPadding("0")).toBe(0);
    expect(parseWindowPadding("32")).toBe(32);
    expect(parseWindowPadding("128")).toBe(128);
    expect(parseWindowPadding("-1")).toBe(DEFAULT_WINDOW_PADDING);
    expect(parseWindowPadding("129")).toBe(DEFAULT_WINDOW_PADDING);
    expect(parseWindowPadding("1.5")).toBe(DEFAULT_WINDOW_PADDING);
    expect(parseWindowPadding("abc")).toBe(DEFAULT_WINDOW_PADDING);
  });

  it("builds the shared page and modal width formulas", () => {
    const vars = windowLayoutVars({ contentInlineSize: 1000, paddingPx: 48 });

    expect(vars["--window-padding-raw"]).toBe("48px");
    expect(vars["--window-padding"]).toBe(
      "clamp(0px, var(--window-padding-raw), 128px)",
    );
    expect(vars["--vault-content-inline-size"]).toBe("1000px");
    expect(vars["--content-available-width"]).toContain(
      "var(--vault-content-inline-size)",
    );
    expect(vars["--page-content-width"]).toBe(
      "min(var(--page-max-width), var(--content-available-width))",
    );
    expect(vars["--readable-content-width"]).toBe(
      "min(var(--readable-max-width), var(--content-available-width))",
    );
    expect(vars["--modal-available-width"]).toBe(
      "var(--content-available-width)",
    );
  });

  it("applies and clears root style variables", () => {
    const root = document.createElement("div");
    applyWindowLayoutVars(
      root,
      windowLayoutVars({ contentInlineSize: 800, paddingPx: 64 }),
    );

    expect(root.style.getPropertyValue("--window-padding-raw")).toBe("64px");
    expect(root.style.getPropertyValue("--vault-content-inline-size")).toBe(
      "800px",
    );

    clearWindowLayoutVars(root);
    expect(root.style.getPropertyValue("--window-padding-raw")).toBe("");
    expect(root.style.getPropertyValue("--vault-content-inline-size")).toBe("");
  });
});
