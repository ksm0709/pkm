# pkm-webapp — HTTP API reference

OpenAPI-style reference for `/api/v1/*` endpoints registered in
`cli/src/pkm/web/routes/__init__.py`. Browser clients authenticate by
password login and an HttpOnly session cookie. CLI/curl clients can still use
the compatibility bearer token; SSE routes additionally accept `?token=` for
`EventSource` clients.

- **Base URL** — `http://<bind>:<port>` (default `127.0.0.1:7420`).
- **Auth header** — `Authorization: Bearer <token>` from
  `~/.config/pkm/web-token`.
- **Browser auth** — `POST /api/v1/auth/login` with the setup password sets
  the `pkm_session` cookie.
- **Content type** — `application/json` for both requests and responses
  unless noted (SSE routes return `text/event-stream`).

## Common responses

| Status | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 400 | Bad request (malformed body, invalid params) |
| 401 | Missing/invalid auth |
| 404 | Vault or note not found |
| 409 | Note already exists (`POST /notes`) |
| 503 | Worker unavailable (`POST /ask`) |

---

## Auth

### `POST /api/v1/auth/login`

Public browser login endpoint.

- **Request body** — `{"password": string, "remember"?: boolean}`
- **Response 200** — `{"ok": true, "vaults": [{ "name": string, "path": string }, ...]}` plus an HttpOnly `pkm_session` cookie.
- **401** — invalid password.
- **503** — password login not configured.

### `POST /api/v1/auth/logout`

Clears the browser session cookie.

- **Response 200** — `{"ok": true}`

---

## Health

### `GET /api/v1/health`

Liveness probe.

- **Response 200** — `{"status": "ok"}`

---

## Vaults

### `GET /api/v1/vaults`

List configured vaults.

- **Response 200** — `[{ "name": string, "path": string }, ...]`

---

## Notes

### `GET /api/v1/vault/{name}/notes`

List notes in vault.

- **Response 200** — array of summaries:
  ```json
  [{"note_id": "...", "title": "...", "path": "...", "tags": [...], "created_at": "..."}]
  ```

### `GET /api/v1/vault/{name}/notes/{id}`

Fetch a single note.

- **Response 200** — 8-key schema:
  ```json
  {"note_id": "...", "title": "...", "body": "...", "frontmatter": {...},
   "created": "...", "updated": "...", "tags": [...], "importance": 0}
  ```
- **404** — note not found.

### `POST /api/v1/vault/{name}/notes`

Create a new note.

- **Request body** — `{"title": string (required), "body": string?, "tags": string[]?}`
- **Response 201** — 8-key note schema (see above).
- **400** — `title` missing.
- **409** — note already exists.

### `PUT /api/v1/vault/{name}/notes/{id}`

Update an existing note (body always; title/tags optional).

- **Request body** — `{"body": string?, "title": string?, "tags": string[]?}`
- **Response 200** — 8-key note schema.
- **404** — note not found.

### `GET /api/v1/vault/{name}/notes/{id}/neighbors`

Graph neighbors with semantic edges.

- **Response 200**:
  ```json
  {"note_id": "...",
   "outbound": [{"note_id": "...", "title": "...", "type": "note"}],
   "inbound":  [{...}],
   "semantic": [{"note_id": "...", "title": "...", "type": "note", "confidence": 0.83}]}
  ```
- **404** — vault unknown or graph not yet built (`pkm index` first).

### `POST /api/v1/vault/{name}/notes/batch-titles`

Resolve a batch of note IDs to titles.

- **Request body** — `{"ids": string[] (max 200)}`
- **Response 200** — `{ "<id>": "<title>" }`. Unresolved IDs map to `""`.
- **400** — `ids` not a list, or > 200 items.

---

## Data files

### `POST /api/v1/vault/{name}/data`

Upload one flat file into the vault `data/` directory. Upload filenames must be
single filenames, not nested paths; collisions are saved with numeric suffixes
such as `report-1.pdf`.

- **Request body** — `multipart/form-data` with a required `file` field.
- **Response 201**:
  ```json
  {
    "filename": "report.pdf",
    "href": "/api/v1/vault/main/data/report.pdf",
    "markdown": "[report.pdf](/api/v1/vault/main/data/report.pdf)",
    "size": 123,
    "content_type": "application/pdf"
  }
  ```
