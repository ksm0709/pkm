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

  it("builds annotation API hrefs with segment-wise encoding", () => {
    expect(annotationsHref("test vault", "reports/한글 report.pdf")).toBe(
      "/api/v1/vault/test%20vault/data-annotations/reports/%ED%95%9C%EA%B8%80%20report.pdf",
    );
    expect(annotationsHref("taeho", "reports/a%2Fb.pdf")).toBe(
      "/api/v1/vault/taeho/data-annotations/reports/a%252Fb.pdf",
    );
  });

  it("loads PDF annotations through apiClient", async () => {
    const doc: PdfAnnotationDocument = {
      version: 1,
      source_path: "report.pdf",
      annotations: [],
    };
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify(doc), { status: 200 }),
    );

    await expect(loadDataAnnotations("taeho", "report.pdf")).resolves.toEqual(
      doc,
    );
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/data-annotations/report.pdf",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("saves PDF annotations as a whole sidecar document", async () => {
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
    vi.mocked(apiClient).mockResolvedValue(
      new Response(JSON.stringify(doc), { status: 200 }),
    );

    await expect(
      saveDataAnnotations("taeho", "report.pdf", doc),
    ).resolves.toEqual(doc);
    expect(apiClient).toHaveBeenCalledWith(
      "/api/v1/vault/taeho/data-annotations/report.pdf",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(doc),
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
