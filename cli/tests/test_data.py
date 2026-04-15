"""Tests for pkm data add/rm commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from pkm.cli import main
from pkm.config import VaultConfig


@pytest.fixture
def cli_runner(monkeypatch, tmp_vault: VaultConfig):
    """Return a callable that invokes main with tmp_vault injected."""
    runner = CliRunner()

    def invoke(*args: str):
        monkeypatch.setattr(
            "pkm.config.discover_vaults",
            lambda *a, **kw: {"test-vault": tmp_vault},
        )
        return runner.invoke(
            main, ["--vault", "test-vault", *args], catch_exceptions=False
        )

    return invoke


class TestDataAdd:
    def test_add_local_file(self, cli_runner, tmp_vault: VaultConfig, tmp_path: Path):
        """Local path source should be copied to data dir."""
        src = tmp_path / "report.pdf"
        src.write_bytes(b"fake-pdf-content")

        result = cli_runner("data", "add", "report.pdf", str(src))

        assert result.exit_code == 0
        dest = tmp_vault.data_dir / "report.pdf"
        assert dest.exists()
        assert dest.read_bytes() == b"fake-pdf-content"

    def test_add_local_file_preserves_metadata(
        self, cli_runner, tmp_vault: VaultConfig, tmp_path: Path
    ):
        """copy2 should preserve file metadata (mtime)."""
        src = tmp_path / "data.csv"
        src.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

        result = cli_runner("data", "add", "data.csv", str(src))
        assert result.exit_code == 0

        dest = tmp_vault.data_dir / "data.csv"
        # mtime should be close (copy2 preserves it)
        assert abs(src.stat().st_mtime - dest.stat().st_mtime) < 2

    def test_add_refuses_overwrite_by_default(
        self, cli_runner, tmp_vault: VaultConfig, tmp_path: Path
    ):
        """Should fail if dest file already exists without --force."""
        existing = tmp_vault.data_dir / "dup.txt"
        existing.write_text("original", encoding="utf-8")

        src = tmp_path / "dup.txt"
        src.write_text("new", encoding="utf-8")

        result = cli_runner("data", "add", "dup.txt", str(src))

        assert result.exit_code != 0
        assert "already exists" in result.output
        # Original content preserved
        assert existing.read_text(encoding="utf-8") == "original"

    def test_add_force_overwrites(
        self, cli_runner, tmp_vault: VaultConfig, tmp_path: Path
    ):
        """--force should overwrite existing file."""
        existing = tmp_vault.data_dir / "dup.txt"
        existing.write_text("original", encoding="utf-8")

        src = tmp_path / "dup.txt"
        src.write_text("new", encoding="utf-8")

        result = cli_runner("data", "add", "dup.txt", str(src), "--force")

        assert result.exit_code == 0
        assert existing.read_text(encoding="utf-8") == "new"

    def test_add_source_not_found(self, cli_runner):
        """Should fail if local source path doesn't exist."""
        result = cli_runner("data", "add", "x.pdf", "/nonexistent/file.pdf")

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_add_source_is_directory(self, cli_runner, tmp_path: Path):
        """Should fail if source is a directory, not a file."""
        src_dir = tmp_path / "somedir"
        src_dir.mkdir()

        result = cli_runner("data", "add", "x.pdf", str(src_dir))

        assert result.exit_code != 0
        assert "not a file" in result.output

    def test_add_url_download(self, cli_runner, tmp_vault: VaultConfig):
        """URL source should be downloaded to data dir."""
        fake_content = b"downloaded-content"

        def mock_urlretrieve(url, dest):
            Path(dest).write_bytes(fake_content)

        with patch("pkm.commands.data.urllib.request.urlretrieve", mock_urlretrieve):
            result = cli_runner(
                "data", "add", "paper.pdf", "https://example.com/paper.pdf"
            )

        assert result.exit_code == 0
        dest = tmp_vault.data_dir / "paper.pdf"
        assert dest.exists()
        assert dest.read_bytes() == fake_content

    def test_add_url_download_failure_cleans_up(
        self, cli_runner, tmp_vault: VaultConfig
    ):
        """Failed download should not leave a partial file."""
        import urllib.error

        def mock_urlretrieve(url, dest):
            # Write partial file, then raise
            Path(dest).write_bytes(b"partial")
            raise urllib.error.URLError("connection refused")

        with patch("pkm.commands.data.urllib.request.urlretrieve", mock_urlretrieve):
            result = cli_runner(
                "data", "add", "fail.pdf", "https://example.com/fail.pdf"
            )

        assert result.exit_code != 0
        assert "Download failed" in result.output
        assert not (tmp_vault.data_dir / "fail.pdf").exists()

    def test_add_creates_data_dir_if_missing(
        self, cli_runner, tmp_vault: VaultConfig, tmp_path: Path
    ):
        """data dir should be auto-created if it doesn't exist."""
        import shutil

        shutil.rmtree(tmp_vault.data_dir)
        assert not tmp_vault.data_dir.exists()

        src = tmp_path / "new.txt"
        src.write_text("hello", encoding="utf-8")

        result = cli_runner("data", "add", "new.txt", str(src))

        assert result.exit_code == 0
        assert (tmp_vault.data_dir / "new.txt").exists()


class TestDataRm:
    def test_rm_existing_file(self, cli_runner, tmp_vault: VaultConfig):
        """Should remove a file from data dir."""
        target = tmp_vault.data_dir / "old.txt"
        target.write_text("delete me", encoding="utf-8")

        result = cli_runner("data", "rm", "old.txt")

        assert result.exit_code == 0
        assert "Removed" in result.output
        assert not target.exists()

    def test_rm_nonexistent_file(self, cli_runner):
        """Should fail for missing file."""
        result = cli_runner("data", "rm", "ghost.txt")

        assert result.exit_code != 0
        assert "not found" in result.output


class TestDataList:
    def test_list_empty(self, cli_runner, tmp_vault: VaultConfig):
        """No-subcommand should list data files; empty dir shows message."""
        # Clear data dir
        for f in tmp_vault.data_dir.iterdir():
            f.unlink()

        result = cli_runner("data")
        assert result.exit_code == 0
        assert "No data files" in result.output

    def test_list_files(self, cli_runner, tmp_vault: VaultConfig):
        """Should list files with sizes."""
        (tmp_vault.data_dir / "a.txt").write_text("hello", encoding="utf-8")
        (tmp_vault.data_dir / "b.pdf").write_bytes(b"x" * 2048)

        result = cli_runner("data")
        assert result.exit_code == 0
        assert "a.txt" in result.output
        assert "b.pdf" in result.output
