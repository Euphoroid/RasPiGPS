#!/usr/bin/env python3
import json
import os

from db import DB_PATH, get_conn

CONFIG_PATH = "/etc/gps-logger/config.json"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def free_mb(path: str) -> float:
    st = os.statvfs(path)
    return (st.f_bavail * st.f_frsize) / (1024 * 1024)


def rotate(threshold_mb: float, target_mb: float):
    db_dir = os.path.dirname(DB_PATH)
    current = free_mb(db_dir)
    if current >= threshold_mb:
        return

    batch = 2000
    with get_conn() as conn:
        while current < target_mb:
            cur = conn.execute(
                """
                DELETE FROM gps_log
                WHERE id IN (
                    SELECT id FROM gps_log
                    ORDER BY timestamp_utc ASC
                    LIMIT ?
                )
                """,
                (batch,),
            )
            if cur.rowcount <= 0:
                break
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            current = free_mb(db_dir)


def main():
    cfg = load_config()
    threshold = float(cfg.get("disk_free_threshold_mb", 200))
    target = float(cfg.get("disk_free_target_mb", max(300, threshold + 100)))
    rotate(threshold_mb=threshold, target_mb=target)


if __name__ == "__main__":
    main()
