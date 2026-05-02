"""Integration tests: daily routes (B7) — CRUD and pagination.

Assertions covered:
  (a) monotonic descending order of returned dates
  (b) `before` is exclusive (strictly older)
  (c) `snippet` is first non-empty markdown line (not frontmatter, not blank)
  (d) `todo_count` matches count of `- [ ]` open checkboxes
  (e) default limit=50; request limit=200 is capped to 100
  (f) GET/POST /daily/today round-trip
  (g) auth 401 cases
"""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-daily-token-b7"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7422, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


@pytest.fixture
def vault_with_daily(tmp_vault: VaultConfig) -> VaultConfig:
    """Extend tmp_vault with five daily notes, each with distinct todo_count and snippet.

    Date        todos   snippet (first non-empty body line)
    2026-04-01    0     ## Day 1
    2026-04-02    1     ## Day 2
    2026-04-03    2     ## Day 3
    2026-04-04    3     ## Day 4
    2026-04-05    4     ## Day 5
    """
    for idx, date_str in enumerate(
        ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05"]
    ):
        todo_lines = "".join(f"- [ ] todo {j}\n" for j in range(idx))
        path = tmp_vault.daily_dir / f"{date_str}.md"
        path.write_text(
            f"---\nid: {date_str}\nconsolidated: false\naliases: []\ntags:\n- daily-notes\n---\n\n"
            f"## Day {idx + 1}\n"
            f"{todo_lines}"
            f"- [done] something\n",
            encoding="utf-8",
        )
    return tmp_vault


# ---------------------------------------------------------------------------
# (a) Monotonic descending order
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_daily_descending_order(app, vault_with_daily: VaultConfig) -> None:
    """(a) Returned dates must be in strictly monotonic descending order."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        dates = [item["date"] for item in data]
        assert len(dates) > 1, "Need multiple dates to test ordering"
        assert dates == sorted(dates, reverse=True), f"Not descending: {dates}"


# ---------------------------------------------------------------------------
# (b) before= is exclusive
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_daily_before_excludes_boundary(
    app, vault_with_daily: VaultConfig
) -> None:
    """(b) before=2026-04-04 must exclude 2026-04-04 itself and everything newer."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily?before=2026-04-04",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        dates = [item["date"] for item in data]
        assert "2026-04-04" not in dates, "before= boundary must be excluded"
        assert "2026-04-05" not in dates, "dates newer than before= must be excluded"
        assert "2026-04-03" in dates
        assert "2026-04-02" in dates
        assert "2026-04-01" in dates


# ---------------------------------------------------------------------------
# (c) snippet — first non-empty markdown line, not frontmatter, not blank
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_daily_snippet_is_first_body_line(
    app, vault_with_daily: VaultConfig
) -> None:
    """(c) snippet is the first non-empty markdown line after the frontmatter block."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        by_date = {item["date"]: item for item in data}

        for idx, date_str in enumerate(
            ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05"]
        ):
            snippet = by_date[date_str]["snippet"]
            expected = f"## Day {idx + 1}"
            assert snippet == expected, (
                f"{date_str}: expected snippet {expected!r}, got {snippet!r}"
            )
            # Must not be a frontmatter artifact
            assert not snippet.startswith("---"), (
                f"Snippet is frontmatter delimiter: {snippet!r}"
            )
            assert not snippet.startswith("id:"), (
                f"Snippet is frontmatter field: {snippet!r}"
            )
            assert snippet != "", f"Snippet must not be empty for {date_str}"


# ---------------------------------------------------------------------------
# (d) todo_count — count of `- [ ]` open checkboxes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_daily_todo_count(app, vault_with_daily: VaultConfig) -> None:
    """(d) todo_count matches the number of `- [ ]` open checkboxes in the note."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        by_date = {item["date"]: item for item in data}

        expected_counts = {
            "2026-04-01": 0,
            "2026-04-02": 1,
            "2026-04-03": 2,
            "2026-04-04": 3,
            "2026-04-05": 4,
        }
        for date_str, expected in expected_counts.items():
            actual = by_date[date_str]["todo_count"]
            assert actual == expected, (
                f"{date_str}: expected todo_count={expected}, got {actual}"
            )


