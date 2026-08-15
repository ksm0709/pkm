# pkm-webapp — HTTP API reference

OpenAPI-style reference for `/api/v1/*` endpoints registered in
`cli/src/pkm/web/routes/__init__.py`. Browser clients authenticate by
password login and an HttpOnly session cookie. CLI/curl clients can still use
the compatibility bearer token. Credentials in URL query parameters are
rejected; browser clients must use the session cookie and non-browser clients
must use the bearer header.

- **Base URL** — `http://<bind>:<port>` (default `127.0.0.1:7420`).
- **Auth header** — `Authorization: Bearer <token>` from
  `~/.config/pkm/web-token`.
- **Browser auth** — `POST /api/v1/auth/login` with the setup password sets
  the `pkm_session` cookie.
- **Content type** — `application/json` for both requests and responses unless
  a file endpoint documents a binary response.

## Common responses

| Status | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 400 | Bad request (malformed body, invalid params) |
| 401 | Missing/invalid auth |
| 404 | Vault or note not found |
| 409 | Conflict (for example, note exists or annotation changed concurrently) |

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

- **Response 200** — 9-key schema. `content_hash` is a SHA-256 revision of the
  parsed Markdown body and is used as the note-side precondition for annotation
  reconciliation:
  ```json
  {"note_id": "...", "title": "...", "body": "...", "content_hash": "sha256:...", "frontmatter": {...},
   "created": "...", "updated": "...", "tags": [...], "importance": 0}
  ```
- **404** — note not found.

### `POST /api/v1/vault/{name}/notes`

Create a new note.

- **Request body** — `{"title": string (required), "body": string?, "tags": string[]?}`
- **Response 201** — 9-key note schema (see above).
- **400** — `title` missing.
- **409** — note already exists.

### `PUT /api/v1/vault/{name}/notes/{id}`

Update an existing note (body always; title/tags optional). The request must
include `If-Match: "sha256:..."` using the `content_hash` returned by the latest
note GET. Note writes and annotation re-anchor PATCHes share the same lifecycle
lock, so note hash validation and sidecar mutation cannot interleave.

- **Request body** — `{"body": string?, "title": string?, "tags": string[]?}`
- **Response 200** — 9-key note schema and the new content hash as `ETag`.
- **409** — a stale client attempts to reintroduce the retired legacy
  `## Annotations` section after sidecar cutover.
- **412** — `If-Match` does not match the current note body.
- **428** — `If-Match` is missing.
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

## Note annotations

Note annotations are stored in unified v2 sidecars. Reading a note with only a
legacy Markdown `## Annotations` section adapts it in memory without writing;
only an explicit user PUT carrying the current `legacy_revision` persists the
v2 sidecar. Automatic re-anchor PATCH is rejected for a legacy projection, so a
background read cannot silently cut over storage or miss later Markdown edits.

A text anchor keeps the compatible `quote` and `occurrence` fields and may add
rendered-text selector fields:

```json
{
  "kind": "text_quote",
  "quote": "multi-version concurrency control",
  "occurrence": 0,
  "selector_version": 1,
  "prefix": "uses ",
  "suffix": " for readers",
  "start": 12,
  "end": 45,
  "heading_path": ["Overview"]
}
```

Annotation `status` is `active`, `needs_review`, or `orphaned`. A source edit
never implies that a comment is resolved: exact/context matches remain active,
ambiguous matches need review, and anchors with no surviving evidence become
orphaned. `reanchor` records `confidence` and the reason (`exact`, `context`,
`ambiguous`, or `missing`). The document-level `source_revision` is an
`fnv1a:<8 hex digits>` change detector for normalized rendered source; it is
not a cryptographic integrity value.

### `GET /api/v1/vault/{name}/annotations/note/{id}`

Read the v2 annotation document or an in-memory legacy projection. GET is
side-effect free. The response includes `annotation_revision`, `storage_mode`
(`none`, `legacy`, or `v2`), and `legacy_revision` for legacy projections, and
returns the annotation revision as an `ETag`.

### `PUT /api/v1/vault/{name}/annotations/note/{id}`

Submit the complete set of note annotations. New clients send `base_revision`
and matching `If-Match`. IDs must be unique; rich text selectors, status,
re-anchor metadata, and source revision are validated. Retained IDs are merged
losslessly with the current record, so an older client's narrow
`quote`/`occurrence` payload cannot erase rich selectors, timestamps, status, or
unknown extension fields. **Deletion requires CAS**: a request with
`base_revision` may delete omitted IDs, while a compatibility request without a
base revision is lossless upsert-only and preserves omitted siblings. A legacy
projection also requires the exact `legacy_revision` returned by GET. Successful
legacy migration writes the sidecar and removes the reserved Markdown
`## Annotations` section under the same note lifecycle lock; subsequent stale
note PUTs that reintroduce that section are rejected.

