# pkm-webapp — Frontend architecture

## Stack

- **SvelteKit 2 + Svelte 5** with `@sveltejs/adapter-static` so the entire
  app builds to a static asset tree shipped inside the `pkm` Python wheel
  (under `pkm/web/static/`).
- **Vite 5** for dev / build.
- **CodeMirror 6** for the editor (modular packages).
- **TypeScript 5** strict.
- **Playwright 1.49** for end-to-end + a11y gates.
- **axe-core 4.10** + `@axe-core/playwright` for WCAG 2.1 AA assertions.

The frontend is single-tenant: it logs in with the setup password, then relies
on the daemon's HttpOnly `pkm_session` cookie for same-origin `/api/v1/*`
requests. The compatibility bearer token is not stored in browser storage.

## Directory layout

```text
web-frontend/
├── src/
│   ├── lib/
│   │   ├── editor/            # CodeMirror module assemblies
│   │   ├── api/               # small fetch wrappers for auth and JSON APIs
│   │   └── stores/            # svelte stores (vault, theme, palette)
│   ├── routes/                # SvelteKit pages (note, daily, search, graph)
│   └── app.html
├── static/                    # public assets (favicon, etc.)
├── tests/playwright/          # motion + a11y smoke gates
├── scripts/check-bundle-size.js
├── playwright.config.ts
├── svelte.config.js
└── vite.config.js
```

## CodeMirror 6 module list

The editor stack is composed of opt-in modules so the build stays under
budget. Each module is loaded via the editor assembly in `src/lib/editor/`:

| Module                | Purpose                                                            |
| --------------------- | ------------------------------------------------------------------ |
| `live-styling`        | Cursor-aware raw-vs-rendered markdown toggling per line.           |
| `slash`               | `/` menu for inserting headings, callouts, etc. (~30ms staggered). |
| `vim`                 | Optional Vim keybindings via `@replit/codemirror-vim`.             |
| `frontmatter-byline`  | Render the YAML frontmatter as a single styled byline.             |
| `wikilink-widget`     | `[[note-id]]` widget with hover-preview + click-to-open.           |
| `tag-pill`            | `#tag` widget rendered as a pill, click-to-filter.                 |
| `markdown-extensions` | GFM tables, strikethrough, task lists, etc.                        |
| `katex-lazy`          | Math rendering, lazy-loaded so initial bundle stays under cap.     |
| `admonitions`         | `> [!note]`-style callouts.                                        |
| `footnotes`           | Markdown footnote rendering + cross-link.                          |
| `checkboxes`          | Interactive `- [ ]` toggles bound to file mutations.               |

## Navigation surface

Cross-component navigation uses a single object on `window`:

```ts
declare global {
  interface Window {
    __pkmNav?: {
      open(noteId: string): void;
      openDaily(date?: string): void;
      openSearch(q?: string): void;
      openPalette(): void;
    };
  }
}
```

Components that need to drive navigation (CmdK, wikilink-widget,
slash-menu) call `window.__pkmNav?.open(...)` rather than passing
prop callbacks down arbitrary depth. The implementation is wired up
once at the top-level layout.

## Bundle budget

- **Cap** — 330 KB gzipped (JS+CSS), enforced by
  `scripts/check-bundle-size.js`.
- **Excludes** — anything under `dist/**/fonts/**` and `*.woff2`. Web fonts
  are subset, preloaded, and shipped separately for a much smaller hit on
  first paint.
- **Lineage** — 220 → 290 (slice 2, CM6) → 296 (slice 3, CmdK) → 330
  (slice 4, Maximalist + lazy KaTeX).

Run locally:

```bash
pnpm build
node scripts/check-bundle-size.js
```

The script prints a per-file breakdown sorted by size descending so any
budget overage is debuggable from a single `pnpm bundle:check` run.

## Theme tokens

The CSS theme is defined as custom properties on `:root` and switched by
toggling `document.documentElement.dataset.theme = 'light' | 'dark'`. The
Playwright fixture `tests/playwright/fixtures/theme.ts` injects this attr
before page scripts run so SSR has a stable initial paint.

| Group      | Tokens                                                                      |
| ---------- | --------------------------------------------------------------------------- |
| Accent     | `--accent`, `--accent-soft`, `--accent-on`                                  |
| Text       | `--text`, `--text-muted`, `--text-faint`, `--text-inverse`                  |
| Background | `--bg`, `--bg-muted`, `--bg-elevated`, `--bg-overlay`                       |
| Border     | `--border`, `--border-strong`                                               |
| Font       | `--font-sans`, `--font-serif`, `--font-mono`                                |
| Motion     | `--ease-out`, `--ease-in-out`, `--dur-fast` (120ms), `--dur-stagger` (30ms) |

The `--text-faint` token is intentionally low-contrast for raw-markdown
rendering on the focused line; the a11y suite checks both the cursor-on and
cursor-off states stay above WCAG AA.

## Quality gates

| Gate          | Command                                         | Threshold                                                                                                  |
| ------------- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Build         | `pnpm build`                                    | exits zero                                                                                                 |
| Unit coverage | `pnpm run test:unit:coverage`                   | 90% lines/statements/functions; branch coverage ratchets from 76% while Svelte/V8 branch debt is paid down |
| Bundle        | `pnpm bundle:check`                             | ≤ 330 KB gzipped                                                                                           |
| E2E motion    | `pnpm test:e2e tests/playwright/motion.spec.ts` | stagger 30±10ms, palette 120±20ms                                                                          |
| A11y          | `pnpm test:a11y`                                | zero AA violations on light + dark                                                                         |

CI and the release job run formatting, unit tests, the production build, the
bundle budget, and focused Playwright regressions covering retirement residue,
accessibility, graph navigation, route generation, and the command palette.
