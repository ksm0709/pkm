"""Integration tests for web data-file upload and download routes."""

from __future__ import annotations

import shutil
from asyncio import gather

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from pkm.config import VaultConfig, WebConfig
from pkm.web.server import make_app

TOKEN = "test-data-token"


@pytest.fixture
def web_cfg(tmp_path) -> WebConfig:
    token_path = tmp_path / "web-token"
    token_path.write_text(TOKEN, encoding="utf-8")
    return WebConfig(port=7422, bind="127.0.0.1", token_path=token_path)


@pytest.fixture
def app(web_cfg: WebConfig):
    return make_app(web_config=web_cfg)


def upload_form(
    content: bytes,
    *,
    filename: str = "report.pdf",
    content_type: str = "application/pdf",
) -> FormData:
    form = FormData()
    form.add_field(
        "file",
        content,
        filename=filename,
        content_type=content_type,
    )
    return form


def raw_upload_body(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "pkm-test-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/plain\r\n"
        "\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


@pytest.mark.anyio
async def test_post_data_upload_writes_file(app, tmp_vault: VaultConfig) -> None:
    payload = b"%PDF-test-bytes"

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/data",
            data=upload_form(payload),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 201
        data = await resp.json()

    assert data["filename"] == "report.pdf"
    assert data["href"] == "/api/v1/vault/test-vault/data/report.pdf"
    assert data["markdown"] == "[report.pdf](/api/v1/vault/test-vault/data/report.pdf)"
    assert data["size"] == len(payload)
    assert data["content_type"] == "application/pdf"
    assert (tmp_vault.data_dir / "report.pdf").read_bytes() == payload


@pytest.mark.anyio
async def test_post_data_upload_creates_data_dir(app, tmp_vault: VaultConfig) -> None:
    shutil.rmtree(tmp_vault.data_dir)
    assert not tmp_vault.data_dir.exists()

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/data",
            data=upload_form(b"hello", filename="notes.txt", content_type="text/plain"),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 201
    assert (tmp_vault.data_dir / "notes.txt").read_text(encoding="utf-8") == "hello"


@pytest.mark.anyio
async def test_post_data_upload_rejects_missing_file(app, tmp_vault: VaultConfig) -> None:
    form = FormData()
    form.add_field("description", "missing file")

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/data",
            data=form,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 400


@pytest.mark.anyio
async def test_post_data_upload_rejects_traversal_filename(
    app,
    tmp_vault: VaultConfig,
) -> None:
    outside = tmp_vault.path / "escape.txt"
    body, content_type = raw_upload_body("../escape.txt", b"escape")

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/data",
            data=body,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": content_type,
            },
        )

    assert resp.status == 400
    assert not outside.exists()
    assert not (tmp_vault.data_dir / "escape.txt").exists()


