"""Row-to-dict serializers and race progress computation."""

import re
import sqlite3
from datetime import datetime


def regatta_summary(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "venue": row["venue"],
        "organizer": row["organizer"],
        "lat": row["lat"],
        "lon": row["lon"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "sailarena_url": row["sailarena_url"],
    }


def boat_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "sail_number": row["sail_number"],
        "boat_name": row["boat_name"],
        "boat_type": row["boat_type"],
        "skipper": row["skipper"],
        "club": row["club"],
        "nation": row["nation"],
        "srs": row["srs"],
        "active": bool(row["active"]),
    }


def sail_number_key(sail_number: str) -> tuple:
    """Natural sort: 'SWE 106' < 'SWE 3031', digits compared numerically."""
    parts = re.split(r"(\d+)", sail_number.upper())
    return tuple(int(p) if p.isdigit() else p.strip() for p in parts if p.strip())


def race_dict(conn: sqlite3.Connection, race: sqlite3.Row) -> dict:
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM roundings WHERE race_id = ?", (race["id"],)
    ).fetchone()["n"]
    return {
        "id": race["id"],
        "number": race["number"],
        "status": race["status"],
        "started_at": race["started_at"],
        "planned_start": race["planned_start"],
        "prep_flag": race["prep_flag"],
        "general_recalls": race["general_recalls"],
        "rounding_count": count,
    }


def regatta_detail(
    conn: sqlite3.Connection, regatta: sqlite3.Row, include_inactive: bool = False
) -> dict:
    out = regatta_summary(regatta)
    out["marks"] = [
        {"id": row["id"], "seq": row["seq"], "name": row["name"]}
        for row in conn.execute(
            "SELECT * FROM marks WHERE regatta_id = ? ORDER BY seq", (regatta["id"],)
        )
    ]
    out["races"] = [
        race_dict(conn, row)
        for row in conn.execute(
            "SELECT * FROM races WHERE regatta_id = ? ORDER BY number",
            (regatta["id"],),
        )
    ]
    boat_sql = "SELECT * FROM boats WHERE regatta_id = ?"
    if not include_inactive:
        boat_sql += " AND active = 1"
    boats = [boat_dict(row) for row in conn.execute(boat_sql, (regatta["id"],))]
    boats.sort(key=lambda b: sail_number_key(b["sail_number"]))
    out["boats"] = boats
    return out


def race_progress(conn: sqlite3.Connection, regatta_id: int, race: sqlite3.Row) -> dict:
    """Per-mark rounding order plus a leaderboard.

    Leaderboard ranks boats by furthest mark reached (course order), ties
    broken by who rounded that mark first. Boats without roundings follow,
    in sail number order.
    """
    marks = list(
        conn.execute(
            "SELECT * FROM marks WHERE regatta_id = ? ORDER BY seq", (regatta_id,)
        )
    )
    boats = {
        row["id"]: boat_dict(row)
        for row in conn.execute(
            "SELECT * FROM boats WHERE regatta_id = ?", (regatta_id,)
        )
    }
    seq_by_mark = {m["id"]: m["seq"] for m in marks}

    rounding_rows = list(
        conn.execute(
            "SELECT * FROM roundings WHERE race_id = ? ORDER BY ts, id", (race["id"],)
        )
    )

    by_mark: dict[int, list[dict]] = {m["id"]: [] for m in marks}
    progress: dict[int, dict] = {}
    for row in rounding_rows:
        mark_id = row["mark_id"]
        if mark_id not in by_mark or row["boat_id"] not in boats:
            continue  # rounding at a mark/boat that has since been removed
        at_mark = by_mark[mark_id]
        # Time gap to the first boat at this mark — the raw material for
        # the public view's gap tables and development chart.
        gap = 0
        if at_mark:
            first = datetime.fromisoformat(at_mark[0]["ts"])
            gap = int((datetime.fromisoformat(row["ts"]) - first).total_seconds())
        entry = {
            "id": row["id"],
            "boat": boats[row["boat_id"]],
            "ts": row["ts"],
            "position": len(at_mark) + 1,
            "gap_seconds": gap,
        }
        at_mark.append(entry)
        seq = seq_by_mark[mark_id]
        best = progress.get(row["boat_id"])
        if not best or seq > best["seq"]:
            progress[row["boat_id"]] = {"seq": seq, "ts": row["ts"]}

    status_by_boat = {
        row["boat_id"]: row["code"]
        for row in conn.execute(
            "SELECT boat_id, code FROM race_boat_status WHERE race_id = ?",
            (race["id"],),
        )
    }
    # ZFP (20 % scoring penalty) still races and keeps its ranking; every
    # other code (OCS, BFD, UFD, DNS, DNF, RET, DSQ) drops the boat to the
    # bottom of the leaderboard with the code shown.
    excluded = {
        bid: code for bid, code in status_by_boat.items() if code != "ZFP"
    }

    leaderboard = []
    ranked = sorted(
        (item for item in progress.items() if item[0] not in excluded),
        key=lambda item: (-item[1]["seq"], item[1]["ts"]),
    )
    mark_name_by_seq = {m["seq"]: m["name"] for m in marks}
    for boat_id, best in ranked:
        leaderboard.append(
            {
                "boat": boats[boat_id],
                "last_mark_seq": best["seq"],
                "last_mark_name": mark_name_by_seq.get(best["seq"], ""),
                "last_ts": best["ts"],
                "code": status_by_boat.get(boat_id),
            }
        )
    remaining = [
        b
        for bid, b in boats.items()
        if bid not in progress and bid not in excluded and b["active"]
    ]
    remaining.sort(key=lambda b: sail_number_key(b["sail_number"]))
    for boat in remaining:
        leaderboard.append(
            {
                "boat": boat,
                "last_mark_seq": None,
                "last_mark_name": "",
                "last_ts": None,
                "code": status_by_boat.get(boat["id"]),
            }
        )
    coded = sorted(
        excluded.items(), key=lambda item: sail_number_key(boats[item[0]]["sail_number"])
    )
    for boat_id, code in coded:
        best = progress.get(boat_id)
        leaderboard.append(
            {
                "boat": boats[boat_id],
                "last_mark_seq": best["seq"] if best else None,
                "last_mark_name": mark_name_by_seq.get(best["seq"], "") if best else "",
                "last_ts": best["ts"] if best else None,
                "code": code,
            }
        )

    return {
        "race": race_dict(conn, race),
        "marks": [
            {
                "id": m["id"],
                "seq": m["seq"],
                "name": m["name"],
                "roundings": by_mark[m["id"]],
            }
            for m in marks
        ],
        "leaderboard": leaderboard,
    }
