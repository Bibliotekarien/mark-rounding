"""Server-side Matomo tracking via the Tracking HTTP API.

Instead of a client-side JS tracker the backend reports page loads
directly to matomo.php: ad-blocker-proof, cookie-free and no analytics
script in the CSP. Trade-off: only document loads are seen, not SPA route
changes within a loaded page.

Privacy follows the platform's client-side conventions: DNT and Sec-GPC
are honored, no cookies, and secret report tokens are masked before URLs
leave the app. Tracking is fire-and-forget — it must never slow down or
fail a request.
"""

import asyncio
import logging
import re
import secrets

import httpx

from . import config

_log = logging.getLogger("markrounding.matomo")

_client: httpx.AsyncClient | None = None

_REPORT_TOKEN_RE = re.compile(r"^(/report/)[^/]+")
# Unanchored: a referrer is a full URL (https://host/report/<token>), and a
# page opened from the committee view — reload, new tab — carries it.
_REFERRER_TOKEN_RE = re.compile(r"(/report/)[^/?#]+")


def sanitize_path(path: str) -> str:
    """Mask the secret committee token so it never reaches analytics."""
    return _REPORT_TOKEN_RE.sub(r"\1_token_", path)


def sanitize_referrer(referrer: str) -> str:
    """Same masking for the Referer header's full URL."""
    return _REFERRER_TOKEN_RE.sub(r"\1_token_", referrer)


def should_track(method: str, path: str, status_code: int) -> bool:
    """Track successful HTML document loads only — not API calls (polling
    would flood analytics), assets, or health checks."""
    if method != "GET" or status_code != 200:
        return False
    if path.startswith(("/api", "/assets")):
        return False
    if "." in path.rsplit("/", 1)[-1]:  # favicon.ico, robots.txt, …
        return False
    return True


def opted_out(headers) -> bool:
    return headers.get("dnt") == "1" or headers.get("sec-gpc") == "1"


def build_params(
    url: str, user_agent: str, lang: str, referrer: str, client_ip: str
) -> dict:
    params = {
        "idsite": config.MATOMO_SITE_ID,
        "rec": "1",
        "apiv": "1",
        "url": url,
        "ua": user_agent,
        "lang": lang,
        "rand": secrets.token_hex(8),
        "send_image": "0",
    }
    if referrer:
        params["urlref"] = referrer
    if config.MATOMO_TOKEN and client_ip:
        params["token_auth"] = config.MATOMO_TOKEN
        params["cip"] = client_ip
    return params


async def _send(params: dict) -> None:
    global _client
    try:
        if _client is None:
            _client = httpx.AsyncClient(timeout=5.0)
        await _client.post(f"{config.MATOMO_URL}/matomo.php", data=params)
    except Exception as exc:  # analytics must never break the app
        _log.debug("Matomo tracking failed: %s", exc)


def track_request(request, status_code: int) -> None:
    """Called from the middleware; schedules a fire-and-forget hit."""
    if not config.MATOMO_ENABLED:
        return
    if not should_track(request.method, request.url.path, status_code):
        return
    if opted_out(request.headers):
        return
    path = sanitize_path(request.url.path)
    # uvicorn runs with --proxy-headers, so scheme/host reflect the edge.
    url = f"{request.url.scheme}://{request.url.netloc}{path}"
    params = build_params(
        url=url,
        user_agent=request.headers.get("user-agent", ""),
        lang=request.headers.get("accept-language", ""),
        referrer=sanitize_referrer(request.headers.get("referer", "")),
        client_ip=request.client.host if request.client else "",
    )
    asyncio.get_running_loop().create_task(_send(params))
