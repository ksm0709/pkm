import { describe, expect, it } from "vitest";
import {
  apiDataHref,
  dataFileKind,
  rawDownloadHref,
  rewriteRenderableDataLinkHref,
  viewerDataHref,
} from "./paths";

describe("data viewer path helpers", () => {
  it("builds canonical API and viewer hrefs with segment-wise encoding", () => {
    const path = "my-invest/reports/108490/2026-06-06/company page.html";

    expect(apiDataHref("test vault", path)).toBe(
      "/api/v1/vault/test%20vault/data/my-invest/reports/108490/2026-06-06/company%20page.html",
    );
    expect(viewerDataHref("test vault", path)).toBe(
      "/test%20vault/view-data/my-invest/reports/108490/2026-06-06/company%20page.html",
    );
    expect(rawDownloadHref("test vault", path)).toBe(
      "/api/v1/vault/test%20vault/data/my-invest/reports/108490/2026-06-06/company%20page.html",
    );
  });

  it("preserves literal percent-encoded filename segments", () => {
    expect(apiDataHref("taeho", "reports/a%2Fb.md")).toBe(
      "/api/v1/vault/taeho/data/reports/a%252Fb.md",
    );
    expect(viewerDataHref("taeho", "reports/a%2Fb.md")).toBe(
      "/taeho/view-data/reports/a%252Fb.md",
    );
    expect(
      rewriteRenderableDataLinkHref(
        "/api/v1/vault/taeho/data/reports/a%252Fb.md",
        "taeho",
      ),
    ).toBe("/taeho/view-data/reports/a%252Fb.md");
  });

  it("classifies renderable data files", () => {
    expect(dataFileKind("report.md")).toBe("markdown");
    expect(dataFileKind("report.markdown")).toBe("markdown");
    expect(dataFileKind("company.html")).toBe("html");
    expect(dataFileKind("company.htm")).toBe("html");
    expect(dataFileKind("report.pdf")).toBe("unsupported");
  });

  it("rewrites same-vault renderable data links to the viewer", () => {
    expect(rewriteRenderableDataLinkHref("/taeho/data/a/report.md", "taeho")).toBe(
      "/taeho/view-data/a/report.md",
    );
    expect(
      rewriteRenderableDataLinkHref(
        "/api/v1/vault/taeho/data/a/company%20page.html#summary",
        "taeho",
      ),
    ).toBe("/taeho/view-data/a/company%20page.html#summary");
  });

  it("does not rewrite non-renderable, cross-vault, or external links", () => {
    expect(rewriteRenderableDataLinkHref("/taeho/data/a/report.pdf", "taeho")).toBeNull();
    expect(rewriteRenderableDataLinkHref("/other/data/a/report.md", "taeho")).toBeNull();
    expect(
      rewriteRenderableDataLinkHref("https://example.com/taeho/data/a/report.md", "taeho"),
    ).toBeNull();
  });
});
