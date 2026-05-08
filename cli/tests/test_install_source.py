"""Scenario tests for setup/update install source resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

import pkm._install_source as install_source


def test_find_local_cli_dir_returns_source_checkout() -> None:
    """Running from this repo resolves the editable CLI checkout."""
    cli_dir = install_source.find_local_cli_dir()

    assert cli_dir is not None
    assert cli_dir.name == "cli"
    assert (cli_dir / "pyproject.toml").exists()


def test_cli_source_uses_local_checkout_without_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local installs yield a persistent editable source and skip network/tar handling."""
    cli_dir = tmp_path / "repo" / "cli"
    cli_dir.mkdir(parents=True)
    network_calls: list[str] = []
    tar_calls: list[str] = []

    monkeypatch.setattr(install_source, "find_local_cli_dir", lambda: cli_dir)
    monkeypatch.setattr(
        install_source.urllib.request,
        "urlretrieve",
        lambda *_args: network_calls.append("download"),
    )
    monkeypatch.setattr(
        install_source.tarfile,
        "open",
        lambda *_args, **_kwargs: tar_calls.append("tar"),
    )

    with install_source.cli_source() as (source_dir, is_local):
        assert source_dir == cli_dir
        assert is_local is True

    assert network_calls == []
    assert tar_calls == []


class _FakeTemporaryDirectory:
    def __init__(self, path: Path, events: list[str]) -> None:
        self.path = path
        self.events = events

    def __enter__(self) -> str:
        self.path.mkdir(parents=True, exist_ok=True)
        self.events.append("enter")
        return str(self.path)

    def __exit__(self, *_exc_info) -> None:
        self.events.append("exit")


class _FakeTarFile:
    def __init__(self, extract) -> None:
        self._extract = extract

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info) -> None:
        return None

    def extractall(self, target: str) -> None:
        self._extract(Path(target))


def test_cli_source_downloads_tarball_and_ignores_macosx_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-local installs download a transient tarball and yield the extracted CLI dir."""
    temp_dir = tmp_path / "download"
    events: list[str] = []
    downloads: list[tuple[str, Path]] = []
    tar_opens: list[tuple[Path, str]] = []

    def fake_urlretrieve(url: str, destination: Path) -> None:
        downloads.append((url, destination))
        destination.write_text("placeholder", encoding="utf-8")

    def fake_tar_open(path: Path, mode: str):
        tar_opens.append((path, mode))

        def extract(target: Path) -> None:
            (target / "__MACOSX").mkdir()
            (target / "pkm-main" / "cli").mkdir(parents=True)

        return _FakeTarFile(extract)

    monkeypatch.setattr(install_source, "find_local_cli_dir", lambda: None)
    monkeypatch.setattr(
        install_source.tempfile,
        "TemporaryDirectory",
        lambda: _FakeTemporaryDirectory(temp_dir, events),
    )
    monkeypatch.setattr(install_source.urllib.request, "urlretrieve", fake_urlretrieve)
    monkeypatch.setattr(install_source.tarfile, "open", fake_tar_open)

    with install_source.cli_source() as (source_dir, is_local):
        assert source_dir == temp_dir / "pkm-main" / "cli"
        assert is_local is False
        assert events == ["enter"]

    assert events == ["enter", "exit"]
    assert downloads == [
        (
            f"https://github.com/{install_source.GITHUB_REPO}/archive/refs/heads/main.tar.gz",
            temp_dir / "pkm.tar.gz",
        )
    ]
    assert tar_opens == [(temp_dir / "pkm.tar.gz", "r:gz")]


def test_cli_source_rejects_malformed_tarball_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A downloaded archive with no source directory fails before install can continue."""
    temp_dir = tmp_path / "download"

    def fake_tar_open(_path: Path, _mode: str):
        return _FakeTarFile(lambda target: (target / "__MACOSX").mkdir())

    monkeypatch.setattr(install_source, "find_local_cli_dir", lambda: None)
    monkeypatch.setattr(
        install_source.tempfile,
        "TemporaryDirectory",
        lambda: _FakeTemporaryDirectory(temp_dir, []),
    )
    monkeypatch.setattr(
        install_source.urllib.request,
        "urlretrieve",
        lambda _url, destination: destination.write_text(
            "placeholder", encoding="utf-8"
        ),
    )
    monkeypatch.setattr(install_source.tarfile, "open", fake_tar_open)

    with pytest.raises(RuntimeError, match="Unexpected tarball layout"):
        with install_source.cli_source():
            raise AssertionError("malformed tarball must not yield a source")
