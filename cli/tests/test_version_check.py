"""Scenario tests for release version check caching and network fallbacks."""

from __future__ import annotations

import json
from io import BytesIO
from urllib.error import URLError

from pkm import version_check


class FakeResponse:
    def __init__(self, payload: object):
        self._buffer = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._buffer.read()


def test_parse_version_handles_prefix_and_invalid_values() -> None:
    """Version parsing supports v-prefixed releases and degrades invalid tags."""
    assert version_check._parse_version("v2.10.3") == (2, 10, 3)
    assert version_check._parse_version("1.9.0") == (1, 9, 0)
    assert version_check._parse_version("not-a-version") == (0,)


def test_fetch_latest_decodes_release_and_handles_failures(monkeypatch) -> None:
    """Latest-release fetch returns tag_name and swallows network/JSON failures."""
    calls = []

    def fake_urlopen(url: str, timeout: int):
        calls.append((url, timeout))
        return FakeResponse({"tag_name": "v3.0.0"})

    monkeypatch.setattr(version_check, "urlopen", fake_urlopen)

    assert version_check._fetch_latest() == "v3.0.0"
    assert calls == [
        (
            "https://api.github.com/repos/ksm0709/pkm/releases/latest",
            version_check.FETCH_TIMEOUT,
        )
    ]

    monkeypatch.setattr(
        version_check,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    assert version_check._fetch_latest() is None

    class BadResponse(FakeResponse):
        def __init__(self):
            self._buffer = BytesIO(b"{bad json")

    monkeypatch.setattr(version_check, "urlopen", lambda *args, **kwargs: BadResponse())
    assert version_check._fetch_latest() is None


def test_get_latest_version_uses_fresh_cache_without_network(
    monkeypatch, tmp_path
) -> None:
    """Fresh cache avoids network calls and returns the cached tag."""
    cache_file = tmp_path / "version_check.json"
    cache_file.write_text(
        json.dumps({"latest": "v2.0.0", "checked_at": 1000.0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(version_check, "CACHE_FILE", cache_file)
    monkeypatch.setattr(version_check.time, "time", lambda: 1000.0 + 10)
    monkeypatch.setattr(
        version_check,
        "_fetch_latest",
        lambda: (_ for _ in ()).throw(AssertionError("network should not run")),
    )

    assert version_check.get_latest_version() == "v2.0.0"


def test_get_latest_version_missing_cache_fetches_and_writes(
    monkeypatch, tmp_path
) -> None:
    """Missing cache fetches latest release and writes a new cache record."""
    cache_file = tmp_path / "nested" / "version_check.json"
    monkeypatch.setattr(version_check, "CACHE_FILE", cache_file)
    monkeypatch.setattr(version_check.time, "time", lambda: 2000.0)
    monkeypatch.setattr(version_check, "_fetch_latest", lambda: "v2.1.0")

    assert version_check.get_latest_version() == "v2.1.0"

    cached = json.loads(cache_file.read_text(encoding="utf-8"))
    assert cached == {"latest": "v2.1.0", "checked_at": 2000.0}


def test_get_latest_version_stale_or_malformed_cache_fetches(
    monkeypatch, tmp_path
) -> None:
    """Stale and malformed caches are ignored in favor of a fresh fetch."""
    cache_file = tmp_path / "version_check.json"
    monkeypatch.setattr(version_check, "CACHE_FILE", cache_file)
    monkeypatch.setattr(
        version_check.time, "time", lambda: 1000.0 + version_check.CACHE_TTL + 1
    )

    cache_file.write_text(
        json.dumps({"latest": "v1.0.0", "checked_at": 1000.0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(version_check, "_fetch_latest", lambda: "v2.0.0")
    assert version_check.get_latest_version() == "v2.0.0"

    cache_file.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr(version_check, "_fetch_latest", lambda: "v2.2.0")
    assert version_check.get_latest_version() == "v2.2.0"


def test_get_latest_version_write_failure_still_returns_latest(
    monkeypatch, tmp_path
) -> None:
    """Cache write failures do not hide a fetched latest release."""
    unwritable_cache = tmp_path / "cache-dir"
    unwritable_cache.mkdir()
    monkeypatch.setattr(version_check, "CACHE_FILE", unwritable_cache)
    monkeypatch.setattr(version_check, "_fetch_latest", lambda: "v2.5.0")

    assert version_check.get_latest_version() == "v2.5.0"


def test_get_recent_versions_filters_tags_and_handles_failures(monkeypatch) -> None:
    """Recent release listing filters missing tag names and returns [] on failure."""
    monkeypatch.setattr(
        version_check,
        "urlopen",
        lambda url, timeout: FakeResponse(
            [{"tag_name": "v3.0.0"}, {"name": "draft"}, {"tag_name": "v2.9.0"}]
        ),
    )

    assert version_check.get_recent_versions(n=3) == ["v3.0.0", "v2.9.0"]

    monkeypatch.setattr(
        version_check,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    assert version_check.get_recent_versions() == []


def test_available_update_compares_versions_and_handles_missing_latest(
    monkeypatch,
) -> None:
    """available_update reports only genuinely newer parsed versions."""
    monkeypatch.setattr(version_check, "get_latest_version", lambda: "v2.0.0")
    assert version_check.available_update("v1.9.9") == "v2.0.0"
    assert version_check.available_update("v2.0.0") is None
    assert version_check.available_update("v2.1.0") is None

    monkeypatch.setattr(version_check, "get_latest_version", lambda: None)
    assert version_check.available_update("v1.0.0") is None

    monkeypatch.setattr(version_check, "get_latest_version", lambda: "bad")
    assert version_check.available_update("v1.0.0") is None
