"""Admin race reset: wipes roundings, boat codes, start data and the
protocol for a single race. Deliberately admin-only — the committee
token must not be able to erase the protocol."""

from tests.test_api import add_boats
from tests.test_api import create_regatta


def _report_activity(client, token, number):
    """Simulate a raced start on race `number`: roundings, a boat code,
    a note and a general recall (which keeps the roundings)."""
    overview = client.get(f"/api/report/{token}").json()
    boats = overview["boats"]
    mark = overview["courses"][0]["marks"][0]
    for boat in boats[:2]:
        client.post(
            f"/api/report/{token}/races/{number}/roundings",
            json={"mark_id": mark["id"], "boat_id": boat["id"]},
        )
    client.put(
        f"/api/report/{token}/races/{number}/boats/{boats[0]['id']}/status",
        json={"code": "OCS"},
    )
    client.post(
        f"/api/report/{token}/races/{number}/log", json={"note": "Testanteckning"}
    )
    client.post(f"/api/report/{token}/races/{number}/general-recall")


def test_reset_wipes_only_the_chosen_race(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]
    _report_activity(client, token, 1)
    _report_activity(client, token, 2)

    resp = client.post(
        f"/api/admin/regattas/{regatta['id']}/races/1/reset", headers=admin_headers
    )
    assert resp.status_code == 200
    race = resp.json()
    assert race["status"] == "upcoming"
    assert race["started_at"] is None
    assert race["planned_start"] is None
    assert race["general_recalls"] == 0
    assert race["shortened"] is False
    assert race["rounding_count"] == 0
    assert race["course_id"] is not None  # the course choice survives

    # boat codes gone, no boat has rounded anything
    detail = client.get(f"/api/report/{token}/races/1").json()
    assert all(entry["code"] is None for entry in detail["leaderboard"])
    assert all(not m["roundings"] for m in detail["marks"])

    # the protocol is wiped and restarts with the reset entry itself
    log = client.get(f"/api/report/{token}/races/1/log").json()
    assert [e["event"] for e in log] == ["race_reset"]

    # race 2 is untouched: roundings, code and protocol remain
    other = client.get(f"/api/report/{token}/races/2").json()
    assert any(m["roundings"] for m in other["marks"])
    assert any(e["code"] == "OCS" for e in other["leaderboard"])
    other_log = client.get(f"/api/report/{token}/races/2/log").json()
    assert any(e["event"] == "note" for e in other_log)


def test_reset_requires_admin(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    token = regatta["report_token"]

    resp = client.post(f"/api/admin/regattas/{regatta['id']}/races/1/reset")
    assert resp.status_code == 401
    # no reset under the committee token's namespace
    resp = client.post(f"/api/report/{token}/races/1/reset")
    assert resp.status_code in (404, 405)


def test_reset_unknown_race_is_404(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    resp = client.post(
        f"/api/admin/regattas/{regatta['id']}/races/99/reset", headers=admin_headers
    )
    assert resp.status_code == 404
