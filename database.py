"""SQLite storage: phones + logs.

DB is created automatically and migrated safely.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS phones (
            mac TEXT PRIMARY KEY,
            ext TEXT NOT NULL,
            password TEXT NOT NULL,
            ip TEXT,
            timezone TEXT
        )
        """
    )
    # Migrations
    cols = cur.execute("PRAGMA table_info(phones)").fetchall()
    col_names = {c[1] for c in cols}
    if "timezone" not in col_names:
        cur.execute("ALTER TABLE phones ADD COLUMN timezone TEXT")
    if "ip" not in col_names:
        cur.execute("ALTER TABLE phones ADD COLUMN ip TEXT")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        )
        """
    )
    conn.commit()


def insert_log(conn: sqlite3.Connection, timestamp: str, level: str, message: str) -> None:
    conn.execute(
        "INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
        (timestamp, level, message),
    )
    conn.commit()

