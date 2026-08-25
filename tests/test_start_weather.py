"""Start-weather snapshot: stored at the fresh start, shown afterwards,
logged in the protocol, cleared by admin reset."""

import pytest

from markrounding.api import report
from tests.test_api import add_boats
from tests.test_api import create_regatta

CANNED = {
    "current": {
        "temperature_2m": 14.3,
        "wind_speed_10m": 5.4,
        "wind_gusts_10m": 8.1,
        "wind_direction_10m": 310.0,
        "weather_code": 2,
    },
    "hourly": {},
}


@pytest.fixture()
def sync_capture(monkeypatch):
    """Run the capture synchronously with a canned Open-Meteo response,
    overriding conftest's no-op. Returns the list of captured race ids."""
    calls = []
    monkeypatch.setattr(report.weather, "get_weather", lambda lat, lon: CANNED)

    def capture(request, regatta, race_id):
        if regatta["lat"] is None or regatta["lon"] is None:
            return
        calls.append(race_id)
        report._store_start_weather(
            request.app.state.db_path, race_id, regatta["lat"], regatta["lon"]
        )

    monkeypatch.setattr(report, "_capture_start_weather", capture)
    return calls


def test_snapshot_on_start_and_shown_after(client, admin_headers, sync_capture):
    regatta = create_regatta(client, admin_headers)
    token = regatta["report_token"]

    resp = client.post(
        f"/api/report/{token}/races/1/status", json={"status": "ongoing"}
    )
    assert resp.status_code == 200
    assert sync_capture == [resp.json()["id"]]

    race = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()["race"]
    snapshot = race["start_weather"]
    assert snapshot["current"]["wind_speed_10m"] == 5.4
    assert snapshot["captured_at"].endswith("Z")

    log = client.get(f"/api/report/{token}/races/1/log").json()
    weather_rows = [e for e in log if e["event"] == "weather"]
    assert len(weather_rows) == 1
    assert weather_rows[0]["note"] == "Vind 5 (8) m/s från NV, 14 °C"

    # Reopening a finished race is not a new start — no second snapshot.
    client.post(f"/api/report/{token}/races/1/status", json={"status": "finished"})
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    assert len(sync_capture) == 1


def test_snapshot_on_first_rounding_autostart(client, admin_headers, sync_capture):
    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]
    overview = client.get(f"/api/report/{token}").json()
    mark = overview["courses"][0]["marks"][0]
    boats = overview["boats"]

    resp = client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": boats[0]["id"]},
    )
    assert resp.status_code == 201
    assert len(sync_capture) == 1
    race = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()["race"]
    assert race["start_weather"]["current"]["temperature_2m"] == 14.3

    # The race is already started — further roundings do not re-capture.
    client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": boats[1]["id"]},
    )
    assert len(sync_capture) == 1


def test_general_recall_restart_takes_new_snapshot(
    client, admin_headers, sync_capture
):
    regatta = create_regatta(client, admin_headers)
    token = regatta["report_token"]
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    client.post(f"/api/report/{token}/races/1/general-recall")
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    assert len(sync_capture) == 2


def test_admin_reset_clears_snapshot(client, admin_headers, sync_capture):
    regatta = create_regatta(client, admin_headers)
    token = regatta["report_token"]
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    resp = client.post(
        f"/api/admin/regattas/{regatta['id']}/races/1/reset", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["start_weather"] is None


def test_no_snapshot_without_coordinates(client, admin_headers, sync_capture):
    regatta = create_regatta(client, admin_headers, lat=None, lon=None)
    token = regatta["report_token"]
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    assert sync_capture == []
    race = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()["race"]
    assert race["start_weather"] is None