### `PATCH /api/v1/vault/{name}/annotations/note/{id}`

Merge automatic re-anchor results by annotation ID, preserving every sibling
annotation not named in `updates`.

- **Request body**:
  ```json
  {
    "base_revision": 7,
    "base_note_revision": "sha256:...",
    "source_revision": "fnv1a:1234abcd",
    "updates": [
      {
        "id": "note-ann-1",
        "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
        "status": "active",
        "reanchor": {"confidence": 1, "reason": "exact"}
      }
    ]
  }
  ```
- **Response 200** — the complete merged v2 annotation document.
- **400** — malformed revision, selector, status, or metadata.
- **412** — `If-Match` disagrees with `base_revision`.
- **409** — stale annotation revision, stale note body revision, legacy storage,
  or an update ID that no longer exists; the client must reload rather than
  overwrite a concurrent change or recreate a deleted annotation.

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

Browser-openable vault data links. It enforces the same authentication and path
validation as the canonical API route. Renderable text formats (`.md`,
`.markdown`, `.html`, `.htm`) redirect to the in-app safe viewer at
`/{name}/view-data/{path}` so users can read reports without downloading them.
Other file types keep the API content-disposition policy: raster images may open
inline, while active/unknown content downloads as an attachment.

### `GET /{name}/view-data/{path}`

SPA route for safe data previews. The frontend fetches the raw bytes through the
canonical API route using the current authenticated session, renders Markdown
with the normal note renderer, sanitizes HTML before display, and exposes a
"Download raw" link back to `/api/v1/vault/{name}/data/{path}`.

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

- **Response 200** — 9-key note schema.

### `POST /api/v1/vault/{name}/daily/today`

Append an entry or create a subnote.

- **Request body — entry** — `{"type": "entry", "content": "..."}`
- **Request body — subnote** — `{"type": "subnote", "title": "...", "content": "..."}`
- **Response 201 — entry** — `{"entry": "..."}`
- **Response 201 — subnote** — `{"note_id": "..."}`
- **400** — invalid `type` or empty `title`.

### `GET /api/v1/vault/{name}/daily/{date}`

Get a specific date's daily note.

- **Response 200** — 9-key note schema.
- **400** — `date` not `YYYY-MM-DD`.
- **404** — no daily note for that date.

---

## Feedback

Feedback stays in the selected vault: every submission creates a tagged daily
subnote and adds its wikilink to today's daily log. When SMTP is configured,
the same record is also emailed to `ksm07091@gmail.com` by default.

### `GET /api/v1/vault/{name}/feedback`

List all feedback records, newest first.

- **Response 200** — `[{
  "note_id": "...", "title": "...", "description": "...",
  "feedback_type": "requirement|bug|idea", "created_at": "..."
  }]`

### `POST /api/v1/vault/{name}/feedback`

Create a feedback record.

- **Request body** — `{"title": string, "description": string, "feedback_type"?: "requirement"|"bug"|"idea"}`
- **Response 201** — the created feedback record plus `email_status`
  (`sent`, `not_configured`, or `failed`). The record is retained in the vault
  even when delivery cannot be attempted or fails.
- **400** — invalid JSON, missing/invalid fields, title longer than 120 characters, or description longer than 8,000 characters.
- **403** — a session-authenticated request is not same-origin.

### Feedback email delivery

The web service reads SMTP settings from its environment. The recipient is
`ksm07091@gmail.com` unless `PKM_FEEDBACK_EMAIL_TO` overrides it.

```ini
PKM_FEEDBACK_SMTP_HOST=smtp.gmail.com
PKM_FEEDBACK_SMTP_PORT=587
PKM_FEEDBACK_SMTP_USERNAME=ksm07091@gmail.com
PKM_FEEDBACK_SMTP_PASSWORD=<Google app password>
PKM_FEEDBACK_EMAIL_FROM=ksm07091@gmail.com
PKM_FEEDBACK_SMTP_STARTTLS=true
```

For implicit TLS on port 465, set `PKM_FEEDBACK_SMTP_USE_SSL=true` instead of
STARTTLS. Store credentials in a mode-`0600` systemd `EnvironmentFile`, then
restart `pkm-web`; never place the password in the vault or browser code.
