"""Gap computation: seconds behind the first boat at each mark."""

from markrounding import db


def test_gap_seconds_per_mark(client, admin_headers, monkeypatch):
    from tests.test_api import add_boats
    from tests.test_api import create_regatta

    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]
    overview = client.get(f"/api/report/{token}").json()
    boats = {b["sail_number"]: b for b in overview["boats"]}
    mark1, mark2 = overview["marks"][1], overview["marks"][2]

    # Start the race first — the first rounding would otherwise auto-flip
    # status and consume an extra tick from the patched clock below.
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})

    # Deterministic clock: each rounding lands 42 s after the previous one.
    times = iter(
        [
            "2026-08-06T10:00:00Z",
            "2026-08-06T10:00:42Z",
            "2026-08-06T10:20:00Z",
            "2026-08-06T10:21:30Z",
        ]
    )
    monkeypatch.setattr(db, "utcnow_iso", lambda: next(times))

    for mark, sail in [
        (mark1, "SWE 7"),
        (mark1, "SWE 106"),
        (mark2, "SWE 7"),
        (mark2, "SWE 106"),
    ]:
        resp = client.post(
            f"/api/report/{token}/races/1/roundings",
            json={"mark_id": mark["id"], "boat_id": boats[sail]["id"]},
        )
        assert resp.status_code == 201

    race = client.get(f"/api/regattas/{regatta['slug']}/races/1").json()
    m1, m2 = race["marks"][1], race["marks"][2]
    assert [r["gap_seconds"] for r in m1["roundings"]] == [0, 42]
    assert [r["gap_seconds"] for r in m2["roundings"]] == [0, 90]
    # the gap grew from 42 s to 90 s between the marks — exactly what the
    # development chart plots
