"""Committee reporting endpoints, authorized by the secret regatta token.

No login: knowing the token (handed out by the admin as a URL) grants
reporting rights for that regatta only.
"""

import json
import sqlite3
import threading
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

from .. import db
from .. import weather
from . import common
from .deps import get_conn
from .deps import regatta_by_token
from .models import BoatIn
from .models import BoatPatch
from .models import BoatStatusIn
from .models import CourseIn
from .models import CoursePatch
from .models import LogNoteIn
from .models import RaceCourseIn
from .models import RaceStatusIn
from .models import RoundingIn
from .models import StartSequenceIn

router = APIRouter(prefix="/api/report/{token}")


def _weather_note(current: dict) -> str:
    """One-line Swedish weather summary for the race protocol."""
    wind = current.get("wind_speed_10m")
    if wind is None:
        return ""
    note = f"Vind {round(wind)}"
    gust = current.get("wind_gusts_10m")
    if gust is not None:
        note += f" ({round(gust)})"
    note += " m/s"
    direction = weather.compass(current.get("wind_direction_10m"))
    if direction:
        note += f" från {direction}"
    temp = current.get("temperature_2m")
    if temp is not None:
        note += f", {round(temp)} °C"
    return note


def _store_start_weather(
    db_path: Path | str, race_id: int, lat: float, lon: float
) -> None:
    """Fetch and persist the start-weather snapshot, and put a one-line
    summary in the protocol. Own connection: runs on a background thread
    after the start request has already returned."""
    data = weather.get_weather(lat, lon)
    current = data.get("current") or {}
    snapshot = {"current": current, "captured_at": db.utcnow_iso()}
    conn = db.connect(db_path)
    try:
        conn.execute(
            "UPDATE races SET start_weather = ? WHERE id = ?",
            (json.dumps(snapshot), race_id),
        )
        note = _weather_note(current)
        if note:
            db.log_event(conn, race_id, "weather", note=note)
        conn.commit()
    finally:
        conn.close()


def _capture_start_weather(
    request: Request, regatta: sqlite3.Row, race_id: int
) -> None:
    """Snapshot the weather at the start signal so it can be read back
    after the race. Runs off-thread and swallows failures — a slow or
    down Open-Meteo must never delay or fail the committee's start tap."""
    if regatta["lat"] is None or regatta["lon"] is None:
        return
    db_path = request.app.state.db_path

    def work() -> None:
        try:
            _store_start_weather(db_path, race_id, regatta["lat"], regatta["lon"])
        except Exception:
            pass  # the snapshot is a bonus, never worth breaking a start

    threading.Thread(target=work, daemon=True).start()


def _race(conn: sqlite3.Connection, regatta_id: int, number: int) -> sqlite3.Row:
    race = conn.execute(
        "SELECT * FROM races WHERE regatta_id = ? AND number = ?",
        (regatta_id, number),
    ).fetchone()
    if not race:
        raise HTTPException(status_code=404, detail="Racet finns inte")
    return race