# ---------------------------------------------------------------------------
# (e) limit — default 50, hard cap 100
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_daily_default_limit_returns_all_when_few(
    app, vault_with_daily: VaultConfig
) -> None:
    """(e) default limit=50: returns all notes when total < 50."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 5


@pytest.mark.anyio
async def test_list_daily_limit_capped_at_100(
    app, vault_with_daily: VaultConfig
) -> None:
    """(e) limit=200 is capped to 100 (only 5 notes exist, so all returned)."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily?limit=200",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert len(data) <= 100


@pytest.mark.anyio
async def test_list_daily_limit_2_returns_two_most_recent(
    app, vault_with_daily: VaultConfig
) -> None:
    """(e) limit=2 returns the 2 most recent notes in descending order."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily?limit=2",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 2
        assert data[0]["date"] == "2026-04-05"
        assert data[1]["date"] == "2026-04-04"


# ---------------------------------------------------------------------------
# (f) GET/POST /daily/today round-trip
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_daily_today_creates_and_returns_note(
    app, tmp_vault: VaultConfig
) -> None:
    """(f) GET /daily/today creates today's note if absent and returns 8-key schema."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily/today",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert set(data.keys()) >= {"note_id", "title", "body", "tags"}
        # Second call is idempotent
        resp2 = await client.get(
            "/api/v1/vault/test-vault/daily/today",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp2.status == 200
        data2 = await resp2.json()
        assert data2["note_id"] == data["note_id"]


@pytest.mark.anyio
async def test_post_daily_entry_appends(app, tmp_vault: VaultConfig) -> None:
    """(f) POST /daily/today type=entry appends an entry and returns 201 with entry text."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/daily/today",
            json={"content": "wrote tests today", "type": "entry"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert "entry" in data
        assert "wrote tests today" in data["entry"]


@pytest.mark.anyio
async def test_post_daily_subnote_creates_file(app, tmp_vault: VaultConfig) -> None:
    """(f) POST /daily/today type=subnote creates a subnote and returns note_id."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/daily/today",
            json={"content": "# Meeting notes", "type": "subnote", "title": "standup"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert "note_id" in data
        assert "standup" in data["note_id"]


@pytest.mark.anyio
async def test_post_daily_subnote_missing_title_returns_400(
    app, tmp_vault: VaultConfig
) -> None:
    """(f) POST /daily/today type=subnote without title returns 400."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/daily/today",
            json={"content": "content", "type": "subnote"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 400


@pytest.mark.anyio
async def test_get_daily_date_returns_specific_note(
    app, vault_with_daily: VaultConfig
) -> None:
    """(f) GET /daily/{date} returns the note for a specific date."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily/2026-04-03",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["note_id"] == "2026-04-03"


@pytest.mark.anyio
async def test_get_daily_date_not_found_returns_404(
    app, vault_with_daily: VaultConfig
) -> None:
    """(f) GET /daily/{date} for a non-existent date returns 404."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/daily/2020-01-01",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 404


# ---------------------------------------------------------------------------
# (g) Auth 401
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_daily_no_auth_returns_401(app, tmp_vault: VaultConfig) -> None:
    """(g) GET /daily without auth returns 401."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/vault/test-vault/daily")
        assert resp.status == 401


@pytest.mark.anyio
async def test_get_daily_today_no_auth_returns_401(app, tmp_vault: VaultConfig) -> None:
    """(g) GET /daily/today without auth returns 401."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/vault/test-vault/daily/today")
        assert resp.status == 401


@pytest.mark.anyio
async def test_post_daily_today_no_auth_returns_401(
    app, tmp_vault: VaultConfig
) -> None:
    """(g) POST /daily/today without auth returns 401."""
    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/daily/today",
            json={"content": "test", "type": "entry"},
        )
        assert resp.status == 401
