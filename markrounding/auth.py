"""Single-admin auth: PBKDF2 password hash + short-lived HS256 JWT.

Simplified from tOPAC's auth stack — one admin account whose password hash
lives in the environment, no user store. Login is rate limited per IP with
a small in-process fixed-window counter (the /api/* routes bypass any edge
PoW gate, so this limiter is load-bearing, not defense-in-depth).
"""

import hashlib
import hmac
import secrets
import time

import jwt
from fastapi import HTTPException
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer

from . import config

_PBKDF2_ITERATIONS = 260_000

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_admin_token() -> str:
    now = int(time.time())
    payload = {"sub": "admin", "iat": now, "exp": now + config.ADMIN_TOKEN_TTL_SECONDS}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def require_admin(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Inloggning krävs")
    token = auth[7:].strip()
    try:
        jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Ogiltig eller utgången session")


# --- login rate limiting (fixed window, in-process) ---

_attempts: dict[str, tuple[int, float]] = {}
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 60.0


def client_ip(request: Request) -> str:
    # Behind edge-Caddy uvicorn runs with --proxy-headers, so request.client
    # already reflects X-Forwarded-For.
    return request.client.host if request.client else "unknown"


def check_login_rate_limit(request: Request) -> None:
    ip = client_ip(request)
    now = time.monotonic()
    count, window_start = _attempts.get(ip, (0, now))
    if now - window_start > LOGIN_WINDOW_SECONDS:
        count, window_start = 0, now
    if count >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429, detail="För många inloggningsförsök. Vänta en minut."
        )
    _attempts[ip] = (count + 1, window_start)


def reset_rate_limit() -> None:
    _attempts.clear()


_dummy_hash = hash_password("timing-equalizer")


def verify_admin_login(password: str) -> bool:
    ok = verify_password(password, config.ADMIN_PASSWORD_HASH)
    if not ok:
        # Equalize timing whether or not the stored hash parses.
        verify_password(password, _dummy_hash)
    return ok
