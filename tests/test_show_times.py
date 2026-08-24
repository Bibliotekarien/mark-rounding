"""Regatta setting show_times: with it off the public API publishes
placements only — timestamps and gaps are stripped server-side, while the
committee endpoints always include them."""

from tests.test_api import add_boats
from tests.test_api import create_regatta


def test_show_times_off_strips_public_times(client, admin_headers):
    regatta = create_regatta(client, admin_headers, show_times=False)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]
    overview = client.get(f"/api/report/{token}").json()
    mark = overview["courses"][0]["marks"][1]

    for boat in overview["boats"][:2]:
        resp = client.post(
            f"/api/report/{token}/races/1/roundings",
            json={"mark_id": mark["id"], "boat_id": boat["id"]},
        )
        assert resp.status_code == 201

    detail = client.get(f"/api/regattas/{regatta['slug']}").json()
    assert detail["show_times"] is False

    race = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()
    roundings = race["marks"][1]["roundings"]
    # The order the times produced is kept — the times themselves are not.
    assert [r["position"] for r in roundings] == [1, 2]
    assert all(r["ts"] is None and r["gap_seconds"] is None for r in roundings)
    assert all(e["last_ts"] is None for e in race["leaderboard"])

    # The committee view still gets the actual times.
    report = client.get(f"/api/report/{token}/races/1").json()
    assert all(r["ts"] for r in report["marks"][1]["roundings"])


def test_show_times_defaults_on_and_can_be_toggled(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    assert regatta["show_times"] is True

    resp = client.patch(
        f"/api/admin/regattas/{regatta['id']}",
        json={"show_times": False},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["show_times"] is False
    assert client.get(f"/api/regattas/{regatta['slug']}").json()["show_times"] is False
