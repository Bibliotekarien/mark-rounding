"""Shared FastAPI dependencies."""

import sqlite3
from collections.abc import Iterator

from fastapi import HTTPException
from fastapi import Request

from .. import db


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def regatta_by_slug(conn: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM regattas WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Regattan finns inte")
    return row


def regatta_by_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM regattas WHERE report_token = ?", (token,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ogiltig rapporteringslänk")
    return row


def regatta_by_id(conn: sqlite3.Connection, regatta_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM regattas WHERE id = ?", (regatta_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Regattan finns inte")
    return row
