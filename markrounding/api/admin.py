"""Admin endpoints: login plus regatta/course/boat management."""

import sqlite3

import httpx
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

from .. import auth
from .. import db
from .. import sailarena
from . import common
from .deps import get_conn
from .deps import regatta_by_id
from .models import BoatIn
from .models import BoatPatch
from .models import BoatsImportIn
from .models import LoginIn
from .models import MarksIn
from .models import RegattaIn
from .models import RegattaPatch
from .models import SailarenaPreviewIn

auth_router = APIRouter(prefix="/api/auth")

router = APIRouter(prefix="/api/admin", dependencies=[Depends(auth.require_admin)])


@auth_router.post("/login")
def login(body: LoginIn, request: Request) -> dict:
    auth.check_login_rate_limit(request)
    if not auth.verify_admin_login(body.password):
        raise HTTPException(status_code=401, detail="Fel lösenord")
    return {"token": auth.create_admin_token()}


def _regatta_admin_view(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    out = common.regatta_detail(conn, row, include_inactive=True)
    out["report_token"] = row["report_token"]
    return out


@router.get("/regattas")
def list_regattas(conn: sqlite3.Connection = Depends(get_conn)) -> list[dict]:
    out = []
    for row in conn.execute("SELECT * FROM regattas ORDER BY id DESC"):
        item = common.regatta_summary(row)
        item["report_token"] = row["report_token"]
        out.append(item)
    return out


@router.post("/regattas", status_code=201)
def create_regatta(
    body: RegattaIn, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    slug = db.unique_slug(conn, body.name)
    cur = conn.execute(
        "INSERT INTO regattas (slug, name, venue, organizer, lat, lon, start_date, "
        "end_date, sailarena_url, report_token, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            slug,
            body.name.strip(),
            body.venue,
            body.organizer,
            body.lat,
            body.lon,
            body.start_date,
            body.end_date,
            body.sailarena_url,
            db.new_report_token(),
            db.utcnow_iso(),
        ),
    )
    regatta_id = cur.lastrowid
    if body.marks:
        db.set_marks(conn, regatta_id, body.marks)
    db.sync_race_count(conn, regatta_id, body.race_count)
    conn.commit()
    return _regatta_admin_view(conn, regatta_by_id(conn, regatta_id))


@router.get("/regattas/{regatta_id}")
def get_regatta(
    regatta_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    return _regatta_admin_view(conn, regatta_by_id(conn, regatta_id))


@router.patch("/regattas/{regatta_id}")
def patch_regatta(
    regatta_id: int,
    body: RegattaPatch,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta_by_id(conn, regatta_id)
    fields = body.model_dump(exclude_unset=True)
    race_count = fields.pop("race_count", None)
    if fields:
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(
            f"UPDATE regattas SET {assignments} WHERE id = ?",
            (*fields.values(), regatta_id),
        )
    if race_count is not None:
        db.sync_race_count(conn, regatta_id, race_count)
    conn.commit()
    return _regatta_admin_view(conn, regatta_by_id(conn, regatta_id))


@router.delete("/regattas/{regatta_id}", status_code=204)
def delete_regatta(
    regatta_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> None:
    regatta_by_id(conn, regatta_id)
    conn.execute("DELETE FROM regattas WHERE id = ?", (regatta_id,))
    conn.commit()


@router.post("/regattas/{regatta_id}/regenerate-token")
def regenerate_token(
    regatta_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta_by_id(conn, regatta_id)
    token = db.new_report_token()
    conn.execute(
        "UPDATE regattas SET report_token = ? WHERE id = ?", (token, regatta_id)
    )
    conn.commit()
    return {"report_token": token}


@router.put("/regattas/{regatta_id}/marks")
def set_marks(
    regatta_id: int, body: MarksIn, conn: sqlite3.Connection = Depends(get_conn)
) -> list[dict]:
    regatta_by_id(conn, regatta_id)
    db.set_marks(conn, regatta_id, body.marks)
    conn.commit()
    return [
        {"id": row["id"], "seq": row["seq"], "name": row["name"]}
        for row in conn.execute(
            "SELECT * FROM marks WHERE regatta_id = ? ORDER BY seq", (regatta_id,)
        )
    ]


@router.post("/sailarena/preview")
def sailarena_preview(body: SailarenaPreviewIn) -> dict:
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Ogiltig URL")
    try:
        return sailarena.fetch_event(body.url)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502, detail="Kunde inte hämta sidan från Sailarena"
        )


@router.post("/regattas/{regatta_id}/boats/import")
def import_boats(
    regatta_id: int,
    body: BoatsImportIn,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    """Store an imported participant list. With replace=True existing boats
    without roundings are removed first; boats with roundings are kept."""
    regatta_by_id(conn, regatta_id)
    if body.replace:
        conn.execute(
            "DELETE FROM boats WHERE regatta_id = ? AND id NOT IN "
            "(SELECT DISTINCT boat_id FROM roundings)",
            (regatta_id,),
        )
    existing = {
        row["sail_number"].strip().upper()
        for row in conn.execute(
            "SELECT sail_number FROM boats WHERE regatta_id = ?", (regatta_id,)
        )
    }
    added = 0
    for boat in body.boats:
        key = boat.sail_number.strip().upper()
        if not key or key in existing:
            continue
        existing.add(key)
        conn.execute(
            "INSERT INTO boats (regatta_id, sail_number, boat_name, boat_type, "
            "skipper, club, nation, srs, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                regatta_id,
                boat.sail_number.strip(),
                boat.boat_name,
                boat.boat_type,
                boat.skipper,
                boat.club,
                boat.nation,
                boat.srs,
                int(boat.active),
            ),
        )
        added += 1
    conn.commit()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM boats WHERE regatta_id = ?", (regatta_id,)
    ).fetchone()["n"]
    return {"added": added, "total": total}


@router.post("/regattas/{regatta_id}/boats", status_code=201)
def add_boat(
    regatta_id: int, body: BoatIn, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta_by_id(conn, regatta_id)
    cur = conn.execute(
        "INSERT INTO boats (regatta_id, sail_number, boat_name, boat_type, skipper, "
        "club, nation, srs, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            regatta_id,
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


@router.patch("/regattas/{regatta_id}/boats/{boat_id}")
def patch_boat(
    regatta_id: int,
    boat_id: int,
    body: BoatPatch,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    regatta_by_id(conn, regatta_id)
    boat = conn.execute(
        "SELECT * FROM boats WHERE id = ? AND regatta_id = ?", (boat_id, regatta_id)
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


@router.delete("/regattas/{regatta_id}/boats/{boat_id}", status_code=204)
def delete_boat(
    regatta_id: int, boat_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> None:
    regatta_by_id(conn, regatta_id)
    deleted = conn.execute(
        "DELETE FROM boats WHERE id = ? AND regatta_id = ?", (boat_id, regatta_id)
    )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="Båten finns inte")
    conn.commit()
