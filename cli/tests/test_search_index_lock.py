"""Search index builds acquire a vault-scoped lock."""

from __future__ import annotations

from contextlib import contextmanager

from pkm.config import VaultConfig
from pkm.search_engine import VectorIndex


def test_build_index_acquires_vault_scoped_lock(tmp_vault: VaultConfig, monkeypatch) -> None:
    from pkm import search_engine

    events = []
    sentinel = VectorIndex(model="fake", created_at="now", entries=[])

    @contextmanager
    def fake_index_build_lock(vault):
        events.append(("enter", vault))
        try:
            yield
        finally:
            events.append(("exit", vault))

    def fake_unlocked_build(vault, model_name="all-MiniLM-L6-v2"):
        events.append(("build", vault, model_name))
        return sentinel

    monkeypatch.setattr(search_engine, "index_build_lock", fake_index_build_lock)
    monkeypatch.setattr(search_engine, "_build_index_unlocked", fake_unlocked_build)

    result = search_engine.build_index(tmp_vault, model_name="fake-model")

    assert result is sentinel
    assert events == [
        ("enter", tmp_vault),
        ("build", tmp_vault, "fake-model"),
        ("exit", tmp_vault),
    ]
