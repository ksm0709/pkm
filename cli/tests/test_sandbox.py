"""Scenario tests for sandbox privilege and audit-hook policy."""

from __future__ import annotations

import sys
import types

import pytest

from pkm import sandbox


@pytest.fixture(autouse=True)
def reset_sandbox_state():
    old_state = dict(sandbox._state)
    sandbox._state.update({"vault_path": None, "installed": False})
    yield
    sandbox._state.clear()
    sandbox._state.update(old_state)


def test_drop_privileges_non_root_only_sets_restrictive_umask(monkeypatch) -> None:
    """Non-root workers do not resolve nobody but still tighten file permissions."""
    umasks = []
    monkeypatch.setattr(sandbox.os, "getuid", lambda: 1000)
    monkeypatch.setattr(sandbox.os, "umask", lambda mask: umasks.append(mask))
    monkeypatch.setitem(sys.modules, "pwd", None)

    sandbox.drop_privileges()

    assert umasks == [0o077]


def test_drop_privileges_root_switches_to_nobody(monkeypatch) -> None:
    """Root workers drop groups, gid, uid, then set a restrictive umask."""
    calls = []
    fake_pwd = types.SimpleNamespace(
        getpwnam=lambda name: types.SimpleNamespace(pw_gid=65534, pw_uid=65534)
    )
    monkeypatch.setitem(sys.modules, "pwd", fake_pwd)
    monkeypatch.setattr(sandbox.os, "getuid", lambda: 0)
    monkeypatch.setattr(
        sandbox.os, "setgroups", lambda groups: calls.append(("groups", groups))
    )
    monkeypatch.setattr(sandbox.os, "setgid", lambda gid: calls.append(("gid", gid)))
    monkeypatch.setattr(sandbox.os, "setuid", lambda uid: calls.append(("uid", uid)))
    monkeypatch.setattr(sandbox.os, "umask", lambda mask: calls.append(("umask", mask)))

    sandbox.drop_privileges()

    assert calls == [
        ("groups", []),
        ("gid", 65534),
        ("uid", 65534),
        ("umask", 0o077),
    ]


def test_drop_privileges_root_failure_raises_sandbox_violation(monkeypatch) -> None:
    """Privilege-drop errors are surfaced as SandboxViolation."""
    fake_pwd = types.SimpleNamespace(
        getpwnam=lambda name: types.SimpleNamespace(pw_gid=65534, pw_uid=65534)
    )
    monkeypatch.setitem(sys.modules, "pwd", fake_pwd)
    monkeypatch.setattr(sandbox.os, "getuid", lambda: 0)
    monkeypatch.setattr(sandbox.os, "setgroups", lambda groups: None)
    monkeypatch.setattr(
        sandbox.os,
        "setgid",
        lambda gid: (_ for _ in ()).throw(OSError("denied")),
    )

    with pytest.raises(sandbox.SandboxViolation, match="Failed to drop privileges"):
        sandbox.drop_privileges()


def test_setup_sandbox_installs_once_but_updates_vault_path(
    monkeypatch, tmp_path
) -> None:
    """Repeated setup does not install another hook but does switch the active vault."""
    hooks = []
    first_vault = tmp_path / "first"
    second_vault = tmp_path / "second"
    monkeypatch.setattr(sandbox.sys, "addaudithook", lambda hook: hooks.append(hook))
    monkeypatch.setattr(sandbox, "drop_privileges", lambda: None)

    sandbox.setup_sandbox(first_vault)
    sandbox.setup_sandbox(second_vault)

    assert len(hooks) == 1
    assert sandbox._state["installed"] is True
    assert sandbox._state["vault_path"] == second_vault.resolve()


def test_audit_hook_blocks_command_and_dangerous_operations(
    monkeypatch, tmp_path
) -> None:
    """The captured audit hook rejects process execution and dangerous native APIs."""
    hooks = []
    monkeypatch.setattr(sandbox.sys, "addaudithook", lambda hook: hooks.append(hook))
    monkeypatch.setattr(sandbox, "drop_privileges", lambda: None)

    sandbox.setup_sandbox(tmp_path / "vault")
    hook = hooks[0]

    for event in ("os.system", "os.exec", "subprocess.Popen"):
        with pytest.raises(sandbox.SandboxViolation, match="Command execution blocked"):
            hook(event, ())

    for event in ("ctypes.dlopen", "ctypes.dlsym", "mmap.__new__"):
        with pytest.raises(
            sandbox.SandboxViolation, match="Dangerous operation blocked"
        ):
            hook(event, ())


def test_audit_hook_enforces_write_and_read_boundaries(monkeypatch, tmp_path) -> None:
    """The captured audit hook allows vault/dev/system reads and blocks outside access."""
    hooks = []
    vault = tmp_path / "vault"
    vault.mkdir()
    inside = vault / "note.md"
    outside = tmp_path / "outside.md"
    allowed_prefix = tmp_path / "allowed-prefix"
    allowed_prefix.mkdir()
    allowed_read = allowed_prefix / "module.py"
    monkeypatch.setattr(sandbox.sys, "addaudithook", lambda hook: hooks.append(hook))
    monkeypatch.setattr(sandbox, "drop_privileges", lambda: None)
    monkeypatch.setattr(sandbox, "_allowed_read_prefixes", [allowed_prefix.resolve()])

    sandbox.setup_sandbox(vault)
    hook = hooks[0]

    hook("open", (inside, "w"))
    hook("open", (inside, "r"))
    hook("open", ("/dev/null", "w"))
    hook("open", (allowed_read, "r"))
    hook("open", ("/etc/hosts", "r"))

    with pytest.raises(sandbox.SandboxViolation, match="Write access denied"):
        hook("open", (outside, "w"))

    with pytest.raises(sandbox.SandboxViolation, match="Read access denied"):
        hook("open", (outside, "r"))


def test_audit_hook_ignores_non_path_and_unresolvable_open_args(
    monkeypatch, tmp_path
) -> None:
    """Non-path open events and path decoding failures are ignored."""
    hooks = []
    monkeypatch.setattr(sandbox.sys, "addaudithook", lambda hook: hooks.append(hook))
    monkeypatch.setattr(sandbox, "drop_privileges", lambda: None)

    sandbox.setup_sandbox(tmp_path / "vault")
    hook = hooks[0]

    hook("open", (object(), "r"))

    class BadPath:
        def __fspath__(self):
            raise OSError("bad path")

    hook("open", (BadPath(), "r"))


def test_non_open_non_sensitive_events_are_ignored(monkeypatch, tmp_path) -> None:
    """Unrelated audit events are not blocked by the sandbox policy."""
    hooks = []
    monkeypatch.setattr(sandbox.sys, "addaudithook", lambda hook: hooks.append(hook))
    monkeypatch.setattr(sandbox, "drop_privileges", lambda: None)

    sandbox.setup_sandbox(tmp_path / "vault")

    hooks[0]("import", ("json",))
