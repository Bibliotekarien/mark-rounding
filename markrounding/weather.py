"""Current + forecast weather from Open-Meteo (no API key required).

Same upstream as gribranker. Responses are cached in-process for ten
minutes per coordinate so a busy regatta page never hammers the API.
Wind speeds in m/s, directions in degrees (from), times ISO UTC.
"""

import time

import httpx

API_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE_TTL_SECONDS = 600.0

_PARAMS = "temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,weather_code"

_cache: dict[tuple[float, float], tuple[float, dict]] = {}


def get_weather(lat: float, lon: float) -> dict:
    key = (round(lat, 3), round(lon, 3))
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

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
    result = {
        "current": data.get("current", {}),
        "hourly": data.get("hourly", {}),
    }
    _cache[key] = (now, result)
    return result
