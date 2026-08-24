"""Public read-only endpoints for the start page and regatta pages."""

import sqlite3

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from .. import weather
from . import common
from .deps import get_conn
from .deps import regatta_by_slug

router = APIRouter(prefix="/api")


@router.get("/regattas")
def list_regattas(conn: sqlite3.Connection = Depends(get_conn)) -> list[dict]:
    out = []
    for row in conn.execute(
        "SELECT * FROM regattas ORDER BY start_date IS NULL, start_date DESC, id DESC"
    ):
        item = common.regatta_summary(row)
        races = conn.execute(
            "SELECT status, COUNT(*) AS n FROM races WHERE regatta_id = ? GROUP BY status",
            (row["id"],),
        ).fetchall()
        counts = {r["status"]: r["n"] for r in races}
        item["race_count"] = sum(counts.values())
        item["finished_races"] = counts.get("finished", 0)
        item["ongoing_races"] = counts.get("ongoing", 0)
        live = conn.execute(
            "SELECT number FROM races WHERE regatta_id = ? AND status = 'ongoing' "
            "ORDER BY number LIMIT 1",
            (row["id"],),
        ).fetchone()
        item["live_race"] = live["number"] if live else None
        item["boat_count"] = conn.execute(
            "SELECT COUNT(*) AS n FROM boats WHERE regatta_id = ? AND active = 1",
            (row["id"],),
        ).fetchone()["n"]
        out.append(item)
    return out


@router.get("/regattas/{slug}")
def regatta_detail(
    slug: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta = regatta_by_slug(conn, slug)
    return common.regatta_detail(conn, regatta)


@router.get("/regattas/{slug}/races/{number}")
def race_detail(
    slug: str, number: int, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta = regatta_by_slug(conn, slug)
    race = conn.execute(
        "SELECT * FROM races WHERE regatta_id = ? AND number = ?",
        (regatta["id"], number),
    ).fetchone()
    if not race:
        raise HTTPException(status_code=404, detail="Racet finns inte")
    return common.race_progress(
        conn, regatta["id"], race, include_times=bool(regatta["show_times"])
    )


@router.get("/regattas/{slug}/weather")
def regatta_weather(
    slug: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    regatta = regatta_by_slug(conn, slug)
    if regatta["lat"] is None or regatta["lon"] is None:
        raise HTTPException(
            status_code=404, detail="Regattan saknar koordinater för väder"
        )
    try:
        return weather.get_weather(regatta["lat"], regatta["lon"])
    except Exception:
        raise HTTPException(status_code=502, detail="Vädertjänsten svarar inte")