@router.get("")
def report_overview(
    token: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta = regatta_by_token(conn, token)
    return common.regatta_detail(conn, regatta, include_inactive=True)


@router.get("/races/{number}")
def report_race(
    token: str, number: int, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    return common.race_progress(conn, regatta["id"], race)


@router.post("/races/{number}/roundings", status_code=201)
def add_rounding(
    token: str,
    number: int,
    body: RoundingIn,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    mark = conn.execute(
        "SELECT id FROM marks WHERE id = ? AND course_id = ?",
        (body.mark_id, race["course_id"]),
    ).fetchone()
    boat = conn.execute(
        "SELECT id FROM boats WHERE id = ? AND regatta_id = ?",
        (body.boat_id, regatta["id"]),
    ).fetchone()
    if not mark or not boat:
        raise HTTPException(status_code=404, detail="Okänt märke eller okänd båt")
    try:
        cur = conn.execute(
            "INSERT INTO roundings (race_id, mark_id, boat_id, ts) VALUES (?, ?, ?, ?)",
            (race["id"], body.mark_id, body.boat_id, db.utcnow_iso()),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="Båten är redan rapporterad vid det här märket"
        )
    # First rounding of an upcoming race flips it to ongoing automatically.
    if race["status"] == "upcoming":
        conn.execute(
            "UPDATE races SET status = 'ongoing', started_at = COALESCE(started_at, ?) "
            "WHERE id = ?",
            (db.utcnow_iso(), race["id"]),
        )
    conn.commit()
    if race["status"] == "upcoming" and not race["started_at"]:
        _capture_start_weather(request, regatta, race["id"])
    return {"id": cur.lastrowid}


@router.delete("/roundings/{rounding_id}", status_code=204)
def delete_rounding(
    token: str, rounding_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> None:
    regatta = regatta_by_token(conn, token)
    row = conn.execute(
        "SELECT r.race_id, r.boat_id, m.name AS mark_name FROM roundings r "
        "JOIN marks m ON m.id = r.mark_id "
        "WHERE r.id = ? AND r.race_id IN (SELECT id FROM races WHERE regatta_id = ?)",
        (rounding_id, regatta["id"]),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Rundningen finns inte")
    conn.execute("DELETE FROM roundings WHERE id = ?", (rounding_id,))
    db.log_event(
        conn,
        row["race_id"],
        "rounding_undone",
        boat_id=row["boat_id"],
        note=f"Rundning vid {row['mark_name']} ångrad",
    )
    conn.commit()


@router.post("/races/{number}/status")
def set_race_status(
    token: str,
    number: int,
    body: RaceStatusIn,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    started_at = race["started_at"]
    if body.status == "ongoing" and not started_at:
        # The start signal happened at the planned time if a sequence ran.
        started_at = race["planned_start"] or db.utcnow_iso()
    if body.status == "upcoming":
        started_at = None
    conn.execute(
        "UPDATE races SET status = ?, started_at = ? WHERE id = ?",
        (body.status, started_at, race["id"]),
    )
    if body.status != race["status"]:
        event = {"ongoing": "start", "finished": "finish", "upcoming": "reset"}[
            body.status
        ]
        db.log_event(conn, race["id"], event)
    conn.commit()
    # Fresh start (not a reopen of a finished race): snapshot the weather.
    if body.status == "ongoing" and not race["started_at"]:
        _capture_start_weather(request, regatta, race["id"])
    return common.race_dict(conn, _race(conn, regatta["id"], number))


@router.post("/races/{number}/start-sequence")
def start_sequence(
    token: str,
    number: int,
    body: StartSequenceIn,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    """Arm the start: countdown of `minutes` with the chosen preparatory
    flag. The race stays 'upcoming' until the start signal is confirmed."""
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    if race["status"] != "upcoming":
        raise HTTPException(
            status_code=409, detail="Racet är redan startat — gör allmän återkallelse först"
        )
    planned = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
    planned_iso = planned.strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE races SET planned_start = ?, prep_flag = ? WHERE id = ?",
        (planned_iso, body.prep_flag, race["id"]),
    )
    db.log_event(
        conn,
        race["id"],
        "sequence",
        note=f"Startsekvens {body.minutes} min, flagga {body.prep_flag}, start {planned_iso}",
    )
    conn.commit()
    return common.race_dict(conn, _race(conn, regatta["id"], number))


@router.delete("/races/{number}/start-sequence")
def postpone(
    token: str, number: int, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    """AP — postpone: abort the running countdown."""
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    conn.execute("UPDATE races SET planned_start = NULL WHERE id = ?", (race["id"],))
    db.log_event(conn, race["id"], "postpone", note="AP — uppskjutet")
    conn.commit()
    return common.race_dict(conn, _race(conn, regatta["id"], number))


@router.post("/races/{number}/general-recall")
def general_recall(
    token: str, number: int, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    """General recall: back to 'upcoming', start time cleared, counter up.
    Boat codes are kept — black flag (BFD) survives a restart per RRS 30.4;
    the committee clears codes manually where the rules say so (e.g. UFD)."""
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    conn.execute(
        "UPDATE races SET status = 'upcoming', started_at = NULL, planned_start = NULL, "
        "general_recalls = general_recalls + 1 WHERE id = ?",
        (race["id"],),
    )
    db.log_event(conn, race["id"], "general_recall", note="Allmän återkallelse")
    conn.commit()
    return common.race_dict(conn, _race(conn, regatta["id"], number))


@router.put("/races/{number}/boats/{boat_id}/status")
def set_boat_status(
    token: str,
    number: int,
    boat_id: int,
    body: BoatStatusIn,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    boat = conn.execute(
        "SELECT id FROM boats WHERE id = ? AND regatta_id = ?",
        (boat_id, regatta["id"]),
    ).fetchone()
    if not boat:
        raise HTTPException(status_code=404, detail="Båten finns inte")
    conn.execute(
        "INSERT INTO race_boat_status (race_id, boat_id, code, ts) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (race_id, boat_id) DO UPDATE SET code = excluded.code, ts = excluded.ts",
        (race["id"], boat_id, body.code, db.utcnow_iso()),
    )
    db.log_event(conn, race["id"], "boat_status", boat_id=boat_id, note=body.code)
    conn.commit()
    return {"boat_id": boat_id, "code": body.code}


@router.delete("/races/{number}/boats/{boat_id}/status", status_code=204)
def clear_boat_status(
    token: str,
    number: int,
    boat_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
) -> None:
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    deleted = conn.execute(
        "DELETE FROM race_boat_status WHERE race_id = ? AND boat_id = ?",
        (race["id"], boat_id),
    )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ingen markering att ta bort")
    db.log_event(conn, race["id"], "boat_status_cleared", boat_id=boat_id)
    conn.commit()


@router.get("/races/{number}/log")
def race_log(
    token: str, number: int, conn: sqlite3.Connection = Depends(get_conn)
) -> list[dict]:
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    return [
        {
            "id": row["id"],
            "ts": row["ts"],
            "event": row["event"],
            "note": row["note"],
            "sail_number": row["sail_number"],
        }
        for row in conn.execute(
            "SELECT l.*, b.sail_number FROM race_log l "
            "LEFT JOIN boats b ON b.id = l.boat_id "
            "WHERE l.race_id = ? ORDER BY l.ts, l.id",
            (race["id"],),
        )
    ]


@router.post("/races/{number}/log", status_code=201)
def add_log_note(
    token: str,
    number: int,
    body: LogNoteIn,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    db.log_event(conn, race["id"], "note", note=body.note)
    conn.commit()
    return {"ok": True}


@router.post("/boats", status_code=201)
def add_boat(
    token: str, body: BoatIn, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta = regatta_by_token(conn, token)
    cur = conn.execute(
        "INSERT INTO boats (regatta_id, sail_number, boat_name, boat_type, skipper, "
        "club, nation, srs, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            regatta["id"],
            body.sail_number.strip(),
            body.boat_name,
            body.boat_type,
            body.skipper,
            body.club,
            body.nation,
            body.srs,
            int(body.active),
        ),
    )
    conn.commit()
    return {"id": cur.lastrowid}


@router.patch("/boats/{boat_id}")
def patch_boat(
    token: str,
    boat_id: int,
    body: BoatPatch,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta = regatta_by_token(conn, token)
    boat = conn.execute(
        "SELECT * FROM boats WHERE id = ? AND regatta_id = ?",
        (boat_id, regatta["id"]),
    ).fetchone()
    if not boat:
        raise HTTPException(status_code=404, detail="Båten finns inte")
    fields = body.model_dump(exclude_unset=True)
    if fields:
        if "active" in fields:
            fields["active"] = int(fields["active"])
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(
            f"UPDATE boats SET {assignments} WHERE id = ?",
            (*fields.values(), boat_id),
        )
        conn.commit()
    row = conn.execute("SELECT * FROM boats WHERE id = ?", (boat_id,)).fetchone()
    return common.boat_dict(row)


def _course(conn: sqlite3.Connection, regatta_id: int, course_id: int) -> sqlite3.Row:
    course = conn.execute(
        "SELECT * FROM courses WHERE id = ? AND regatta_id = ?",
        (course_id, regatta_id),
    ).fetchone()
    if not course:
        raise HTTPException(status_code=404, detail="Banan finns inte")
    return course


@router.post("/courses", status_code=201)
def add_course(
    token: str, body: CourseIn, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta = regatta_by_token(conn, token)
    course_id = db.create_course(conn, regatta["id"], body.name, body.marks)
    conn.commit()
    return common.course_dict(
        conn, conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    )


@router.patch("/courses/{course_id}")
def patch_course(
    token: str,
    course_id: int,
    body: CoursePatch,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta = regatta_by_token(conn, token)
    _course(conn, regatta["id"], course_id)
    if body.name is not None:
        conn.execute(
            "UPDATE courses SET name = ? WHERE id = ?", (body.name.strip(), course_id)
        )
    if body.marks is not None:
        db.set_marks(conn, course_id, body.marks)
    conn.commit()
    return common.course_dict(
        conn, conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    )


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(
    token: str, course_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> None:
    regatta = regatta_by_token(conn, token)
    _course(conn, regatta["id"], course_id)
    used = conn.execute(
        "SELECT 1 FROM roundings WHERE race_id IN "
        "(SELECT id FROM races WHERE course_id = ?) LIMIT 1",
        (course_id,),
    ).fetchone()
    if used:
        raise HTTPException(
            status_code=409,
            detail="Banan används av race med rapporterade rundningar och kan inte tas bort",
        )
    conn.execute(
        "UPDATE races SET course_id = NULL WHERE course_id = ?", (course_id,)
    )
    conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    conn.commit()


@router.post("/races/{number}/course")
def set_race_course(
    token: str,
    number: int,
    body: RaceCourseIn,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    """Pick which course a race sails. Only before the start — an ongoing
    race's course is part of the reported data."""
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    if race["status"] != "upcoming":
        raise HTTPException(
            status_code=409, detail="Banan kan bara bytas innan racet startat"
        )
    course = _course(conn, regatta["id"], body.course_id)
    conn.execute(
        "UPDATE races SET course_id = ? WHERE id = ?", (body.course_id, race["id"])
    )
    db.log_event(conn, race["id"], "course_set", note=course["name"])
    conn.commit()
    return common.race_dict(conn, _race(conn, regatta["id"], number))


@router.post("/races/{number}/shorten")
def shorten_race(
    token: str, number: int, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    """Shortened course (flag S, RRS 32): the race finishes at the mark
    where roundings were last recorded — one button ends it."""
    regatta = regatta_by_token(conn, token)
    race = _race(conn, regatta["id"], number)
    if race["status"] != "ongoing":
        raise HTTPException(
            status_code=409, detail="Bara ett pågående race kan avkortas"
        )
    conn.execute(
        "UPDATE races SET shortened = 1, status = 'finished' WHERE id = ?",
        (race["id"],),
    )
    db.log_event(
        conn, race["id"], "shortened", note="Avkortad bana (S) — racet avslutat"
    )
    conn.commit()
    return common.race_dict(conn, _race(conn, regatta["id"], number))
