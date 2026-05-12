export const DEFAULT_WINDOW_PADDING = 32;
export const MIN_WINDOW_PADDING = 0;
export const MAX_WINDOW_PADDING = 128;

export const WINDOW_LAYOUT_VAR_NAMES = [
  "--window-padding-raw",
  "--window-padding",
  "--vault-content-inline-size",
  "--content-available-width",
  "--page-max-width",
  "--readable-max-width",
  "--page-content-width",
  "--readable-content-width",
  "--modal-available-width",
] as const;

export function parseWindowPadding(
  value: unknown,
  fallback = DEFAULT_WINDOW_PADDING,
) {
  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) return fallback;
  const parsed = Number(text);
  if (
    !Number.isInteger(parsed) ||
    parsed < MIN_WINDOW_PADDING ||
    parsed > MAX_WINDOW_PADDING
  ) {
    return fallback;
  }
  return parsed;
}

export function windowLayoutVars({
  contentInlineSize,
  paddingPx,
}: {
  contentInlineSize: number;
  paddingPx: number;
}) {
  const safeContentInlineSize = Math.max(0, Math.round(contentInlineSize));
  const safePadding = parseWindowPadding(paddingPx);
  return {
    "--window-padding-raw": `${safePadding}px`,
    "--window-padding": "clamp(0px, var(--window-padding-raw), 128px)",
    "--vault-content-inline-size": `${safeContentInlineSize}px`,
    "--content-available-width":
      "max(0px, calc(var(--vault-content-inline-size) - var(--window-padding) - var(--window-padding)))",
    "--page-max-width": "1180px",
    "--readable-max-width": "860px",
    "--page-content-width":
      "min(var(--page-max-width), var(--content-available-width))",
    "--readable-content-width":
      "min(var(--readable-max-width), var(--content-available-width))",
    "--modal-available-width": "var(--content-available-width)",
  } satisfies Record<(typeof WINDOW_LAYOUT_VAR_NAMES)[number], string>;
}

export function applyWindowLayoutVars(
  root: HTMLElement,
  vars: ReturnType<typeof windowLayoutVars>,
) {
  for (const [name, value] of Object.entries(vars)) {
    root.style.setProperty(name, value);
  }
}

export function clearWindowLayoutVars(root: HTMLElement) {
  for (const name of WINDOW_LAYOUT_VAR_NAMES) {
    root.style.removeProperty(name);
  }
}
