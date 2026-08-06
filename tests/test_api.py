"""End-to-end flow: admin creates a regatta, committee reports roundings
via the secret token, the public follows progress."""


def create_regatta(client, admin_headers, **overrides):
    body = {
        "name": "Testregattan",
        "venue": "Uppsala",
        "lat": 59.78,
        "lon": 17.63,
        "start_date": "2026-06-19",
        "end_date": "2026-06-20",
        "race_count": 2,
        "courses": [
            {"name": "Standardbana", "marks": ["Start", "Kryssmärke", "Gate", "Mål"]}
        ],
    }
    body.update(overrides)
    resp = client.post("/api/admin/regattas", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def add_boats(client, admin_headers, regatta_id):
    boats = [
        {"sail_number": "SWE 106", "boat_name": "Oriole", "boat_type": "Omega 42"},
        {"sail_number": "SWE 3031", "boat_name": "Relax", "boat_type": "Elan E3"},
        {"sail_number": "SWE 7", "boat_name": "Tärnan", "boat_type": "Neptunkryssare"},
    ]
    resp = client.post(
        f"/api/admin/regattas/{regatta_id}/boats/import",
        json={"boats": boats},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["added"] == 3


def test_full_reporting_flow(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]

    overview = client.get(f"/api/report/{token}").json()
    course = overview["courses"][0]
    assert course["name"] == "Standardbana"
    assert [m["name"] for m in course["marks"]] == ["Start", "Kryssmärke", "Gate", "Mål"]
    assert len(overview["races"]) == 2
    # races default to the regatta's first course
    assert all(r["course_id"] == course["id"] for r in overview["races"])
    boats = {b["sail_number"]: b for b in overview["boats"]}
    # natural sail number sort: 7 < 106 < 3031
    assert [b["sail_number"] for b in overview["boats"]] == ["SWE 7", "SWE 106", "SWE 3031"]

    mark = course["marks"][1]
    b7, b106 = boats["SWE 7"], boats["SWE 106"]

    r1 = client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": b106["id"]},
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": b7["id"]},
    )
    assert r2.status_code == 201

    # duplicate is rejected
    dup = client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": b106["id"]},
    )
    assert dup.status_code == 409

    # first rounding auto-started the race
    race = client.get(f"/api/report/{token}/races/1").json()
    assert race["race"]["status"] == "ongoing"
    assert race["race"]["started_at"]

    # rounding order at the mark and on the public page
    public = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()
    rounded = public["marks"][1]["roundings"]
    assert [r["boat"]["sail_number"] for r in rounded] == ["SWE 106", "SWE 7"]
    assert [r["position"] for r in rounded] == [1, 2]

    # leaderboard: both at same mark, 106 rounded first; 3031 not started
    lb = public["leaderboard"]
    assert [e["boat"]["sail_number"] for e in lb] == ["SWE 106", "SWE 7", "SWE 3031"]
    assert lb[0]["last_mark_name"] == "Kryssmärke"
    assert lb[2]["last_mark_seq"] is None

    # undo: remove SWE 106's rounding, SWE 7 becomes leader
    undo = client.delete(f"/api/report/{token}/roundings/{r1.json()['id']}")
    assert undo.status_code == 204
    lb = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()["leaderboard"]
    assert lb[0]["boat"]["sail_number"] == "SWE 7"

    # finish the race
    fin = client.post(f"/api/report/{token}/races/1/status", json={"status": "finished"})
    assert fin.status_code == 200
    assert fin.json()["status"] == "finished"


def test_report_boat_management(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]

    # committee adds a late-registered boat
    resp = client.post(
        f"/api/report/{token}/boats",
        json={"sail_number": "SWE 42", "boat_name": "Sen anmälan"},
    )
    assert resp.status_code == 201
    boat_id = resp.json()["id"]

    # …and deactivates it when it withdraws
    resp = client.patch(f"/api/report/{token}/boats/{boat_id}", json={"active": False})
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # inactive boats hidden on the public page, visible in report view
    public = client.get(f"/api/regattas/{regatta['slug']}").json()
    assert all(b["sail_number"] != "SWE 42" for b in public["boats"])
    report = client.get(f"/api/report/{token}").json()
    assert any(b["sail_number"] == "SWE 42" for b in report["boats"])


def test_report_course_editing(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    token = regatta["report_token"]
    course_id = regatta["courses"][0]["id"]
    resp = client.patch(
        f"/api/report/{token}/courses/{course_id}",
        json={"marks": ["Start", "Märke 1", "Mål"], "name": "Kortbana"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Kortbana"
    assert [m["name"] for m in body["marks"]] == ["Start", "Märke 1", "Mål"]
    assert [m["seq"] for m in body["marks"]] == [1, 2, 3]


def test_invalid_token_rejected(client):
    assert client.get("/api/report/not-a-token").status_code == 404
    resp = client.post(
        "/api/report/not-a-token/races/1/roundings",
        json={"mark_id": 1, "boat_id": 1},
    )
    assert resp.status_code == 404


def test_race_count_sync(client, admin_headers):
    regatta = create_regatta(client, admin_headers, race_count=3)
    resp = client.patch(
        f"/api/admin/regattas/{regatta['id']}",
        json={"race_count": 5},
        headers=admin_headers,
    )
    assert [r["number"] for r in resp.json()["races"]] == [1, 2, 3, 4, 5]
    resp = client.patch(
        f"/api/admin/regattas/{regatta['id']}",
        json={"race_count": 2},
        headers=admin_headers,
    )
    assert [r["number"] for r in resp.json()["races"]] == [1, 2]


def test_public_listing(client, admin_headers):
    create_regatta(client, admin_headers, name="Vårregattan")
    create_regatta(client, admin_headers, name="Höstregattan", start_date="2026-09-01")
    listing = client.get("/api/regattas").json()
    assert len(listing) == 2
    assert "report_token" not in listing[0]
    slugs = {r["slug"] for r in listing}
    assert slugs == {"varregattan", "hostregattan"}


def test_regenerate_token(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    old_token = regatta["report_token"]
    resp = client.post(
        f"/api/admin/regattas/{regatta['id']}/regenerate-token",
        headers=admin_headers,
    )
    new_token = resp.json()["report_token"]
    assert new_token != old_token
    assert client.get(f"/api/report/{old_token}").status_code == 404
    assert client.get(f"/api/report/{new_token}").status_code == 200
