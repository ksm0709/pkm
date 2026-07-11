"""Authentication helpers and middleware for the PKM web server.

Browser auth is password login -> HttpOnly session cookie.  The legacy bearer
token remains valid for CLI/curl/MCP callers. Query-string tokens are rejected.
"""

from __future__ import annotations

import hmac
import hashlib
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable

from aiohttp import web

from pkm.config import WebConfig, discover_vaults


PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/login",
        "/manifest.webmanifest",
        "/service-worker.js",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
    }
)
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/_app/",
    "/favicon",
    "/icons/",
)
SESSION_COOKIE_NAME = "pkm_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
_PASSWORD_ALG = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 240_000


def _load_token(token_path: Path) -> str:
    """Read and strip the bearer token from *token_path*.

    Called once per process (cached).  Raises RuntimeError if the file is
    missing or empty so the server fails fast on misconfiguration.
    """
    if not token_path.exists():
        raise RuntimeError(
            f"Web token file not found: {token_path}. "
            "Generate one with: pkm setup --web"
        )
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"Web token file is empty: {token_path}")
    return token


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return a salted PBKDF2-SHA256 password hash string."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
    )
    return f"{_PASSWORD_ALG}${_PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verify for hashes produced by :func:`hash_password`."""
    try:
        alg, iterations_raw, salt_hex, expected_hex = encoded.strip().split("$", 3)
        if alg != _PASSWORD_ALG:
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _load_password_hash(password_path: Path) -> str | None:
    if not password_path.exists():
        return None
    value = password_path.read_text(encoding="utf-8").strip()
    return value or None


def _session_secret(token: str, password_hash: str, reset_value: str) -> bytes:
    return hashlib.sha256(
        f"{token}\0{password_hash}\0{reset_value}".encode("utf-8")
    ).digest()


def _load_reset_value(reset_path: Path) -> str:
    if not reset_path.exists():
        return ""
    return reset_path.read_text(encoding="utf-8").strip()


def create_session_cookie_value(
    *,
    token: str,
    password_hash: str,
    reset_value: str = "",
    now: int | None = None,
) -> str:
    """Create a stateless, signed 30-day browser session token."""
    issued_at = int(time.time()) if now is None else now
    nonce = os.urandom(16).hex()
    body = f"v1${issued_at}${nonce}"
    sig = hmac.new(
        _session_secret(token, password_hash, reset_value),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}${sig}"


def verify_session_cookie_value(
    value: str,
    *,
    token: str,
    password_hash: str,
    reset_value: str = "",
    now: int | None = None,
) -> bool:
    """Verify a session token and enforce the 30-day max age."""
    try:
        version, issued_raw, nonce, provided_sig = value.split("$", 3)
        if version != "v1" or not nonce:
            return False
        issued_at = int(issued_raw)
    except (ValueError, TypeError):
        return False

    current = int(time.time()) if now is None else now
    if issued_at > current + 60:
        return False
    if current - issued_at > SESSION_MAX_AGE_SECONDS:
        return False

    body = f"v1${issued_at}${nonce}"
    expected = hmac.new(
        _session_secret(token, password_hash, reset_value),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided_sig, expected)


def _is_public_request(request: web.Request) -> bool:
    path = request.path
    return path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES)


def make_auth_middleware(web_config: WebConfig) -> web.middleware:
    """Return an aiohttp middleware factory bound to *web_config*.

    The token file is read exactly once (on first authenticated request) and
    cached for the lifetime of the process.
    """

    @lru_cache(maxsize=1)
    def _get_token() -> str:
        return _load_token(web_config.token_path)

    @lru_cache(maxsize=1)
    def _get_password_hash() -> str | None:
        return _load_password_hash(web_config.password_path)

    @web.middleware
    async def auth_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        """Authenticate every incoming request.

        Precedence:
        1. ``Authorization: Bearer ***`` header — valid on all routes.
        2. signed ``pkm_session`` cookie — browser route.
        """
        if _is_public_request(request):
            return await handler(request)

        expected = _get_token()

        # --- Bearer header (canonical, accepted everywhere) ---
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided = auth_header[len("Bearer ") :]
            if hmac.compare_digest(provided, expected):
                return await handler(request)
            return web.Response(status=401, text="Invalid token")


        # --- Browser session cookie ---
        password_hash = _get_password_hash()
        session_cookie = request.cookies.get(SESSION_COOKIE_NAME, "")
        if password_hash and session_cookie:
            reset_value = _load_reset_value(web_config.session_reset_path)
            if verify_session_cookie_value(
                session_cookie,
                token=expected,
                password_hash=password_hash,
                reset_value=reset_value,
            ):
                return await handler(request)

        return web.Response(
            status=401,
            text="Unauthorized",
            headers={"WWW-Authenticate": 'Bearer realm="pkm"'},
        )

    return auth_middleware


def make_login_handler(
    web_config: WebConfig,
) -> Callable[[web.Request], Awaitable[web.Response]]:
    """Return the public password-login handler bound to *web_config*."""

    @lru_cache(maxsize=1)
    def _get_token() -> str:
        return _load_token(web_config.token_path)

    @lru_cache(maxsize=1)
    def _get_password_hash() -> str | None:
        return _load_password_hash(web_config.password_path)

    async def login(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            raise web.HTTPBadRequest(reason="Invalid JSON body")

        provided = str(data.get("password", ""))
        password_hash = _get_password_hash()
        if password_hash is None:
            raise web.HTTPServiceUnavailable(reason="Password login not configured")
        if not provided or not verify_password(provided, password_hash):
            return web.json_response({"error": "invalid_password"}, status=401)

        reset_value = _load_reset_value(web_config.session_reset_path)
        cookie_value = create_session_cookie_value(
            token=_get_token(),
            password_hash=password_hash,
            reset_value=reset_value,
        )
        vaults = [
            {"name": vault.name, "path": str(vault.path)}
            for vault in discover_vaults().values()
        ]
        response = web.json_response({"ok": True, "vaults": vaults})
        remember = bool(data.get("remember", True))
        cookie_kwargs = {
            "httponly": True,
            "samesite": "Lax",
            "path": "/",
        }
        if remember:
            cookie_kwargs["max_age"] = SESSION_MAX_AGE_SECONDS
        response.set_cookie(SESSION_COOKIE_NAME, cookie_value, **cookie_kwargs)
        return response

    return login


async def logout(request: web.Request) -> web.Response:
    """Clear the browser session cookie."""
    response = web.json_response({"ok": True})
    response.del_cookie(SESSION_COOKIE_NAME, path="/")
    return response