@pytest.mark.anyio
async def test_post_data_upload_uses_collision_suffix(
    app,
    tmp_vault: VaultConfig,
) -> None:
    async with TestClient(TestServer(app)) as client:
        first = await client.post(
            "/api/v1/vault/test-vault/data",
            data=upload_form(b"one", filename="report.pdf"),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        second = await client.post(
            "/api/v1/vault/test-vault/data",
            data=upload_form(b"two", filename="report.pdf"),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert first.status == 201
        assert second.status == 201
        data = await second.json()

    assert data["filename"] == "report-1.pdf"
    assert (tmp_vault.data_dir / "report.pdf").read_bytes() == b"one"
    assert (tmp_vault.data_dir / "report-1.pdf").read_bytes() == b"two"


@pytest.mark.anyio
async def test_post_data_upload_skips_existing_collision_suffixes(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "report.pdf").write_bytes(b"existing")
    (tmp_vault.data_dir / "report-1.pdf").write_bytes(b"existing 1")

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/v1/vault/test-vault/data",
            data=upload_form(b"new", filename="report.pdf"),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 201
        data = await resp.json()

    assert data["filename"] == "report-2.pdf"
    assert (tmp_vault.data_dir / "report.pdf").read_bytes() == b"existing"
    assert (tmp_vault.data_dir / "report-1.pdf").read_bytes() == b"existing 1"
    assert (tmp_vault.data_dir / "report-2.pdf").read_bytes() == b"new"


@pytest.mark.anyio
async def test_post_data_upload_concurrent_same_name_allocates_unique_files(
    app,
    tmp_vault: VaultConfig,
) -> None:
    async with TestClient(TestServer(app)) as client:
        first, second = await gather(
            client.post(
                "/api/v1/vault/test-vault/data",
                data=upload_form(b"one", filename="race.txt", content_type="text/plain"),
                headers={"Authorization": f"Bearer {TOKEN}"},
            ),
            client.post(
                "/api/v1/vault/test-vault/data",
                data=upload_form(b"two", filename="race.txt", content_type="text/plain"),
                headers={"Authorization": f"Bearer {TOKEN}"},
            ),
        )
        assert first.status == 201
        assert second.status == 201
        first_data, second_data = await gather(first.json(), second.json())

    filenames = {first_data["filename"], second_data["filename"]}
    assert filenames == {"race.txt", "race-1.txt"}
    contents = {
        (tmp_vault.data_dir / filename).read_bytes() for filename in filenames
    }
    assert contents == {b"one", b"two"}


@pytest.mark.anyio
async def test_get_data_file_returns_uploaded_bytes(app, tmp_vault: VaultConfig) -> None:
    target = tmp_vault.data_dir / "sample.pdf"
    target.write_bytes(b"pdf bytes")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data/sample.pdf",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        body = await resp.read()

    assert body == b"pdf bytes"


@pytest.mark.anyio
async def test_get_data_file_forces_attachment_for_active_content(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "page.html").write_text("<script></script>", encoding="utf-8")
    (tmp_vault.data_dir / "vector.svg").write_text("<svg></svg>", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        html_resp = await client.get(
            "/api/v1/vault/test-vault/data/page.html",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        svg_resp = await client.get(
            "/api/v1/vault/test-vault/data/vector.svg",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert html_resp.status == 200
        assert svg_resp.status == 200

    for resp in (html_resp, svg_resp):
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Content-Type"].startswith("application/octet-stream")
        assert "attachment" in resp.headers["Content-Disposition"]


@pytest.mark.anyio
async def test_get_data_file_allows_raster_images_inline(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "photo.png").write_bytes(b"png")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data/photo.png",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Content-Type"].startswith("image/png")
    assert "Content-Disposition" not in resp.headers


@pytest.mark.anyio
async def test_get_data_file_rejects_traversal(app, tmp_vault: VaultConfig) -> None:
    outside = tmp_vault.path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data/..%2Fsecret.txt",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status in {400, 404}
        body = await resp.text()

    assert body != "secret"


@pytest.mark.anyio
async def test_data_routes_require_auth(app, tmp_vault: VaultConfig) -> None:
    async with TestClient(TestServer(app)) as client:
        post_resp = await client.post(
            "/api/v1/vault/test-vault/data",
            data=upload_form(b"no auth"),
        )
        get_resp = await client.get("/api/v1/vault/test-vault/data/sample.pdf")

    assert post_resp.status == 401
    assert get_resp.status == 401


@pytest.mark.anyio
async def test_data_routes_do_not_accept_query_token(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "sample.pdf").write_bytes(b"pdf")

    async with TestClient(TestServer(app)) as client:
        post_resp = await client.post(
            f"/api/v1/vault/test-vault/data?token={TOKEN}",
            data=upload_form(b"query token"),
        )
        get_resp = await client.get(
            f"/api/v1/vault/test-vault/data/sample.pdf?token={TOKEN}",
        )

    assert post_resp.status == 401
    assert get_resp.status == 401
