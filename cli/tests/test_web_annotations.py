"""Integration tests for unified web annotation routes."""

from __future__ import annotations

from hashlib import sha256

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-annotations-token"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7422, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.mark.anyio
async def test_get_data_annotations_v2_returns_empty_document_for_existing_pdf(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "report.pdf").write_bytes(b"pdf")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/annotations/data/report.pdf",
            headers=auth(),
        )
        payload = await resp.json()

    assert resp.status == 200
    assert payload == {
        "version": 2,
        "source_key": "data:report.pdf",
        "source": {"kind": "data", "path": "report.pdf"},
        "annotations": [],
    }


@pytest.mark.anyio
async def test_put_data_annotations_v2_writes_per_data_source_sidecar_only(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "reports" / "한글 report.pdf"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"pdf")
    document = {
        "source_key": "client-supplied-wrong-key",
        "source": {"kind": "data", "path": "wrong.pdf"},
        "annotations": [
            {
                "id": "text-1",
                "kind": "text",
                "anchor": {
                    "kind": "pdf_text",
                    "quote": "selected words",
                    "rects": [
                        {"page": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
                    ],
                },
                "comment": "note",
                "created_at": "2026-07-06T10:00:00Z",
                "updated_at": "2026-07-06T10:00:00Z",
            }
        ],
    }

    async with TestClient(TestServer(app)) as client:
        put_resp = await client.put(
            "/api/v1/vault/test-vault/annotations/data/reports/%ED%95%9C%EA%B8%80%20report.pdf",
            json=document,
            headers=auth(),
        )
        saved = await put_resp.json()
        get_resp = await client.get(
            "/api/v1/vault/test-vault/annotations/data/reports/%ED%95%9C%EA%B8%80%20report.pdf",
            headers=auth(),
        )
        loaded = await get_resp.json()

    assert put_resp.status == 200
    assert get_resp.status == 200
    assert saved == loaded
    assert saved["version"] == 2
    assert saved["source_key"] == "data:reports/한글 report.pdf"
    assert saved["source"] == {"kind": "data", "path": "reports/한글 report.pdf"}
    assert saved["annotations"] == document["annotations"]
    v2_name = (
        sha256("data:reports/한글 report.pdf".encode("utf-8")).hexdigest() + ".json"
    )
    v1_name = sha256("reports/한글 report.pdf".encode("utf-8")).hexdigest() + ".json"
    assert (tmp_vault.path / ".pkm" / "annotations" / "data" / v2_name).is_file()
    assert not (tmp_vault.path / ".pkm" / "annotations" / "all.json").exists()
    assert not (tmp_vault.path / ".pkm" / "data-annotations" / v1_name).exists()


@pytest.mark.anyio
async def test_data_annotations_v2_preserves_legacy_pdf_annotation_endpoint_schema(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "report.pdf").write_bytes(b"pdf")

    async with TestClient(TestServer(app)) as client:
        legacy_resp = await client.get(
            "/api/v1/vault/test-vault/data-annotations/report.pdf",
            headers=auth(),
        )
        legacy_payload = await legacy_resp.json()

    assert legacy_resp.status == 200
    assert legacy_payload == {
        "version": 1,
        "source_path": "report.pdf",
        "annotations": [],
    }


@pytest.mark.anyio
async def test_data_annotations_v2_reads_legacy_v1_sidecar_without_migrating_on_get(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "report.pdf").write_bytes(b"pdf")
    legacy_doc = {
        "annotations": [
            {
                "id": "legacy-text",
                "type": "text",
                "rects": [{"page": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}],
                "quote": "legacy quote",
                "comment": "legacy note",
                "created_at": "2026-07-06T10:00:00Z",
                "updated_at": "2026-07-06T10:00:00Z",
            }
        ]
    }

    async with TestClient(TestServer(app)) as client:
        legacy_put = await client.put(
            "/api/v1/vault/test-vault/data-annotations/report.pdf",
            json=legacy_doc,
            headers=auth(),
        )
        v2_get = await client.get(
            "/api/v1/vault/test-vault/annotations/data/report.pdf",
            headers=auth(),
        )
        payload = await v2_get.json()

    v2_name = sha256("data:report.pdf".encode("utf-8")).hexdigest() + ".json"
    assert legacy_put.status == 200
    assert v2_get.status == 200
    assert payload == {
        "version": 2,
        "source_key": "data:report.pdf",
        "source": {"kind": "data", "path": "report.pdf"},
        "annotations": [
            {
                "id": "legacy-text",
                "kind": "text",
                "anchor": {
                    "kind": "pdf_text",
                    "quote": "legacy quote",
                    "rects": [
                        {"page": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
                    ],
                },
                "comment": "legacy note",
                "created_at": "2026-07-06T10:00:00Z",
                "updated_at": "2026-07-06T10:00:00Z",
            }
        ],
    }
    assert not (tmp_vault.path / ".pkm" / "annotations" / "data" / v2_name).exists()


@pytest.mark.anyio
async def test_note_annotations_v2_round_trip_without_mutating_markdown(
    app,
    tmp_vault: VaultConfig,
) -> None:
    note_path = tmp_vault.notes_dir / "2026-04-01-mvcc.md"
    original_body = note_path.read_text(encoding="utf-8")
    document = {
        "source_revision": "fnv1a:1234abcd",
        "annotations": [
            {
                "id": "ann-1",
                "kind": "note",
                "anchor": {
                    "kind": "text_quote",
                    "quote": "MVCC",
                    "occurrence": 0,
                    "selector_version": 1,
                    "prefix": "uses ",
                    "suffix": " for concurrency",
                    "start": 5,
                    "end": 9,
                    "heading_path": ["Overview"],
                },
                "status": "active",
                "reanchor": {"confidence": 1, "reason": "exact"},
                "comment": "key term",
                "created_at": "2026-07-06T10:00:00Z",
                "updated_at": "2026-07-06T10:00:00Z",
            }
        ],
    }

    async with TestClient(TestServer(app)) as client:
        put_resp = await client.put(
            "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc",
            json=document,
            headers=auth(),
        )
        saved = await put_resp.json()
        get_resp = await client.get(
            "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc",
            headers=auth(),
        )
        loaded = await get_resp.json()

    assert put_resp.status == 200
    assert get_resp.status == 200
    assert saved == loaded
    assert saved["source_key"] == "note:2026-04-01-mvcc"
    assert saved["source"] == {"kind": "note", "note_id": "2026-04-01-mvcc"}
    assert saved["source_revision"] == document["source_revision"]
    assert saved["annotations"] == document["annotations"]
    assert note_path.read_text(encoding="utf-8") == original_body


@pytest.mark.anyio
async def test_note_annotations_v2_reads_legacy_markdown_annotations_without_migrating(
    app,
    tmp_vault: VaultConfig,
) -> None:
    note_path = tmp_vault.notes_dir / "legacy-annotated.md"
    note_path.write_text(
        "First source mentions Alpha quote.\n\n"
        "## Annotations\n"
        "- “Alpha quote.” ([↩ 원문](#quote=Alpha%20quote.&occ=0))\n"
        "  - First memo\n"
        "    continued detail\n",
        encoding="utf-8",
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/annotations/note/legacy-annotated",
            headers=auth(),
        )
        payload = await resp.json()

    v2_name = sha256("note:legacy-annotated".encode("utf-8")).hexdigest() + ".json"
    assert resp.status == 200
    assert payload.pop("annotation_revision") == 0
    assert payload.pop("storage_mode") == "legacy"
    assert payload.pop("legacy_revision").startswith("sha256:")
    assert payload == {
        "version": 2,
        "source_key": "note:legacy-annotated",
        "source": {"kind": "note", "note_id": "legacy-annotated"},
        "annotations": [
            {
                "id": "#quote=Alpha%20quote.&occ=0\u00003",
                "kind": "note",
                "anchor": {
                    "kind": "text_quote",
                    "quote": "Alpha quote.",
                    "occurrence": 0,
                },
                "comment": "First memo\ncontinued detail",
                "created_at": "",
                "updated_at": "",
            }
        ],
    }
    assert not (tmp_vault.path / ".pkm" / "annotations" / "note" / v2_name).exists()


@pytest.mark.anyio
async def test_note_annotations_v2_supports_daily_notes(
    app,
    tmp_vault: VaultConfig,
) -> None:
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/annotations/note/2026-04-01",
            headers=auth(),
        )
        payload = await resp.json()

    assert resp.status == 200
    assert payload["source_key"] == "note:2026-04-01"
    assert payload["source"] == {"kind": "note", "note_id": "2026-04-01"}


@pytest.mark.anyio
async def test_note_annotations_v2_rejects_invalid_or_missing_note_ids(
    app,
    tmp_vault: VaultConfig,
) -> None:
    async with TestClient(TestServer(app)) as client:
        invalid = await client.get(
            "/api/v1/vault/test-vault/annotations/note/tag:daily-notes",
            headers=auth(),
        )
        missing = await client.get(
            "/api/v1/vault/test-vault/annotations/note/not-found",
            headers=auth(),
        )

    assert invalid.status == 400
    assert missing.status == 404


@pytest.mark.anyio
async def test_legacy_note_annotations_require_explicit_current_snapshot_to_migrate(
    app,
    tmp_vault: VaultConfig,
) -> None:
    note_id = "legacy-migration"
    note_path = tmp_vault.notes_dir / f"{note_id}.md"
    note_path.write_text(
        "Source has Alpha quote.\n\n"
        "## Annotations\n"
        "- “Alpha quote.” ([↩ 원문](#quote=Alpha%20quote.&occ=0))\n"
        "  - Original memo\n",
        encoding="utf-8",
    )
    endpoint = f"/api/v1/vault/test-vault/annotations/note/{note_id}"
    sidecar_name = sha256(f"note:{note_id}".encode()).hexdigest() + ".json"
    sidecar_path = tmp_vault.path / ".pkm" / "annotations" / "note" / sidecar_name

    async with TestClient(TestServer(app)) as client:
        loaded_response = await client.get(endpoint, headers=auth())
        loaded = await loaded_response.json()
        note_response = await client.get(
            f"/api/v1/vault/test-vault/notes/{note_id}", headers=auth()
        )
        note_revision = (await note_response.json())["content_hash"]
        automatic = await client.patch(
            endpoint,
            json={
                "base_revision": 0,
                "base_note_revision": note_revision,
                "source_revision": "fnv1a:1234abcd",
                "updates": [],
            },
            headers={**auth(), "If-Match": '"0"'},
        )
        note_path.write_text(
            note_path.read_text(encoding="utf-8").replace(
                "Original memo", "Externally changed memo"
            ),
            encoding="utf-8",
        )
        stale_migration = await client.put(
            endpoint,
            json={
                "base_revision": 0,
                "legacy_revision": loaded["legacy_revision"],
                "annotations": loaded["annotations"],
            },
            headers={**auth(), "If-Match": '"0"'},
        )

    assert loaded["storage_mode"] == "legacy"
    assert automatic.status == 409
    assert stale_migration.status == 409
    assert not sidecar_path.exists()


@pytest.mark.anyio
async def test_legacy_note_migration_removes_shadow_and_rejects_stale_markdown_put(
    app,
    tmp_vault: VaultConfig,
) -> None:
    note_id = "legacy-cutover"
    original_body = (
        "Source has Alpha quote.\n\n"
        "## Annotations\n"
        "- “Alpha quote.” ([↩ 원문](#quote=Alpha%20quote.&occ=0))\n"
        "  - Original memo\n\n"
        "## Next\n"
        "Keep this section.\n"
    )
    note_path = tmp_vault.notes_dir / f"{note_id}.md"
    note_path.write_text(original_body, encoding="utf-8")
    annotations_endpoint = f"/api/v1/vault/test-vault/annotations/note/{note_id}"
    note_endpoint = f"/api/v1/vault/test-vault/notes/{note_id}"

    async with TestClient(TestServer(app)) as client:
        loaded_response = await client.get(annotations_endpoint, headers=auth())
        loaded = await loaded_response.json()
        migrated = await client.put(
            annotations_endpoint,
            json={
                "base_revision": 0,
                "legacy_revision": loaded["legacy_revision"],
                "annotations": loaded["annotations"],
            },
            headers={**auth(), "If-Match": '"0"'},
        )
        note_response = await client.get(note_endpoint, headers=auth())
        note_payload = await note_response.json()
        stale_note_put = await client.put(
            note_endpoint,
            json={"body": original_body},
            headers={
                **auth(),
                "If-Match": f'"{note_payload["content_hash"]}"',
            },
        )
        reloaded_response = await client.get(annotations_endpoint, headers=auth())
        reloaded = await reloaded_response.json()

    assert migrated.status == 200
    assert "## Annotations" not in note_payload["body"]
    assert "## Next\nKeep this section." in note_payload["body"]
    assert stale_note_put.status == 409
    assert reloaded["storage_mode"] == "v2"
    assert reloaded["annotations"][0]["comment"] == "Original memo"


@pytest.mark.anyio
async def test_get_note_annotations_reports_storage_revision_and_etag(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"

    async with TestClient(TestServer(app)) as client:
        response = await client.get(endpoint, headers=auth())
        payload = await response.json()

    assert response.status == 200
    assert response.headers["ETag"] == '"0"'
    assert payload["annotation_revision"] == 0
    assert payload["storage_mode"] == "none"


@pytest.mark.anyio
async def test_patch_note_annotations_requires_base_revision(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    annotation = {
        "id": "ann-1",
        "kind": "note",
        "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
        "comment": "first",
        "created_at": "",
        "updated_at": "",
    }

    async with TestClient(TestServer(app)) as client:
        put_response = await client.put(
            endpoint,
            json={"base_revision": 0, "annotations": [annotation]},
            headers=auth(),
        )
        patch_response = await client.patch(
            endpoint,
            json={
                "source_revision": "fnv1a:1234abcd",
                "updates": [],
            },
            headers=auth(),
        )

    assert put_response.status == 200
    assert patch_response.status == 428


@pytest.mark.anyio
async def test_put_note_annotations_rejects_inconsistent_if_match(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    annotation = {
        "id": "ann-1",
        "kind": "note",
        "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
        "comment": "first",
        "created_at": "",
        "updated_at": "",
    }

    async with TestClient(TestServer(app)) as client:
        response = await client.put(
            endpoint,
            json={"base_revision": 0, "annotations": [annotation]},
            headers={**auth(), "If-Match": '"1"'},
        )

    assert response.status == 412


@pytest.mark.anyio
async def test_patch_note_annotations_rejects_stale_revision_without_overwrite(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    annotation = {
        "id": "ann-1",
        "kind": "note",
        "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
        "comment": "first",
        "created_at": "",
        "updated_at": "",
    }
    update = {
        "id": "ann-1",
        "anchor": {
            "kind": "text_quote",
            "quote": "MVCC",
            "occurrence": 0,
            "selector_version": 1,
            "prefix": "uses ",
            "suffix": " safely",
            "start": 5,
            "end": 9,
            "heading_path": ["Overview"],
        },
        "status": "active",
        "reanchor": {"confidence": 1, "reason": "exact"},
    }

    async with TestClient(TestServer(app)) as client:
        note_response = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc", headers=auth()
        )
        note_revision = (await note_response.json())["content_hash"]
        created = await client.put(
            endpoint,
            json={"base_revision": 0, "annotations": [annotation]},
            headers=auth(),
        )
        first = await client.patch(
            endpoint,
            json={
                "base_revision": 1,
                "base_note_revision": note_revision,
                "source_revision": "fnv1a:1234abcd",
                "updates": [update],
            },
            headers=auth(),
        )
        stale = await client.patch(
            endpoint,
            json={
                "base_revision": 1,
                "base_note_revision": note_revision,
                "source_revision": "fnv1a:87654321",
                "updates": [],
            },
            headers=auth(),
        )
        loaded_response = await client.get(endpoint, headers=auth())
        loaded = await loaded_response.json()

    assert created.status == 200
    assert first.status == 200
    assert stale.status == 409
    assert loaded["annotation_revision"] == 2
    assert loaded["source_revision"] == "fnv1a:1234abcd"
    assert loaded["annotations"][0]["anchor"] == update["anchor"]


@pytest.mark.anyio
async def test_legacy_client_put_preserves_rich_fields_and_newer_selector(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    rich = {
        "id": "ann-1",
        "kind": "note",
        "anchor": {
            "kind": "text_quote",
            "quote": "new MVCC phrase",
            "occurrence": 0,
            "selector_version": 1,
            "prefix": "uses ",
            "suffix": " safely",
            "start": 5,
            "end": 20,
            "heading_path": ["Overview"],
        },
        "status": "active",
        "reanchor": {"confidence": 1, "reason": "exact"},
        "comment": "original",
        "created_at": "2026-07-06T10:00:00Z",
        "updated_at": "2026-07-06T10:00:00Z",
        "extension": {"owner": "new-client"},
    }
    legacy_edit = {
        "id": "ann-1",
        "kind": "note",
        "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
        "comment": "edited by old client",
        "created_at": "",
        "updated_at": "",
    }

    async with TestClient(TestServer(app)) as client:
        await client.put(
            endpoint,
            json={
                "base_revision": 0,
                "source_revision": "fnv1a:1234abcd",
                "annotations": [rich],
            },
            headers=auth(),
        )
        edited = await client.put(
            endpoint,
            json={"annotations": [legacy_edit]},
            headers=auth(),
        )
        payload = await edited.json()

    assert edited.status == 200
    assert payload["annotation_revision"] == 2
    assert payload["source_revision"] == "fnv1a:1234abcd"
    assert payload["annotations"][0] == {
        **rich,
        "comment": "edited by old client",
    }


@pytest.mark.anyio
async def test_legacy_client_put_preserves_newer_sibling_annotations(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"

    def annotation(annotation_id: str, comment: str) -> dict:
        return {
            "id": annotation_id,
            "kind": "note",
            "anchor": {
                "kind": "text_quote",
                "quote": annotation_id,
                "occurrence": 0,
            },
            "comment": comment,
            "created_at": "",
            "updated_at": "",
        }

    first = annotation("ann-a", "original")
    sibling = annotation("ann-b", "newer sibling")
    legacy_edit = annotation("ann-a", "edited by old client")

    async with TestClient(TestServer(app)) as client:
        created = await client.put(
            endpoint,
            json={"base_revision": 0, "annotations": [first, sibling]},
            headers=auth(),
        )
        edited = await client.put(
            endpoint,
            json={"annotations": [legacy_edit]},
            headers=auth(),
        )
        payload = await edited.json()

    assert created.status == 200
    assert edited.status == 200
    assert payload["annotation_revision"] == 2
    assert {item["id"] for item in payload["annotations"]} == {"ann-a", "ann-b"}
    assert (
        next(item for item in payload["annotations"] if item["id"] == "ann-b")[
            "comment"
        ]
        == "newer sibling"
    )


@pytest.mark.anyio
async def test_patch_note_annotations_rejects_stale_note_revision(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    annotation = {
        "id": "ann-1",
        "kind": "note",
        "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
        "comment": "first",
        "created_at": "",
        "updated_at": "",
    }

    async with TestClient(TestServer(app)) as client:
        note_response = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc", headers=auth()
        )
        note_payload = await note_response.json()
        created = await client.put(
            endpoint,
            json={"base_revision": 0, "annotations": [annotation]},
            headers=auth(),
        )
        note_path = tmp_vault.notes_dir / "2026-04-01-mvcc.md"
        note_path.write_text(
            note_path.read_text(encoding="utf-8") + "\nExternal edit.\n",
            encoding="utf-8",
        )
        patch_response = await client.patch(
            endpoint,
            json={
                "base_revision": 1,
                "base_note_revision": note_payload["content_hash"],
                "source_revision": "fnv1a:1234abcd",
                "updates": [],
            },
            headers=auth(),
        )

    assert created.status == 200
    assert patch_response.status == 409


@pytest.mark.anyio
@pytest.mark.parametrize(
    "annotation",
    [
        {
            "id": "ann-comment",
            "kind": "note",
            "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
            "comment": 42,
            "created_at": "",
            "updated_at": "",
        },
        {
            "id": "ann-range",
            "kind": "note",
            "anchor": {
                "kind": "text_quote",
                "quote": "MVCC",
                "occurrence": 0,
                "selector_version": 1,
                "prefix": "",
                "suffix": "",
                "start": 0,
                "end": 3,
            },
            "status": "active",
            "reanchor": {"confidence": 1, "reason": "exact"},
            "comment": "bad range",
            "created_at": "",
            "updated_at": "",
        },
        {
            "id": "ann-status",
            "kind": "note",
            "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
            "status": "active",
            "reanchor": {"confidence": 0, "reason": "ambiguous"},
            "comment": "bad status",
            "created_at": "",
            "updated_at": "",
        },
    ],
)
async def test_put_note_annotations_rejects_malformed_annotation_fields(
    app,
    tmp_vault: VaultConfig,
    annotation: dict,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"

    async with TestClient(TestServer(app)) as client:
        response = await client.put(
            endpoint,
            json={"base_revision": 0, "annotations": [annotation]},
            headers=auth(),
        )

    assert response.status == 400


@pytest.mark.anyio
async def test_put_note_annotations_rejects_invalid_rich_selector(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    response_payload = {
        "annotations": [
            {
                "id": "ann-1",
                "kind": "note",
                "anchor": {
                    "kind": "text_quote",
                    "quote": "MVCC",
                    "occurrence": 0,
                    "selector_version": 2,
                },
                "status": "active",
                "reanchor": {"confidence": 1, "reason": "exact"},
                "comment": "first",
                "created_at": "",
                "updated_at": "",
            }
        ]
    }

    async with TestClient(TestServer(app)) as client:
        response = await client.put(endpoint, json=response_payload, headers=auth())

    assert response.status == 400


@pytest.mark.anyio
async def test_patch_note_annotation_anchors_rejects_invalid_selector_ranges(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    annotation = {
        "id": "ann-1",
        "kind": "note",
        "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
        "comment": "first",
        "created_at": "",
        "updated_at": "",
    }

    async with TestClient(TestServer(app)) as client:
        note_response = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc", headers=auth()
        )
        note_revision = (await note_response.json())["content_hash"]
        await client.put(endpoint, json={"annotations": [annotation]}, headers=auth())
        response = await client.patch(
            endpoint,
            json={
                "base_revision": 1,
                "base_note_revision": note_revision,
                "source_revision": "fnv1a:1234abcd",
                "updates": [
                    {
                        "id": "ann-1",
                        "anchor": {
                            "kind": "text_quote",
                            "quote": "MVCC",
                            "occurrence": 0,
                            "selector_version": 1,
                            "prefix": "uses ",
                            "suffix": " safely",
                            "start": 10,
                            "end": 4,
                            "heading_path": [],
                        },
                        "status": "active",
                        "reanchor": {"confidence": 1, "reason": "exact"},
                    }
                ],
            },
            headers=auth(),
        )

    assert response.status == 400


@pytest.mark.anyio
async def test_patch_note_annotation_anchors_merges_by_id_without_replacing_siblings(
    app,
    tmp_vault: VaultConfig,
) -> None:
    endpoint = "/api/v1/vault/test-vault/annotations/note/2026-04-01-mvcc"
    original = {
        "annotations": [
            {
                "id": "ann-1",
                "kind": "note",
                "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
                "comment": "first",
                "created_at": "2026-07-06T10:00:00Z",
                "updated_at": "2026-07-06T10:00:00Z",
            },
            {
                "id": "ann-2",
                "kind": "note",
                "anchor": {
                    "kind": "text_quote",
                    "quote": "concurrency",
                    "occurrence": 0,
                },
                "comment": "second",
                "created_at": "2026-07-06T10:00:00Z",
                "updated_at": "2026-07-06T10:00:00Z",
            },
        ]
    }
    rich_anchor = {
        "kind": "text_quote",
        "quote": "multi-version concurrency control",
        "occurrence": 0,
        "selector_version": 1,
        "prefix": "uses ",
        "suffix": " for readers",
        "start": 12,
        "end": 45,
        "heading_path": ["Overview"],
    }

    async with TestClient(TestServer(app)) as client:
        note_response = await client.get(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc", headers=auth()
        )
        note_revision = (await note_response.json())["content_hash"]
        put_resp = await client.put(endpoint, json=original, headers=auth())
        patch_resp = await client.patch(
            endpoint,
            json={
                "base_revision": 1,
                "base_note_revision": note_revision,
                "source_revision": "fnv1a:1234abcd",
                "updates": [
                    {
                        "id": "ann-1",
                        "anchor": rich_anchor,
                        "status": "active",
                        "reanchor": {"confidence": 0.9, "reason": "context"},
                    }
                ],
            },
            headers=auth(),
        )
        patched = await patch_resp.json()

    assert put_resp.status == 200
    assert patch_resp.status == 200
    assert patched["source_revision"] == "fnv1a:1234abcd"
    assert patched["annotations"][0] == {
        **original["annotations"][0],
        "anchor": rich_anchor,
        "status": "active",
        "reanchor": {"confidence": 0.9, "reason": "context"},
    }
    assert patched["annotations"][1] == original["annotations"][1]
