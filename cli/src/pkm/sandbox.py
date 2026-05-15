import sys
import os
from pathlib import Path


class SandboxViolation(Exception):
    pass


def drop_privileges() -> None:
    if hasattr(os, "getuid") and os.getuid() == 0:
        try:
            import pwd

            nobody = pwd.getpwnam("nobody")
            os.setgroups([])
            os.setgid(nobody.pw_gid)
            os.setuid(nobody.pw_uid)
        except Exception as e:
            raise SandboxViolation(f"Failed to drop privileges: {e}")

    _ = os.umask(0o077)


_state: dict = {"vault_path": None, "installed": False}
_NATIVE_LOAD_EVENTS = {"ctypes.dlopen", "ctypes.dlsym", "mmap.__new__"}
_TRUSTED_NATIVE_PROFILES = {"trusted-native", "trusted_native"}

_allowed_read_prefixes = [
    Path(sys.prefix).resolve(),
    Path(sys.base_prefix).resolve(),
    Path(__file__).parent.parent.parent.resolve(),
    Path.home().resolve(),
]

_allowed_files = {
    "/etc/localtime",
    "/etc/timezone",
    "/etc/resolv.conf",
    "/etc/hosts",
}


def _sandbox_profile() -> str:
    return os.environ.get("PKM_WORKER_SANDBOX_PROFILE", "strict").strip().lower()


def _native_load_allowed() -> bool:
    return _sandbox_profile() in _TRUSTED_NATIVE_PROFILES


def _workflow_index_subprocess_allowed(args: tuple[object, ...]) -> bool:
    """Permit the worker's isolated graph/index rebuild and nothing else."""
    if not _native_load_allowed() or len(args) < 4:
        return False

    executable, cmd_args, cwd, env = args[:4]
    if not isinstance(cmd_args, (list, tuple)):
        return False

    try:
        cmd = [os.fsdecode(part) for part in cmd_args]
    except TypeError:
        return False

    if len(cmd) != 6 or cmd[1:4] != ["-m", "pkm", "--vault"] or cmd[5] != "index":
        return False
    if not cmd[4] or cmd[4].startswith("-") or "/" in cmd[4]:
        return False

    try:
        expected_executable = Path(sys.executable).resolve()
        if Path(os.fsdecode(executable)).resolve() != expected_executable:
            return False
        if Path(cmd[0]).resolve() != expected_executable:
            return False
    except Exception:
        return False

    vault_path = _state["vault_path"]
    if vault_path is None or cwd is None or not isinstance(env, dict):
        return False

    try:
        cwd_path = Path(os.fsdecode(cwd)).resolve()
        root_path = Path(os.fsdecode(env.get("PKM_VAULTS_ROOT", ""))).resolve()
    except Exception:
        return False

    return cwd_path == vault_path and root_path == vault_path.parent.resolve()


def setup_sandbox(vault_dir: Path | str) -> None:
    _state["vault_path"] = Path(vault_dir).resolve()

    if _state["installed"]:
        return

    def audit_hook(event: str, args: tuple[object, ...]):
        if event == "subprocess.Popen" and not _workflow_index_subprocess_allowed(
            args
        ):
            raise SandboxViolation(f"Command execution blocked: {event}")

        if event in {"os.system", "os.exec", "os.posix_spawn", "os.spawn"}:
            raise SandboxViolation(f"Command execution blocked: {event}")

        if event in _NATIVE_LOAD_EVENTS and not _native_load_allowed():
            raise SandboxViolation(f"Dangerous operation blocked: {event}")

        if event == "open":
            path = args[0]
            mode = str(args[1]) if len(args) > 1 else "r"

            if not isinstance(path, (str, bytes, Path)):
                return

            try:
                target_path = Path(os.fsdecode(path)).resolve()
            except Exception:
                return

            vault_path = _state["vault_path"]
            is_in_vault = vault_path is not None and target_path.is_relative_to(
                vault_path
            )
            is_dev = str(target_path).startswith("/dev/")

            if "w" in mode or "a" in mode or "+" in mode:
                if not is_in_vault and not is_dev:
                    raise SandboxViolation(
                        f"Write access denied outside vault: {target_path}"
                    )
            else:
                if not is_in_vault and not is_dev:
                    is_allowed_sys = any(
                        target_path.is_relative_to(prefix)
                        for prefix in _allowed_read_prefixes
                    )
                    if not is_allowed_sys and str(target_path) not in _allowed_files:
                        raise SandboxViolation(
                            f"Read access denied outside vault and allowed prefixes: {target_path}"
                        )

    sys.addaudithook(audit_hook)
    _state["installed"] = True
    drop_privileges()
