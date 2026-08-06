"""Multiple courses: per-race selection, shortening, and the migration
from the single-course-per-regatta schema."""

import sqlite3

from markrounding import db as mdb
from tests.test_api import add_boats
from tests.test_api import create_regatta


def test_multiple_courses_and_race_selection(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    token = regatta["report_token"]

    # committee defines a second, shorter course
    resp = client.post(
        f"/api/report/{token}/courses",
        json={"name": "Kortbana", "marks": ["Start", "Kryss", "Mål"]},
    )
    assert resp.status_code == 201
    short = resp.json()

    # race 2 sails the short course
    resp = client.post(
        f"/api/report/{token}/races/2/course", json={"course_id": short["id"]}
    )
    assert resp.status_code == 200
    assert resp.json()["course_name"] == "Kortbana"

    # race 1 keeps the default course; the race views follow each course
    race1 = client.get(f"/api/report/{token}/races/1").json()
    race2 = client.get(f"/api/report/{token}/races/2").json()
    assert len(race1["marks"]) == 4
    assert [m["name"] for m in race2["marks"]] == ["Start", "Kryss", "Mål"]

    # course choice is logged in the protocol
    log = client.get(f"/api/report/{token}/races/2/log").json()
    assert any(e["event"] == "course_set" and e["note"] == "Kortbana" for e in log)


def test_course_locked_once_started(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    token = regatta["report_token"]
    other = client.post(
        f"/api/report/{token}/courses", json={"name": "B", "marks": ["Start", "Mål"]}
    ).json()
    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    resp = client.post(
        f"/api/report/{token}/races/1/course", json={"course_id": other["id"]}
    )
    assert resp.status_code == 409


def test_shorten_finishes_race(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]

    # cannot shorten a race that has not started
    assert client.post(f"/api/report/{token}/races/1/shorten").status_code == 409

    client.post(f"/api/report/{token}/races/1/status", json={"status": "ongoing"})
    resp = client.post(f"/api/report/{token}/races/1/shorten")
    assert resp.status_code == 200
    race = resp.json()
    assert race["status"] == "finished"
    assert race["shortened"] is True

    log = client.get(f"/api/report/{token}/races/1/log").json()
    assert any(e["event"] == "shortened" for e in log)


def test_delete_course_rules(client, admin_headers):
    regatta = create_regatta(client, admin_headers)
    add_boats(client, admin_headers, regatta["id"])
    token = regatta["report_token"]
    default = regatta["courses"][0]
    spare = client.post(
        f"/api/report/{token}/courses", json={"name": "Reserv", "marks": ["Start", "Mål"]}
    ).json()

    # unused course can be deleted
    assert client.delete(f"/api/report/{token}/courses/{spare['id']}").status_code == 204

    # a course with reported roundings cannot
    overview = client.get(f"/api/report/{token}").json()
    boat = overview["boats"][0]
    mark = overview["courses"][0]["marks"][0]
    client.post(
        f"/api/report/{token}/races/1/roundings",
        json={"mark_id": mark["id"], "boat_id": boat["id"]},
    )
    assert (
        client.delete(f"/api/report/{token}/courses/{default['id']}").status_code == 409
    )


OLD_SCHEMA = """
CREATE TABLE regattas (
    id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    venue TEXT NOT NULL DEFAULT '', organizer TEXT NOT NULL DEFAULT '',
    lat REAL, lon REAL, start_date TEXT, end_date TEXT,
    sailarena_url TEXT NOT NULL DEFAULT '', report_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE marks (
    id INTEGER PRIMARY KEY,
    regatta_id INTEGER NOT NULL REFERENCES regattas(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL, name TEXT NOT NULL, UNIQUE (regatta_id, seq)
);
CREATE TABLE races (
    id INTEGER PRIMARY KEY,
    regatta_id INTEGER NOT NULL REFERENCES regattas(id) ON DELETE CASCADE,
    number INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'upcoming',
    started_at TEXT, planned_start TEXT, prep_flag TEXT NOT NULL DEFAULT 'P',
    general_recalls INTEGER NOT NULL DEFAULT 0, UNIQUE (regatta_id, number)
);
CREATE TABLE boats (
    id INTEGER PRIMARY KEY,
    regatta_id INTEGER NOT NULL REFERENCES regattas(id) ON DELETE CASCADE,
    sail_number TEXT NOT NULL, boat_name TEXT NOT NULL DEFAULT '',
    boat_type TEXT NOT NULL DEFAULT '', skipper TEXT NOT NULL DEFAULT '',
    club TEXT NOT NULL DEFAULT '', nation TEXT NOT NULL DEFAULT '',
    srs TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE roundings (
    id INTEGER PRIMARY KEY,
    race_id INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    mark_id INTEGER NOT NULL REFERENCES marks(id) ON DELETE CASCADE,
    boat_id INTEGER NOT NULL REFERENCES boats(id) ON DELETE CASCADE,
    ts TEXT NOT NULL, UNIQUE (race_id, mark_id, boat_id)
);
INSERT INTO regattas (id, slug, name, report_token, created_at)
    VALUES (1, 'gammal', 'Gammal regatta', 'tok', '2026-08-01T00:00:00Z');
INSERT INTO marks (id, regatta_id, seq, name) VALUES
    (1, 1, 1, 'Start'), (2, 1, 2, 'Kryss'), (3, 1, 3, 'Mål');
INSERT INTO races (id, regatta_id, number, status) VALUES (1, 1, 1, 'ongoing');
INSERT INTO boats (id, regatta_id, sail_number) VALUES (1, 1, 'SWE 1');
INSERT INTO roundings (race_id, mark_id, boat_id, ts)
    VALUES (1, 2, 1, '2026-08-01T10:00:00Z');
"""


def test_migration_from_single_course_schema(tmp_path):
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    conn.close()

    conn = mdb.connect(path)
    mdb.init_db(conn)

    course = conn.execute("SELECT * FROM courses").fetchone()
    assert course["name"] == "Bana 1"
    assert course["regatta_id"] == 1
    marks = conn.execute(
        "SELECT * FROM marks WHERE course_id = ? ORDER BY seq", (course["id"],)
    ).fetchall()
    assert [m["name"] for m in marks] == ["Start", "Kryss", "Mål"]
    assert [m["id"] for m in marks] == [1, 2, 3]  # mark ids preserved
    race = conn.execute("SELECT * FROM races").fetchone()
    assert race["course_id"] == course["id"]
    # the reported rounding survived and still points at mark 2
    rounding = conn.execute("SELECT * FROM roundings").fetchone()
    assert rounding["mark_id"] == 2

    # idempotent: running init_db again changes nothing
    mdb.init_db(conn)
    assert conn.execute("SELECT COUNT(*) AS n FROM courses").fetchone()["n"] == 1
    conn.close()
