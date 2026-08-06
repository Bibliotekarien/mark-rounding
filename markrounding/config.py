"""Environment-driven configuration, validated at import time.

Mirrors the tOPAC config pattern: hard failure in production when a secret
is missing, warning + dev default in development. All variables use the
MARKROUNDING_ prefix. Error messages are in Swedish (user-facing).
"""

import logging
import os
from pathlib import Path

_log = logging.getLogger("markrounding.config")

_ENV = os.getenv("MARKROUNDING_ENV", "development").strip().lower()
IS_DEVELOPMENT = _ENV in {"development", "dev", "local"}
IS_PRODUCTION = _ENV == "production"

DEFAULT_DB_PATH = Path(
    os.getenv(
        "MARKROUNDING_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "markrounding.sqlite"),
    )
)

# JWT signing secret for the admin session token.
_JWT_DEV_DEFAULT = "dev-secret-not-for-production-use-0000000000000000"
JWT_SECRET = os.getenv("MARKROUNDING_SECRET", "").strip()
if not JWT_SECRET:
    if IS_PRODUCTION:
        raise RuntimeError(
            "MARKROUNDING_SECRET saknas. Sätt variabeln i .env.\n"
            'Generera: python3 -c "import secrets; print(secrets.token_hex(64))"'
        )
    _log.warning(
        "MARKROUNDING_SECRET är inte satt — använder dev-default. "
        "SÄTT variabeln före driftsättning i produktion!"
    )
    JWT_SECRET = _JWT_DEV_DEFAULT

# PBKDF2 hash of the single admin password, produced by
# `uv run markrounding hash-password`.
_ADMIN_DEV_DEFAULT = (
    # Hash of "admin" — dev only. Regenerate with `markrounding hash-password`.
    "pbkdf2$260000$b056a0b3dcd8f17bbcc5305343a8d181$"
    "66982acdf2e307cc20b6bc478e8f772757db42eb91adaa8a86588cd6b2405a14"
)
ADMIN_PASSWORD_HASH = os.getenv("MARKROUNDING_ADMIN_PASSWORD_HASH", "").strip()
if not ADMIN_PASSWORD_HASH:
    if IS_PRODUCTION:
        raise RuntimeError(
            "MARKROUNDING_ADMIN_PASSWORD_HASH saknas. Sätt variabeln i .env.\n"
            "Generera: uv run markrounding hash-password"
        )
    _log.warning(
        "MARKROUNDING_ADMIN_PASSWORD_HASH är inte satt — admin-lösenordet är "
        "'admin' (dev-default). SÄTT variabeln före driftsättning i produktion!"
    )
    ADMIN_PASSWORD_HASH = _ADMIN_DEV_DEFAULT

ADMIN_TOKEN_TTL_SECONDS = int(os.getenv("MARKROUNDING_ADMIN_TOKEN_TTL", "43200"))

# Server-side Matomo tracking (Tracking HTTP API). Off unless both URL and
# site id are set — dev environments simply skip tracking.
MATOMO_URL = os.getenv("MARKROUNDING_MATOMO_URL", "").strip().rstrip("/")
MATOMO_SITE_ID = os.getenv("MARKROUNDING_MATOMO_SITE_ID", "").strip()
# token_auth lets us pass the real visitor IP (cip); without it Matomo
# records the container's IP for every visit.
MATOMO_TOKEN = os.getenv("MARKROUNDING_MATOMO_TOKEN", "").strip()
MATOMO_ENABLED = bool(MATOMO_URL and MATOMO_SITE_ID)
