"""Integration tests for web data-file upload and download routes."""

from __future__ import annotations

import shutil
from asyncio import gather
from hashlib import sha256

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
async def test_get_data_file_returns_nested_api_path(app, tmp_vault: VaultConfig) -> None:
    nested = tmp_vault.data_dir / "my-invest" / "reports" / "329180" / "2026-06-03"
    nested.mkdir(parents=True)
    (nested / "01_deep_research.md").write_text("deep report", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data/"
            "my-invest/reports/329180/2026-06-03/01_deep_research.md",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status == 200
        body = await resp.text()

    assert body == "deep report"
    assert resp.headers["Cache-Control"] == "no-store"


@pytest.mark.anyio
async def test_get_data_file_redirects_nested_human_markdown_path(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "my-invest" / "reports" / "329180" / "2026-06-03"
    nested.mkdir(parents=True)
    (nested / "01_deep_research.md").write_text("deep report", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/test-vault/data/my-invest/reports/329180/2026-06-03/01_deep_research.md",
            headers={"Authorization": f"Bearer {TOKEN}"},
            allow_redirects=False,
        )

    assert resp.status == 303
    assert resp.headers["Location"] == (
        "/test-vault/view-data/my-invest/reports/329180/2026-06-03/"
        "01_deep_research.md"
    )


@pytest.mark.anyio
async def test_nested_data_routes_require_auth_and_reject_query_token(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "bundle" / "report.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("secret data", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        api_no_auth = await client.get("/api/v1/vault/test-vault/data/bundle/report.md")
        human_no_auth = await client.get("/test-vault/data/bundle/report.md")
        api_query_token = await client.get(
            f"/api/v1/vault/test-vault/data/bundle/report.md?token={TOKEN}"
        )
        human_query_token = await client.get(f"/test-vault/data/bundle/report.md?token={TOKEN}")

    assert api_no_auth.status == 401
    assert human_no_auth.status == 401
    assert api_query_token.status == 401
    assert human_query_token.status == 401


@pytest.mark.anyio
async def test_get_nested_data_file_rejects_traversal_variants(
    app,
    tmp_vault: VaultConfig,
) -> None:
    outside = tmp_vault.path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    attempted_paths = [
        "/api/v1/vault/test-vault/data/my-invest%2F..%2F..%2Fsecret.txt",
        "/api/v1/vault/test-vault/data/my-invest%2F%2E%2E%2F%2E%2E%2Fsecret.txt",
        "/api/v1/vault/test-vault/data/my-invest%2F.%2Freports.txt",
        "/api/v1/vault/test-vault/data/my-invest%5Creports.txt",
        "/test-vault/data/my-invest%2F..%2F..%2Fsecret.txt",
        "/test-vault/data/%2Fsecret.txt",
    ]

    async with TestClient(TestServer(app)) as client:
        for path in attempted_paths:
            resp = await client.get(path, headers={"Authorization": f"Bearer {TOKEN}"})
            assert resp.status in {400, 404}
            body = await resp.text()
            assert body != "secret"


@pytest.mark.anyio
async def test_get_nested_data_file_rejects_empty_path_components(
    app,
    tmp_vault: VaultConfig,
) -> None:
    target = tmp_vault.data_dir / "bundle" / "report.md"
    target.parent.mkdir(parents=True)
    target.write_text("safe report", encoding="utf-8")

    attempted_paths = [
        "/api/v1/vault/test-vault/data/bundle%2F%2Freport.md",
        "/test-vault/data/bundle%2F%2Freport.md",
    ]

    async with TestClient(TestServer(app)) as client:
        for path in attempted_paths:
            resp = await client.get(path, headers={"Authorization": f"Bearer {TOKEN}"})
            assert resp.status == 400
            body = await resp.text()
            assert body != "safe report"


@pytest.mark.anyio
async def test_get_nested_data_file_rejects_symlink_escape(
    app,
    tmp_vault: VaultConfig,
) -> None:
    outside = tmp_vault.path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_vault.data_dir / "bundle" / "secret-link.txt"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data/bundle/secret-link.txt",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status in {400, 404}
        body = await resp.text()

    assert body != "secret"


@pytest.mark.anyio
async def test_human_data_route_redirects_renderable_text_files_to_viewer(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "my-invest" / "reports" / "108490" / "2026-06-06"
    nested.mkdir(parents=True)
    (nested / "01_deep_research.md").write_text("# Deep report", encoding="utf-8")
    (nested / "company page.html").write_text("<h1>Company</h1>", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        markdown_resp = await client.get(
            "/test-vault/data/my-invest/reports/108490/2026-06-06/01_deep_research.md",
            headers={"Authorization": f"Bearer {TOKEN}"},
            allow_redirects=False,
        )
        html_resp = await client.get(
            "/test-vault/data/my-invest/reports/108490/2026-06-06/company%20page.html",
            headers={"Authorization": f"Bearer {TOKEN}"},
            allow_redirects=False,
        )

    assert markdown_resp.status == 303
    assert markdown_resp.headers["Location"] == (
        "/test-vault/view-data/my-invest/reports/108490/2026-06-06/"
        "01_deep_research.md"
    )
    assert html_resp.status == 303
    assert html_resp.headers["Location"] == (
        "/test-vault/view-data/my-invest/reports/108490/2026-06-06/"
        "company%20page.html"
    )


@pytest.mark.anyio
async def test_human_data_route_keeps_non_pdf_download_policy(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "bundle"
    nested.mkdir(parents=True)
    (nested / "archive.zip").write_bytes(b"zip")
    (nested / "photo.png").write_bytes(b"png")

    async with TestClient(TestServer(app)) as client:
        zip_resp = await client.get(
            "/test-vault/data/bundle/archive.zip",
            headers={"Authorization": f"Bearer {TOKEN}"},
            allow_redirects=False,
        )
        png_resp = await client.get(
            "/test-vault/data/bundle/photo.png",
            headers={"Authorization": f"Bearer {TOKEN}"},
            allow_redirects=False,
        )

    assert zip_resp.status == 200
    assert zip_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert zip_resp.headers["Content-Type"].startswith("application/octet-stream")
    assert 'filename="archive.zip"' in zip_resp.headers["Content-Disposition"]
    assert png_resp.status == 200
    assert png_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert png_resp.headers["Content-Type"].startswith("image/png")
    assert "Content-Disposition" not in png_resp.headers


@pytest.mark.anyio
async def test_human_data_route_redirects_pdf_to_viewer(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "bundle"
    nested.mkdir(parents=True)
    (nested / "report.pdf").write_bytes(b"pdf")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/test-vault/data/bundle/report.pdf",
            headers={"Authorization": f"Bearer {TOKEN}"},
            allow_redirects=False,
        )

    assert resp.status == 303
    assert resp.headers["Location"] == "/test-vault/view-data/bundle/report.pdf"


@pytest.mark.anyio
async def test_raw_pdf_data_route_preserves_attachment_policy(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "bundle"
    nested.mkdir(parents=True)
    (nested / "report.pdf").write_bytes(b"pdf")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data/bundle/report.pdf",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        body = await resp.read()

    assert resp.status == 200
    assert body == b"pdf"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["Content-Type"].startswith("application/octet-stream")
    assert 'filename="report.pdf"' in resp.headers["Content-Disposition"]


@pytest.mark.anyio
async def test_get_pdf_annotations_returns_empty_document_for_existing_pdf(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "report.pdf").write_bytes(b"pdf")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data-annotations/report.pdf",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        payload = await resp.json()

    assert resp.status == 200
    assert payload == {"version": 1, "source_path": "report.pdf", "annotations": []}


@pytest.mark.anyio
async def test_put_pdf_annotations_persists_sidecar_outside_data_dir(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "reports" / "한글 report.pdf"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"pdf")
    annotation_doc = {
        "annotations": [
            {
                "id": "area-1",
                "type": "area",
                "rects": [
                    {"page": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
                ],
                "comment": "important table",
                "created_at": "2026-06-29T08:00:00Z",
                "updated_at": "2026-06-29T08:00:00Z",
            }
        ]
    }

    async with TestClient(TestServer(app)) as client:
        put_resp = await client.put(
            "/api/v1/vault/test-vault/data-annotations/reports/%ED%95%9C%EA%B8%80%20report.pdf",
            json=annotation_doc,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        saved = await put_resp.json()
        get_resp = await client.get(
            "/api/v1/vault/test-vault/data-annotations/reports/%ED%95%9C%EA%B8%80%20report.pdf",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        loaded = await get_resp.json()

    assert put_resp.status == 200
    assert get_resp.status == 200
    assert saved == loaded
    assert saved["version"] == 1
    assert saved["source_path"] == "reports/한글 report.pdf"
    assert saved["annotations"] == annotation_doc["annotations"]
    sidecar_name = sha256("reports/한글 report.pdf".encode("utf-8")).hexdigest() + ".json"
    assert (tmp_vault.path / ".pkm" / "data-annotations" / sidecar_name).is_file()
    assert not (tmp_vault.data_dir / ".pkm-annotations" / sidecar_name).exists()


@pytest.mark.anyio
async def test_pdf_annotations_reject_non_pdf_target(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "report.md").write_text("# report", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/vault/test-vault/data-annotations/report.md",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status == 415


@pytest.mark.anyio
async def test_pdf_annotations_reject_invalid_payload_without_corrupting_sidecar(
    app,
    tmp_vault: VaultConfig,
) -> None:
    (tmp_vault.data_dir / "report.pdf").write_bytes(b"pdf")
    valid_doc = {
        "annotations": [
            {
                "id": "text-1",
                "type": "text",
                "rects": [
                    {"page": 2, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
                ],
                "quote": "selected words",
                "comment": "note",
                "created_at": "2026-06-29T08:00:00Z",
                "updated_at": "2026-06-29T08:00:00Z",
            }
        ]
    }
    invalid_doc = {
        "annotations": [
            {
                "id": "bad",
                "type": "area",
                "rects": [
                    {"page": 0, "x": 1.2, "y": 0.2, "width": 0, "height": 0.4}
                ],
            }
        ]
    }

    async with TestClient(TestServer(app)) as client:
        ok = await client.put(
            "/api/v1/vault/test-vault/data-annotations/report.pdf",
            json=valid_doc,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        bad = await client.put(
            "/api/v1/vault/test-vault/data-annotations/report.pdf",
            json=invalid_doc,
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        loaded_resp = await client.get(
            "/api/v1/vault/test-vault/data-annotations/report.pdf",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        loaded = await loaded_resp.json()

    assert ok.status == 200
    assert bad.status == 400
    assert loaded["annotations"] == valid_doc["annotations"]


@pytest.mark.anyio
async def test_get_nested_data_file_preserves_api_download_headers(
    app,
    tmp_vault: VaultConfig,
) -> None:
    nested = tmp_vault.data_dir / "bundle"
    nested.mkdir(parents=True)
    (nested / "page.html").write_text("<script></script>", encoding="utf-8")

    async with TestClient(TestServer(app)) as client:
        html_resp = await client.get(
            "/api/v1/vault/test-vault/data/bundle/page.html",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert html_resp.status == 200
    assert html_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert html_resp.headers["Content-Type"].startswith("application/octet-stream")
    assert 'filename="page.html"' in html_resp.headers["Content-Disposition"]


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
