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
    v2_name = sha256("data:reports/한글 report.pdf".encode("utf-8")).hexdigest() + ".json"
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
    assert legacy_payload == {"version": 1, "source_path": "report.pdf", "annotations": []}


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
                "rects": [
                    {"page": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
                ],
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
        "annotations": [
            {
                "id": "ann-1",
                "kind": "note",
                "anchor": {"kind": "text_quote", "quote": "MVCC", "occurrence": 0},
                "comment": "key term",
                "created_at": "2026-07-06T10:00:00Z",
                "updated_at": "2026-07-06T10:00:00Z",
            }
        ]
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
