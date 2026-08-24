"""Weather cache: TTL, one upstream call per expiry, stale-on-error."""

import httpx
import pytest

from markrounding import weather


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class Clock:
    """Stands in for the time module — only monotonic() is used."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


@pytest.fixture(autouse=True)
def clean_cache():
    weather._cache.clear()
    yield
    weather._cache.clear()


def test_caches_per_coordinate(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse({"current": {"temperature_2m": 18.2}, "hourly": {}})

    monkeypatch.setattr(weather.httpx, "get", fake_get)
    first = weather.get_weather(59.78, 17.63)
    assert weather.get_weather(59.78, 17.63) is first
    assert len(calls) == 1
    weather.get_weather(57.7, 11.9)  # other coordinate → own cache entry
    assert len(calls) == 2


def test_serves_stale_on_upstream_failure(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(weather, "time", clock)
    failing = {"active": False}
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(clock.now)
        if failing["active"]:
            raise httpx.ConnectError("down")
        return FakeResponse({"current": {"wind_speed_10m": 5.1}, "hourly": {}})

    monkeypatch.setattr(weather.httpx, "get", fake_get)

    fresh = weather.get_weather(59.78, 17.63)
    failing["active"] = True
    clock.now += weather._CACHE_TTL_SECONDS + 1

    assert weather.get_weather(59.78, 17.63) is fresh  # stale beats an error
    assert len(calls) == 2
    weather.get_weather(59.78, 17.63)  # backed off — no immediate retry
    assert len(calls) == 2
    clock.now += weather._RETRY_AFTER_FAILURE_SECONDS + 1
    weather.get_weather(59.78, 17.63)
    assert len(calls) == 3

    failing["active"] = False
    clock.now += weather._RETRY_AFTER_FAILURE_SECONDS + 1
    assert weather.get_weather(59.78, 17.63) is not fresh  # recovered
    assert len(calls) == 4


def test_failure_without_cache_raises(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(weather.httpx, "get", fake_get)
    with pytest.raises(httpx.ConnectError):
        weather.get_weather(1.0, 2.0)


def test_compass():
    assert weather.compass(0) == "N"
    assert weather.compass(310) == "NV"
    assert weather.compass(359) == "N"
    assert weather.compass(None) == ""
