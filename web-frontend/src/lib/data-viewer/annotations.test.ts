import { describe, expect, it, vi, afterEach } from "vitest";
import { apiClient } from "$lib/api/client.js";
import {
  annotationsHref,
  loadDataAnnotations,
  saveDataAnnotations,
  type PdfAnnotationDocument,
} from "./annotations";

vi.mock("$lib/api/client.js", () => ({
  apiClient: vi.fn(),
}));

describe("PDF annotation client", () => {
  afterEach(() => {
    vi.mocked(apiClient).mockReset();
  });

  it("builds v2 annotation API hrefs with segment-wise encoding", () => {
    expect(annotationsHref("test vault", "reports/한글 report.pdf")).toBe(
      "/api/v1/vault/test%20vault/annotations/data/reports/%ED%95%9C%EA%B8%80%20report.pdf",
    );
    expect(annotationsHref("taeho", "reports/a%2Fb.pdf")).toBe(
      "/api/v1/vault/taeho/annotations/data/reports/a%252Fb.pdf",
    );
  });

  it("loads v2 PDF annotations and maps them to the viewer document shape", async () => {
    const v2Doc = {
      version: 2,
      source_key: "data:report.pdf",
      source: { kind: "data", path: "report.pdf" },
      annotations: [
        {
          id: "text-1",
          kind: "text",
          anchor: {
            kind: "pdf_text",
            quote: "selected words",
            rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          },
          comment: "note",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    };
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify(v2Doc), { status: 200 }),
    );

    await expect(loadDataAnnotations("taeho", "report.pdf")).resolves.toEqual({
      version: 1,
      source_path: "report.pdf",
      annotations: [
        {
          id: "text-1",
          type: "text",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          quote: "selected words",
          comment: "note",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    });
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/annotations/data/report.pdf",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("saves viewer PDF annotations as a v2 source-scoped sidecar document", async () => {
    const doc: PdfAnnotationDocument = {
      version: 1,
      source_path: "report.pdf",
      annotations: [
        {
          id: "area-1",
          type: "area",
          rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          comment: "note",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    };
    const savedV2 = {
      version: 2,
      source_key: "data:report.pdf",
      source: { kind: "data", path: "report.pdf" },
      annotations: [
        {
          id: "area-1",
          kind: "area",
          anchor: {
            kind: "pdf_rects",
            rects: [{ page: 1, x: 0.1, y: 0.2, width: 0.3, height: 0.4 }],
          },
          comment: "note",
          created_at: "2026-06-29T08:00:00Z",
          updated_at: "2026-06-29T08:00:00Z",
        },
      ],
    };
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify(savedV2), { status: 200 }),
    );

    await expect(
      saveDataAnnotations("taeho", "report.pdf", doc),
    ).resolves.toEqual(doc);
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/annotations/data/report.pdf",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(savedV2),
      }),
    );
  });

  it("throws useful errors on non-OK responses", async () => {
    vi.mocked(apiClient).mockResolvedValue(
      new Response("bad", { status: 400 }),
    );

    await expect(loadDataAnnotations("taeho", "bad.pdf")).rejects.toThrow(
      "GET PDF annotations → 400",
    );
  });
});
