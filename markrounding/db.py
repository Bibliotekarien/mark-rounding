"""SQLite storage. Raw sqlite3 (stdlib), WAL mode, no ORM.

Schema is applied idempotently at startup (CREATE TABLE IF NOT EXISTS).
All timestamps are ISO-8601 UTC with a trailing Z.
"""

import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime
from datetime import timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS regattas (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    venue TEXT NOT NULL DEFAULT '',
    organizer TEXT NOT NULL DEFAULT '',
    lat REAL,
    lon REAL,
    start_date TEXT,
    end_date TEXT,
    sailarena_url TEXT NOT NULL DEFAULT '',
    report_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marks (
    id INTEGER PRIMARY KEY,
    regatta_id INTEGER NOT NULL REFERENCES regattas(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (regatta_id, seq)
);

CREATE TABLE IF NOT EXISTS races (
    id INTEGER PRIMARY KEY,
    regatta_id INTEGER NOT NULL REFERENCES regattas(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'upcoming',
    started_at TEXT,
    planned_start TEXT,
    prep_flag TEXT NOT NULL DEFAULT 'P',
    general_recalls INTEGER NOT NULL DEFAULT 0,
    UNIQUE (regatta_id, number),
    CHECK (status IN ('upcoming', 'ongoing', 'finished'))
);

CREATE TABLE IF NOT EXISTS race_boat_status (
    id INTEGER PRIMARY KEY,
    race_id INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    boat_id INTEGER NOT NULL REFERENCES boats(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    ts TEXT NOT NULL,
    UNIQUE (race_id, boat_id),
    CHECK (code IN ('OCS', 'UFD', 'BFD', 'ZFP', 'DNS', 'DNF', 'RET', 'DSQ'))
);

CREATE TABLE IF NOT EXISTS boats (
    id INTEGER PRIMARY KEY,
    regatta_id INTEGER NOT NULL REFERENCES regattas(id) ON DELETE CASCADE,
    sail_number TEXT NOT NULL,
    boat_name TEXT NOT NULL DEFAULT '',
    boat_type TEXT NOT NULL DEFAULT '',
    skipper TEXT NOT NULL DEFAULT '',
    club TEXT NOT NULL DEFAULT '',
    nation TEXT NOT NULL DEFAULT '',
    srs TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_boats_regatta ON boats (regatta_id);

CREATE TABLE IF NOT EXISTS roundings (
    id INTEGER PRIMARY KEY,
    race_id INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    mark_id INTEGER NOT NULL REFERENCES marks(id) ON DELETE CASCADE,
    boat_id INTEGER NOT NULL REFERENCES boats(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    UNIQUE (race_id, mark_id, boat_id)
);

CREATE INDEX IF NOT EXISTS idx_roundings_race ON roundings (race_id);

CREATE TABLE IF NOT EXISTS race_log (
    id INTEGER PRIMARY KEY,
    race_id INTEGER NOT NULL REFERENCES races(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    boat_id INTEGER REFERENCES boats(id) ON DELETE SET NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_race_log_race ON race_log (race_id);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Additive, idempotent migrations for databases created before the
    # start procedure feature (no migration engine — see CLAUDE.md).
    _ensure_column(conn, "races", "planned_start", "planned_start TEXT")
    _ensure_column(conn, "races", "prep_flag", "prep_flag TEXT NOT NULL DEFAULT 'P'")
    _ensure_column(
        conn, "races", "general_recalls", "general_recalls INTEGER NOT NULL DEFAULT 0"
    )
    conn.commit()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_report_token() -> str:
    return secrets.token_urlsafe(18)


def slugify(name: str) -> str:
    # ASCII-fold (å→a, ä→a, ö→o), keep alnum, dash-separate the rest.
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    return slug or "regatta"


def unique_slug(conn: sqlite3.Connection, name: str) -> str:
    base = slugify(name)
    slug = base
    n = 2
    while conn.execute("SELECT 1 FROM regattas WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{n}"
        n += 1
    return slug


def log_event(
    conn: sqlite3.Connection,
    race_id: int,
    event: str,
    boat_id: int | None = None,
    note: str = "",
) -> None:
    """Append to the committee protocol. Every committee action is logged
    so the start vessel has a written record of the race."""
    conn.execute(
        "INSERT INTO race_log (race_id, ts, event, boat_id, note) VALUES (?, ?, ?, ?, ?)",
        (race_id, utcnow_iso(), event, boat_id, note),
    )


def set_marks(conn: sqlite3.Connection, regatta_id: int, names: list[str]) -> None:
    """Replace the course with the given ordered mark names.

    Marks are matched by position so renaming keeps existing roundings.
    Marks beyond the new course length are deleted — their roundings
    cascade away, which the UI warns about before shortening a course.
    """
    for seq, name in enumerate(names, start=1):
        updated = conn.execute(
            "UPDATE marks SET name = ? WHERE regatta_id = ? AND seq = ?",
            (name.strip(), regatta_id, seq),
        )
        if updated.rowcount == 0:
            conn.execute(
                "INSERT INTO marks (regatta_id, seq, name) VALUES (?, ?, ?)",
                (regatta_id, seq, name.strip()),
            )
    conn.execute(
        "DELETE FROM marks WHERE regatta_id = ? AND seq > ?",
        (regatta_id, len(names)),
    )


def sync_race_count(conn: sqlite3.Connection, regatta_id: int, count: int) -> None:
    """Ensure races 1..count exist. Extra races are removed only if they have
    no roundings (protects reported data from an accidental count decrease)."""
    existing = {
        row["number"]: row["id"]
        for row in conn.execute(
            "SELECT id, number FROM races WHERE regatta_id = ?", (regatta_id,)
        )
    }
    for number in range(1, count + 1):
        if number not in existing:
            conn.execute(
                "INSERT INTO races (regatta_id, number) VALUES (?, ?)",
                (regatta_id, number),
            )
    for number, race_id in existing.items():
        if number > count:
            has_data = conn.execute(
                "SELECT 1 FROM roundings WHERE race_id = ? LIMIT 1", (race_id,)
            ).fetchone()
            if not has_data:
                conn.execute("DELETE FROM races WHERE id = ?", (race_id,))
