export type DataFileKind = "markdown" | "html" | "unsupported";

const markdownExtensions = new Set([".md", ".markdown"]);
const htmlExtensions = new Set([".html", ".htm"]);

function safeDecodeURIComponent(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function stripQueryAndHash(value: string) {
  const hashIndex = value.indexOf("#");
  const withoutHash = hashIndex >= 0 ? value.slice(0, hashIndex) : value;
  const hash = hashIndex >= 0 ? value.slice(hashIndex) : "";
  const queryIndex = withoutHash.indexOf("?");
  return {
    path: queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash,
    hash,
  };
}

function extensionOf(path: string) {
  const { path: cleanPath } = stripQueryAndHash(path);
  const decoded = safeDecodeURIComponent(cleanPath);
  const basename = decoded.split("/").pop() ?? "";
  const dotIndex = basename.lastIndexOf(".");
  if (dotIndex < 0) return "";
  return basename.slice(dotIndex).toLowerCase();
}

export function dataFileKind(path: string): DataFileKind {
  const extension = extensionOf(path);
  if (markdownExtensions.has(extension)) return "markdown";
  if (htmlExtensions.has(extension)) return "html";
  return "unsupported";
}

export function encodeDataPathForUrl(path: string) {
  return path
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
}

function decodeHrefDataPath(path: string) {
  return path
    .split("/")
    .map((part) => safeDecodeURIComponent(part))
    .join("/");
}

export function apiDataHref(vault: string, path: string) {
  return `/api/v1/vault/${encodeURIComponent(vault)}/data/${encodeDataPathForUrl(path)}`;
}

export function rawDownloadHref(vault: string, path: string) {
  return apiDataHref(vault, path);
}

export function viewerDataHref(vault: string, path: string) {
  return `/${encodeURIComponent(vault)}/view-data/${encodeDataPathForUrl(path)}`;
}

function sameVault(encodedVault: string, currentVault: string) {
  return safeDecodeURIComponent(encodedVault) === currentVault;
}

export function rewriteRenderableDataLinkHref(
  href: string,
  currentVault: string,
): string | null {
  const trimmed = href.trim();
  if (!trimmed.startsWith("/")) return null;

  const { path, hash } = stripQueryAndHash(trimmed);
  const apiMatch = path.match(/^\/api\/v1\/vault\/([^/]+)\/data\/(.+)$/);
  if (apiMatch) {
    const [, encodedVault, dataPath] = apiMatch;
    if (!sameVault(encodedVault, currentVault)) return null;
    if (dataFileKind(dataPath) === "unsupported") return null;
    return `${viewerDataHref(currentVault, decodeHrefDataPath(dataPath))}${hash}`;
  }

  const humanMatch = path.match(/^\/([^/]+)\/data\/(.+)$/);
  if (!humanMatch) return null;
  const [, encodedVault, dataPath] = humanMatch;
  if (!sameVault(encodedVault, currentVault)) return null;
  if (dataFileKind(dataPath) === "unsupported") return null;
  return `${viewerDataHref(currentVault, decodeHrefDataPath(dataPath))}${hash}`;
}
