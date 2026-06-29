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

export function annotationsHref(vault: string, path: string) {
  return `/api/v1/vault/${encodeURIComponent(vault)}/data-annotations/${encodeDataPathForUrl(path)}`;
}

async function parseAnnotationResponse(
  response: Response,
  action: "GET" | "PUT",
): Promise<PdfAnnotationDocument> {
  if (!response.ok) {
    throw new Error(`${action} PDF annotations → ${response.status}`);
  }
  return response.json() as Promise<PdfAnnotationDocument>;
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
    body: JSON.stringify(document),
  });
  return parseAnnotationResponse(response, "PUT");
}
