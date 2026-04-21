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


def setup_sandbox(vault_dir: Path | str) -> None:
    vault_path = Path(vault_dir).resolve()

    allowed_read_prefixes = [
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path(__file__).parent.parent.parent.resolve(),
        Path.home().resolve(),
    ]

    def audit_hook(event: str, args: tuple[object, ...]):

        if event in {
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "os.spawn",
            "subprocess.Popen",
        }:
            raise SandboxViolation(f"Command execution blocked: {event}")

        if event in {"ctypes.dlopen", "ctypes.dlsym", "mmap.__new__"}:
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

            is_in_vault = target_path.is_relative_to(vault_path)
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
                        for prefix in allowed_read_prefixes
                    )

                    allowed_files = {
                        "/etc/localtime",
                        "/etc/timezone",
                        "/etc/resolv.conf",
                        "/etc/hosts",
                    }

                    if not is_allowed_sys and str(target_path) not in allowed_files:
                        raise SandboxViolation(
                            f"Read access denied outside vault and allowed prefixes: {target_path}"
                        )

    sys.addaudithook(audit_hook)
    drop_privileges()
