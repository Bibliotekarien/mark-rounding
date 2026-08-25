"""Current + forecast weather from Open-Meteo (no API key required).

Same upstream as gribranker. Responses are cached in-process for fifteen
minutes per coordinate so a busy regatta page never hammers the API.
Refreshes are single-flight, and when Open-Meteo fails the last good
response is served instead (weather moves slowly; stale beats an error)
with retries backed off to once a minute. Wind speeds in m/s, directions
in degrees (from), times ISO UTC.
"""

import threading
import time

import httpx

API_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE_TTL_SECONDS = 900.0
_RETRY_AFTER_FAILURE_SECONDS = 60.0

_PARAMS = "temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,weather_code"

_cache: dict[tuple[float, float], tuple[float, dict]] = {}
_lock = threading.Lock()


def get_weather(lat: float, lon: float) -> dict:
    key = (round(lat, 3), round(lon, 3))
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    with _lock:
        # Single flight: whoever waited here re-checks before fetching, so
        # a stampede of page loads at expiry becomes one upstream call.
        cached = _cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        try:
            resp = httpx.get(
                API_URL,
                params={
                    "latitude": key[0],
                    "longitude": key[1],
                    "current": _PARAMS,
                    "hourly": _PARAMS,
                    "wind_speed_unit": "ms",
                    "forecast_days": 3,
                    "timezone": "UTC",
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            if cached is None:
                raise  # nothing to fall back on — the endpoint answers 502
            # Serve stale, and re-date the entry so the failing upstream is
            # retried after a minute instead of on every page load.
            _cache[key] = (
                now - _CACHE_TTL_SECONDS + _RETRY_AFTER_FAILURE_SECONDS,
                cached[1],
            )
            return cached[1]
        result = {
            "current": data.get("current", {}),
            "hourly": data.get("hourly", {}),
        }
        _cache[key] = (now, result)
        return result


_COMPASS = [
    "N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO",
    "S", "SSV", "SV", "VSV", "V", "VNV", "NV", "NNV",
]


def compass(degrees: float | None) -> str:
    """Wind direction as a Swedish 16-point compass label (from-direction)."""
    if degrees is None:
        return ""
    return _COMPASS[round(degrees / 22.5) % 16]
