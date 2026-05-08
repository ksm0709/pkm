"""Integration tests: write routes (B7) — POST /notes and PUT /notes/{id}."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-write-token-b7"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7421, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


# --- POST /api/v1/vault/{name}/notes ---


@pytest.mark.anyio
async def test_create_note_returns_201(app, tmp_vault: VaultConfig) -> None:
    """POST /notes with valid body returns 201 and 8-key note schema."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes",
            json={"title": "Test Note", "body": "Hello world"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert set(data.keys()) >= {
            "note_id",
            "title",
            "body",
            "frontmatter",
            "created",
            "updated",
            "tags",
            "importance",
        }
        assert data["title"] == "Test Note"
        assert data["body"] == "Hello world"


@pytest.mark.anyio
async def test_create_note_with_tags(app, tmp_vault: VaultConfig) -> None:
    """POST /notes with tags stores them in the note."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes",
            json={"title": "Tagged Note", "body": "content", "tags": ["foo", "bar"]},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert "foo" in data["tags"]
        assert "bar" in data["tags"]


@pytest.mark.anyio
async def test_create_note_missing_title_returns_400(
    app, tmp_vault: VaultConfig
) -> None:
    """POST /notes without title returns 400."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes",
            json={"body": "No title here"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_create_note_rejects_malformed_json(app, tmp_vault: VaultConfig) -> None:
    """POST /notes reports malformed JSON bodies as client errors."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes",
            data="{",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_create_note_maps_lifecycle_conflict_to_409(
    app, tmp_vault: VaultConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lifecycle duplicate errors surface as HTTP conflicts."""
    from pkm.commands import notes as notes_cmd

    def duplicate_note(*_args, **_kwargs):
        raise FileExistsError("duplicate note")

    monkeypatch.setattr(notes_cmd, "create_note", duplicate_note)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes",
            json={"title": "Duplicate Note"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 409


@pytest.mark.anyio
async def test_create_note_maps_lifecycle_validation_to_400(
    app, tmp_vault: VaultConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lifecycle validation errors remain client errors at the REST boundary."""
    from pkm.commands import notes as notes_cmd

    def invalid_note(*_args, **_kwargs):
        raise ValueError("invalid note")

    monkeypatch.setattr(notes_cmd, "create_note", invalid_note)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes",
            json={"title": "Invalid Note"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_create_note_unknown_vault_returns_404(
    app, tmp_vault: VaultConfig
) -> None:
    """POST /notes to unknown vault returns 404."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/no-such-vault/notes",
            json={"title": "Note"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404


@pytest.mark.anyio
async def test_create_note_no_auth_returns_401(app, tmp_vault: VaultConfig) -> None:
    """POST /notes without auth token returns 401."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes",
            json={"title": "Note"},
        )
        assert resp.status == 401


# --- PUT /api/v1/vault/{name}/notes/{id} ---


@pytest.mark.anyio
async def test_ensure_note_creates_blank_note_with_exact_id(
    app, tmp_vault: VaultConfig
) -> None:
    """POST /notes/{id}/ensure creates unresolved wikilink targets in place."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes/new-unresolved-note/ensure",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 201
        data = await resp.json()

    note_path = tmp_vault.notes_dir / "new-unresolved-note.md"
    assert note_path.exists()
    assert data["note_id"] == "new-unresolved-note"
    assert data["title"] == "new unresolved note"
    assert data["body"] == ""


@pytest.mark.anyio
async def test_ensure_note_existing_note_is_idempotent(
    app, tmp_vault: VaultConfig
) -> None:
    """Ensuring an already-resolved note returns it without overwriting content."""
    note_path = tmp_vault.notes_dir / "existing-target.md"
    note_path.write_text(
        "---\nid: existing-target\ntitle: Existing Target\ntags: []\n---\n\nKeep me.\n",
        encoding="utf-8",
    )

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/notes/existing-target/ensure",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()

    assert data["note_id"] == "existing-target"
    assert data["title"] == "Existing Target"
    assert data["body"] == "Keep me.\n"
    assert "Keep me." in note_path.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_ensure_note_rejects_tag_and_path_escape(
    app, tmp_vault: VaultConfig
) -> None:
    """Only normal note ids can be auto-created from app wikilinks."""
    async with TestClient(TestServer(app)) as client:
        tag_resp = await client.post(
            "/api/v1/vault/test-vault/notes/tag:TODO/ensure",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        escape_resp = await client.post(
            "/api/v1/vault/test-vault/notes/..%2Fescape/ensure",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert tag_resp.status == 400
    assert escape_resp.status == 400


@pytest.mark.anyio
async def test_update_note_returns_updated_body(app, tmp_vault: VaultConfig) -> None:
    """PUT /notes/{id} updates body and returns the updated 8-key schema."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc",
            json={"body": "Updated MVCC content."},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["body"] == "Updated MVCC content."
        assert data["note_id"] == "2026-04-01-mvcc"


@pytest.mark.anyio
async def test_update_note_preserves_tags(app, tmp_vault: VaultConfig) -> None:
    """PUT /notes/{id} without tags field preserves existing frontmatter tags."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc",
            json={"body": "new body"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "database" in data["tags"]


@pytest.mark.anyio
async def test_update_note_can_set_tags(app, tmp_vault: VaultConfig) -> None:
    """PUT /notes/{id} with tags field updates the note's tags."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc",
            json={"body": "body", "tags": ["newtag"]},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "newtag" in data["tags"]


@pytest.mark.anyio
async def test_update_note_can_set_title(app, tmp_vault: VaultConfig) -> None:
    """PUT /notes/{id} with title updates frontmatter and response title."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc",
            json={"title": "Updated MVCC Title"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["title"] == "Updated MVCC Title"
        assert "Today" not in data["title"]


@pytest.mark.anyio
async def test_update_note_rejects_malformed_json(app, tmp_vault: VaultConfig) -> None:
    """PUT /notes/{id} reports malformed JSON bodies as client errors."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc",
            data="{",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_update_note_not_found_returns_404(app, tmp_vault: VaultConfig) -> None:
    """PUT /notes/{id} for a non-existent note returns 404."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/notes/does-not-exist",
            json={"body": "body"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404


@pytest.mark.anyio
async def test_update_note_no_auth_returns_401(app, tmp_vault: VaultConfig) -> None:
    """PUT /notes/{id} without auth token returns 401."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.put(
            "/api/v1/vault/test-vault/notes/2026-04-01-mvcc",
            json={"body": "body"},
        )
        assert resp.status == 401
