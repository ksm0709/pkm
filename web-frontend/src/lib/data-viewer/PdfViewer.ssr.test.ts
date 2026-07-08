import { describe, expect, it } from "vitest";
import { render } from "svelte/server";
import PdfViewer from "./PdfViewer.svelte";

describe("PdfViewer SSR", () => {
  it("renders a browser-only PDF shell without touching document during SSR", () => {
    expect(() =>
      render(PdfViewer, {
        props: { vault: "taeho", path: "reports/report.pdf" },
      }),
    ).not.toThrow();
  });
});
