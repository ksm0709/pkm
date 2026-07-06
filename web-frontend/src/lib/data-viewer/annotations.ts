import { apiClient } from "$lib/api/client.js";
import { encodeDataPathForUrl } from "./paths";

export interface PdfAnnotationRect {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export type PdfAnnotationType = "area" | "text";

export interface PdfAnnotation {
  id: string;
  type: PdfAnnotationType;
  rects: PdfAnnotationRect[];
  comment: string;
  created_at: string;
  updated_at: string;
  quote?: string;
}

export interface PdfAnnotationDocument {
  version: 1;
  source_path: string;
  annotations: PdfAnnotation[];
}

type PdfAnnotationAnchorKind = "pdf_rects" | "pdf_text";

interface PdfAnnotationAnchorV2 {
  kind: PdfAnnotationAnchorKind;
  rects: PdfAnnotationRect[];
  quote?: string;
}

interface PdfAnnotationV2 {
  id: string;
  kind: PdfAnnotationType;
  anchor: PdfAnnotationAnchorV2;
  comment: string;
  created_at: string;
  updated_at: string;
}

interface PdfAnnotationDocumentV2 {
  version: 2;
  source_key: string;
  source: { kind: "data"; path: string };
  annotations: PdfAnnotationV2[];
}

export function annotationsHref(vault: string, path: string) {
  return `/api/v1/vault/${encodeURIComponent(vault)}/annotations/data/${encodeDataPathForUrl(path)}`;
}

function annotationToV2(annotation: PdfAnnotation): PdfAnnotationV2 {
  const anchor: PdfAnnotationAnchorV2 = {
    kind: annotation.type === "text" ? "pdf_text" : "pdf_rects",
    rects: annotation.rects,
  };
  if (annotation.type === "text" && annotation.quote) {
    anchor.quote = annotation.quote;
  }
  return {
    id: annotation.id,
    kind: annotation.type,
    anchor,
    comment: annotation.comment ?? "",
    created_at: annotation.created_at,
    updated_at: annotation.updated_at,
  };
}

function annotationFromV2(annotation: PdfAnnotationV2): PdfAnnotation {
  return {
    id: annotation.id,
    type: annotation.kind,
    rects: annotation.anchor.rects,
    quote: annotation.anchor.quote,
    comment: annotation.comment ?? "",
    created_at: annotation.created_at,
    updated_at: annotation.updated_at,
  };
}

function documentToV2(
  path: string,
  document: PdfAnnotationDocument,
): PdfAnnotationDocumentV2 {
  return {
    version: 2,
    source_key: `data:${path}`,
    source: { kind: "data", path },
    annotations: document.annotations.map(annotationToV2),
  };
}

function documentFromV2(
  document: PdfAnnotationDocumentV2,
): PdfAnnotationDocument {
  return {
    version: 1,
    source_path: document.source.path,
    annotations: document.annotations.map(annotationFromV2),
  };
}

async function parseAnnotationResponse(
  response: Response,
  action: "GET" | "PUT",
): Promise<PdfAnnotationDocument> {
  if (!response.ok) {
    throw new Error(`${action} PDF annotations → ${response.status}`);
  }
  return documentFromV2((await response.json()) as PdfAnnotationDocumentV2);
}

export async function loadDataAnnotations(vault: string, path: string) {
  const response = await apiClient(annotationsHref(vault, path), {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  return parseAnnotationResponse(response, "GET");
}

export async function saveDataAnnotations(
  vault: string,
  path: string,
  document: PdfAnnotationDocument,
) {
  const response = await apiClient(annotationsHref(vault, path), {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(documentToV2(path, document)),
  });
  return parseAnnotationResponse(response, "PUT");
}