- **400** — missing file field, non-multipart request, or invalid filename.
- **409** — no collision-free filename could be allocated.

### `GET /api/v1/vault/{name}/data/{path}`

Download a file from the vault `data/` directory. `path` may be either a flat
filename or a nested relative path such as
`my-invest/reports/329180/2026-06-03/01_deep_research.md`.

- **Response 200** — raw file bytes.
- **400** — invalid data path, including absolute paths, backslashes, empty
  path components, `.`, `..`, or symlink escapes outside `data/`.
- **404** — data file not found.
- **Security** — active content such as HTML/SVG is served as an attachment with
  `X-Content-Type-Options: nosniff`; safe raster images may be displayed inline.

### `GET /{name}/data/{path}`

Compatibility route for browser-openable vault data links. It serves the same
files and enforces the same authentication, validation, and content-disposition
policy as the canonical API route above.

---

## Search

### `GET /api/v1/vault/{name}/search`

Full-text search.

- **Query params** — `q` (required), `limit` (default 50), `tag` (optional).
- **Response 200** — `[{"note_id": "...", "title": "...", "snippet": "...", "score": 0.0}]`
- **400** — missing `q`.

---

## Tags

### `GET /api/v1/vault/{name}/tags`

List tags with counts.

- **Response 200** — `[{"tag": "database", "count": 12}, ...]`

### `GET /api/v1/vault/{name}/tags/search`

Tag autocomplete.

- **Query params** — `q` (required), `limit` (default 10).
- **Response 200** — `[{"tag": "...", "count": 0}, ...]`

---

## Graph

### `GET /api/v1/vault/{name}/graph`

Full graph (nodes + edges).

- **Response 200** — `node_link_data` shape from networkx.
- **404** — graph not yet built.

### `GET /api/v1/vault/{name}/graph/ego/{note_id}`

Ego graph (depth-1 neighborhood + optional semantic).

- **Query params** — `depth` (default 1), `semantic` (`true`/`false`).
- **Response 200** — `node_link_data` shape limited to ego.

---

## Daily

### `GET /api/v1/vault/{name}/daily`

Paginated list of daily-note summaries (descending).

- **Query params** — `before` (`YYYY-MM-DD`, exclusive upper bound), `limit` (1–100, default 50).
- **Response 200** — `[{"date": "YYYY-MM-DD", "title": "...", "todo_count": 0, "snippet": "..."}]`

### `GET /api/v1/vault/{name}/daily/today`

Get (or create) today's daily note.

- **Response 200** — 8-key note schema.

### `POST /api/v1/vault/{name}/daily/today`

Append an entry or create a subnote.

- **Request body — entry** — `{"type": "entry", "content": "..."}`
- **Request body — subnote** — `{"type": "subnote", "title": "...", "content": "..."}`
- **Response 201 — entry** — `{"entry": "..."}`
- **Response 201 — subnote** — `{"note_id": "..."}`
- **400** — invalid `type` or empty `title`.

### `GET /api/v1/vault/{name}/daily/{date}`

Get a specific date's daily note.

- **Response 200** — 8-key note schema.
- **400** — `date` not `YYYY-MM-DD`.
- **404** — no daily note for that date.

---

## Ask (SSE)

### `POST /api/v1/vault/{name}/ask`

Stream an LLM ask using server-sent events.

- **Auth** — `Authorization: Bearer <token>` **or** `?token=<token>` query
  param (whitelisted for SSE clients that can't set headers).
- **Request body** — `{"query": string (required), "session_id"?: string}`
- **Response 200** — `Content-Type: text/event-stream`. Each worker chunk
  becomes one SSE event, named after `chunk.type`:
  - `event: tool_detail` → `{"name": "...", "arguments": {...}}`
  - `event: reasoning`   → `{"content": "..."}`
  - `event: content`     → `{"content": "..."}`
  - `event: result`      → `{"response": "..."}`  *(terminal on success)*
  - `event: error`       → `{"reason": "draining"}` *(terminal on drain)* or
                            `{"message": "..."}` *(terminal on worker error)*
- **400** — empty/missing `query`.
- **401** — missing auth.
- **503** — worker not yet attached to daemon.

The daemon emits keepalive comments every ~10s to keep proxies from
collapsing the stream and bumps `DaemonState.last_activity` so idle-shutdown
does not fire mid-ask.
