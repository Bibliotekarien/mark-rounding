"""Start procedure: countdown sequence, AP, general recall, OCS/black
flag reporting and the committee protocol."""

from tests.test_api import add_boats
from tests.test_api import create_regatta


def setup_regatta(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    return regatta


def test_start_sequence_and_signal(client, admin_headers):
    regatta = setup_regatta(client, admin_headers)
    token = regatta["report_token"]

    resp = client.post(
        f"/api/report/{token}/races/1/start-sequence",
        json={"minutes": 5, "prep_flag": "I"},
    )
    assert resp.status_code == 200
    race = resp.json()
    assert race["planned_start"]
    assert race["prep_flag"] == "I"
    assert race["status"] == "upcoming"

    # start signal: race becomes ongoing, started_at = planned start
    resp = client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    assert resp.json()["started_at"] == race["planned_start"]

    log = client.get(f"/api/report/{token}/races/1/log").json()
    events = [e["event"] for e in log]
    assert "sequence" in events
    assert "start" in events


def test_postpone_clears_countdown(client, admin_headers):
    regatta = setup_regatta(client, admin_headers)
    token = regatta["report_token"]
    client.post(f"/api/report/{token}/races/1/start-sequence", json={"minutes": 5})
    resp = client.delete(f"/api/report/{token}/races/1/start-sequence")
    assert resp.status_code == 200
    assert resp.json()["planned_start"] is None
    log = client.get(f"/api/report/{token}/races/1/log").json()
    assert any(e["event"] == "postpone" for e in log)


def test_general_recall(client, admin_headers):
    regatta = setup_regatta(client, admin_headers)
    token = regatta["report_token"]
    client.post(f"/api/report/{token}/races/1/start-sequence", json={"minutes": 5})
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})

    resp = client.post(f"/api/report/{token}/races/1/general-recall")
    race = resp.json()
    assert race["status"] == "upcoming"
    assert race["started_at"] is None
    assert race["planned_start"] is None
    assert race["general_recalls"] == 1

    # a new sequence can be armed after the recall
    resp = client.post(
        f"/api/report/{token}/races/1/start-sequence",
        json={"minutes": 4, "prep_flag": "BLACK"},
    )
    assert resp.status_code == 200
    assert resp.json()["prep_flag"] == "BLACK"


def test_sequence_rejected_while_ongoing(client, admin_headers):
    regatta = setup_regatta(client, admin_headers)
    token = regatta["report_token"]
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    resp = client.post(f"/api/report/{token}/races/1/start-sequence", json={"minutes": 5})
    assert resp.status_code == 409


def test_boat_status_codes_and_leaderboard(client, admin_headers):
    regatta = setup_regatta(client, admin_headers)
    token = regatta["report_token"]
    overview = client.get(f"/api/report/{token}").json()
    boats = {b["sail_number"]: b for b in overview["boats"]}
    mark = overview["marks"][1]

    # SWE 7 rounds a mark but is OCS; SWE 106 gets a 20 % penalty (ZFP)
    client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": boats["SWE 7"]["id"]},
    )
    client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": boats["SWE 106"]["id"]},
    )
    resp = client.put(
        f"/api/report/{token}/races/1/boats/{boats['SWE 7']['id']}/status",
        json={"code": "OCS"},
    )
    assert resp.status_code == 200
    client.put(
        f"/api/report/{token}/races/1/boats/{boats['SWE 106']['id']}/status",
        json={"code": "ZFP"},
    )

    lb = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()["leaderboard"]
    # ZFP keeps ranking (leader), OCS drops to the bottom with code shown
    assert lb[0]["boat"]["sail_number"] == "SWE 106"
    assert lb[0]["code"] == "ZFP"
    assert lb[-1]["boat"]["sail_number"] == "SWE 7"
    assert lb[-1]["code"] == "OCS"
    # untouched boat in between, no code
    assert lb[1]["boat"]["sail_number"] == "SWE 3031"
    assert lb[1]["code"] is None

    # clearing the OCS restores normal ranking
    resp = client.delete(
        f"/api/report/{token}/races/1/boats/{boats['SWE 7']['id']}/status"
    )
    assert resp.status_code == 204
    lb = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()["leaderboard"]
    assert lb[0]["boat"]["sail_number"] == "SWE 7"  # rounded first

    assert client.put(
        f"/api/report/{token}/races/1/boats/{boats['SWE 7']['id']}/status",
        json={"code": "XYZ"},
    ).status_code == 422


def test_protocol_notes_and_undo_logged(client, admin_headers):
    regatta = setup_regatta(client, admin_headers)
    token = regatta["report_token"]
    overview = client.get(f"/api/report/{token}").json()
    boat = overview["boats"][0]
    mark = overview["marks"][0]

    resp = client.post(
        f"/api/report/{token}/races/1/log",
        json={"note": "Vind vrider vänster, 8 m/s"},
    )
    assert resp.status_code == 201

    r = client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": boat["id"]},
    )
    client.delete(f"/api/report/{token}/roundings/{r.json()['id']}")

    log = client.get(f"/api/report/{token}/races/1/log").json()
    events = {e["event"] for e in log}
    assert "note" in events
    assert "rounding_undone" in events
    undo = next(e for e in log if e["event"] == "rounding_undone")
    assert undo["sail_number"] == boat["sail_number"]
    note = next(e for e in log if e["event"] == "note")
    assert "Vind vrider" in note["note"]
