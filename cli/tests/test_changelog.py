"""Scenario tests for changelog source selection and parsing."""

from __future__ import annotations

from io import BytesIO

import pytest

from pkm import changelog


CHANGELOG_TEXT = """# Changelog

## v2.3.0 - Latest

- Latest feature

## v2.2.0 - Previous

- Previous fix

## v2.1.0 - Older

- Older note
"""


class FakeResponse:
    def __init__(self, content: str):
        self._buffer = BytesIO(content.encode("utf-8"))

    def read(self) -> bytes:
        return self._buffer.read()


def test_get_changelog_latest_sections_from_local_file(monkeypatch) -> None:
    """latest_n returns newest local changelog sections without network fallback."""
    monkeypatch.setattr(changelog.Path, "exists", lambda self: True)
    monkeypatch.setattr(
        changelog.Path, "read_text", lambda self, encoding: CHANGELOG_TEXT
    )
    monkeypatch.setattr(
        changelog.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("network fallback should not run"),
    )

    result = changelog.get_changelog(latest_n=2)

    assert "## v2.3.0 - Latest" in result
    assert "## v2.2.0 - Previous" in result
    assert "## v2.1.0 - Older" not in result


def test_get_changelog_since_version_accepts_bare_version(monkeypatch) -> None:
    """since_version returns only sections newer than the matched version."""
    monkeypatch.setattr(changelog.Path, "exists", lambda self: True)
    monkeypatch.setattr(
        changelog.Path, "read_text", lambda self, encoding: CHANGELOG_TEXT
    )
    monkeypatch.setattr(
        changelog.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("network fallback should not run"),
    )

    result = changelog.get_changelog(since_version="2.2.0")

    assert "## v2.3.0 - Latest" in result
    assert "## v2.2.0 - Previous" not in result
    assert "## v2.1.0 - Older" not in result


def test_get_changelog_since_latest_reports_no_new_changes(monkeypatch) -> None:
    """When since_version is the newest section, the changelog reports no changes."""
    monkeypatch.setattr(changelog.Path, "exists", lambda self: True)
    monkeypatch.setattr(
        changelog.Path, "read_text", lambda self, encoding: CHANGELOG_TEXT
    )
    monkeypatch.setattr(
        changelog.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("network fallback should not run"),
    )

    assert changelog.get_changelog(since_version="v2.3.0") == "No new changes."


def test_get_changelog_returns_empty_for_malformed_content(monkeypatch) -> None:
    """Malformed local changelog content yields an empty string."""
    monkeypatch.setattr(changelog.Path, "exists", lambda self: True)
    monkeypatch.setattr(
        changelog.Path,
        "read_text",
        lambda self, encoding: "# Changelog\n\n### not a version\n",
    )
    monkeypatch.setattr(
        changelog.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("network fallback should not run"),
    )

    assert changelog.get_changelog(latest_n=1) == ""


def test_get_changelog_falls_back_to_remote_when_local_missing(monkeypatch) -> None:
    """Remote changelog content is decoded and parsed when no local file exists."""
    monkeypatch.setattr(changelog.Path, "exists", lambda self: False)
    monkeypatch.setattr(
        changelog.urllib.request,
        "urlopen",
        lambda url, timeout: FakeResponse(CHANGELOG_TEXT),
    )

    result = changelog.get_changelog(latest_n=1)

    assert "## v2.3.0 - Latest" in result
    assert "Latest feature" in result
    assert "## v2.2.0 - Previous" not in result


def test_get_changelog_returns_empty_when_all_sources_fail(monkeypatch) -> None:
    """Missing local files and failed remote fetch return an empty changelog."""
    monkeypatch.setattr(changelog.Path, "exists", lambda self: False)
    monkeypatch.setattr(
        changelog.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
    )

    assert changelog.get_changelog(latest_n=1) == ""
