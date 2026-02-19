#!/usr/bin/env python3
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = "/var/lib/gps-logger/gps_logs.db"


def ensure_parent_dir() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_conn():
    ensure_parent_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(default_interval_sec: float, default_min_speed: float, default_max_hdop: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gps_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                lat REAL,
                lon REAL,
                alt_m REAL,
                speed_mps REAL,
                course_deg REAL,
                hdop REAL,
                satellites INTEGER,
                fix_mode INTEGER,
                source TEXT DEFAULT 'gpsd'
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_gps_log_timestamp
            ON gps_log(timestamp_utc)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        set_setting(conn, "log_interval_sec", str(default_interval_sec))
        set_setting(conn, "min_speed_write_mps", str(default_min_speed))
        set_setting(conn, "max_hdop_for_log", str(default_max_hdop))


def set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings(key, value, updated_at)
        VALUES(?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=CURRENT_TIMESTAMP
        """,
        (key, value),
    )


def fetch_setting(key: str, fallback: float) -> float:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return fallback
    try:
        return float(row["value"])
    except (TypeError, ValueError):
        return fallback
