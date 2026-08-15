"""Integration tests for feedback records stored in the vault."""

from __future__ import annotations

from datetime import datetime

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.commands.daily import _make_subnote_content
from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-feedback-token"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7423, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.mark.anyio
async def test_post_feedback_creates_tagged_subnote_and_daily_link(
    app, tmp_vault: VaultConfig
) -> None:
    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/v1/vault/test-vault/feedback",
            json={
                "title": "Keep feedback in the vault",
                "description": "I want requests available without an external service.",
                "feedback_type": "requirement",
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert response.status == 201
        record = await response.json()

    assert record["title"] == "Keep feedback in the vault"
    assert record["feedback_type"] == "requirement"
    assert record["description"] == "I want requests available without an external service."
    assert record["note_id"].startswith(
        f"{datetime.now():%Y-%m-%d}-feedback-"
    )

    feedback_note = tmp_vault.daily_dir / f"{record['note_id']}.md"
    assert feedback_note.exists()
    saved = feedback_note.read_text(encoding="utf-8")
    assert "- feedback" in saved
    assert "feedback_type: requirement" in saved

    daily_log = (
        tmp_vault.daily_dir / f"{datetime.now():%Y-%m-%d}.md"
    ).read_text(encoding="utf-8")
    assert f"[[{record['note_id']}]]" in daily_log


@pytest.mark.anyio
async def test_get_feedback_returns_only_feedback_subnotes_newest_first(
    app, tmp_vault: VaultConfig
) -> None:
    older_id = "2026-01-01-feedback-older"
    newer_id = "2026-01-02-feedback-newer"
    tmp_vault.daily_dir.joinpath(f"{older_id}.md").write_text(
        _make_subnote_content(
            older_id,
            "Older requirement",
            tags=["feedback"],
        ).replace(
            "---\n\nOlder requirement",
            "created_at: '2026-01-01T10:00:00Z'\ntitle: Older\nfeedback_type: idea\n---\n\nOlder requirement",
        ),
        encoding="utf-8",
    )
    tmp_vault.daily_dir.joinpath(f"{newer_id}.md").write_text(
        _make_subnote_content(
            newer_id,
            "Newer requirement",
            tags=["feedback"],
        ).replace(
            "---\n\nNewer requirement",
            "created_at: '2026-01-02T10:00:00Z'\ntitle: Newer\nfeedback_type: bug\n---\n\nNewer requirement",
        ),
        encoding="utf-8",
    )
    tmp_vault.daily_dir.joinpath("2026-01-03-meeting.md").write_text(
        _make_subnote_content("2026-01-03-meeting", "Not feedback", tags=["work"]),
        encoding="utf-8",
    )

    async with TestClient(TestServer(app)) as client:
        response = await client.get(
            "/api/v1/vault/test-vault/feedback",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert response.status == 200
        records = await response.json()

    assert [record["note_id"] for record in records] == [newer_id, older_id]
    assert records[0]["feedback_type"] == "bug"
    assert records[0]["description"] == "Newer requirement"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        {"description": "Missing title"},
        {"title": "Missing description"},
        {"title": "Bad type", "description": "Text", "feedback_type": []},
        {"title": "Line\nbreak", "description": "Text"},
    ],
)
async def test_post_feedback_rejects_invalid_input(
    app, tmp_vault: VaultConfig, body: dict
) -> None:
    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/v1/vault/test-vault/feedback",
            json=body,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert response.status == 400


@pytest.mark.anyio
async def test_post_feedback_rejects_missing_auth(app, tmp_vault: VaultConfig) -> None:
    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/v1/vault/test-vault/feedback",
            json={"title": "No auth", "description": "Not allowed"},
        )

    assert response.status == 401
