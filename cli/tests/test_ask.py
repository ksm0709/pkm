import os
import json
import socket
import time
import subprocess
import pytest
from pkm.config import VaultConfig
from pkm.search_engine import build_index


@pytest.fixture
def daemon_env(tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    notes_dir = vault_dir / "notes"
    notes_dir.mkdir()

    note_path = notes_dir / "test-note.md"
    note_path.write_text(
        "---\nid: test-note\ntags: [test]\n---\nThe secret password is 'hunter2'.\n"
    )

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PKM_TEST_MOCK_LLM", "1")

    vault = VaultConfig(name="test-vault", path=vault_dir)
    monkeypatch.setattr(
        "pkm.config.discover_vaults", lambda root=None: {"test-vault": vault}
    )

    class FakeModel:
        def encode(self, texts, **kwargs):
            import numpy as np

            texts_list = texts if isinstance(texts, list) else [texts]
            return np.array([[0.5] * 384 for _ in texts_list])

    monkeypatch.setattr(
        "pkm.search_engine._require_transformers", lambda name: FakeModel()
    )
    build_index(vault)

    return vault, config_dir


def test_ask_e2e(daemon_env):
    vault, config_dir = daemon_env

    import sys

    env = os.environ.copy()
    env["HOME"] = str(config_dir.parent)
    env["PKM_TEST_MOCK_LLM"] = "1"

    daemon_proc = subprocess.Popen(
        [sys.executable, "-m", "pkm.daemon"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        sock_path = config_dir.parent / ".config" / "pkm" / "daemon.sock"
        for _ in range(50):
            if sock_path.exists():
                break
            time.sleep(0.1)

        assert sock_path.exists(), "Daemon socket not created"

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(str(sock_path))
            req = {
                "action": "ask",
                "query": "What is the secret password?",
                "vault_name": "test-vault",
                "model": "test-model",
            }
            sock.sendall(json.dumps(req).encode("utf-8") + b"\n")

            f = sock.makefile("r", encoding="utf-8")
            resp_line = f.readline()

            assert resp_line
            data = json.loads(resp_line)

            assert "error" not in data

            response_text = (
                data.get("data", {}).get("response", "")
                if "data" in data
                else data.get("response", "")
            )
            assert "hunter2" in response_text
            assert "What is the secret password?" in response_text

    finally:
        daemon_proc.terminate()
        daemon_proc.wait()
