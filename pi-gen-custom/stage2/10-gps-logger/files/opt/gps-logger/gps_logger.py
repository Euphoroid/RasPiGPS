#!/usr/bin/env python3
import json
import os
import socket
import time
from datetime import datetime, timezone

from db import fetch_setting, get_conn, init_db

CONFIG_PATH = "/etc/gps-logger/config.json"
STATUS_PATH = "/run/gps-logger/status.json"


class GPSState:
    def __init__(self):
        self.lat = None
        self.lon = None
        self.alt = None
        self.speed = 0.0
        self.track = None
        self.fix_mode = 0
        self.hdop = None
        self.satellites = 0
        self.last_seen = None
        self.gps_time_utc = None


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_runtime_dirs():
    os.makedirs("/run/gps-logger", exist_ok=True)
    os.makedirs("/var/lib/gps-logger", exist_ok=True)


def write_status(state: GPSState, free_bytes: int):
    system_time = datetime.now(timezone.utc).isoformat()
    status_time = state.gps_time_utc or datetime.now(timezone.utc).isoformat()
    time_source = "gps" if state.gps_time_utc else "system"
    payload = {
        "timestamp_utc": status_time,
        "timestamp_source": time_source,
        "system_timestamp_utc": system_time,
        "fix_mode": state.fix_mode,
        "satellites": state.satellites,
        "hdop": state.hdop,
        "speed_mps": state.speed,
        "lat": state.lat,
        "lon": state.lon,
        "alt_m": state.alt,
        "course_deg": state.track,
        "disk_free_bytes": free_bytes,
    }
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, STATUS_PATH)


def connect_gpsd() -> socket.socket:
    s = socket.create_connection(("127.0.0.1", 2947), timeout=10)
    s.sendall(b'?WATCH={"enable":true,"json":true};\n')
    s.settimeout(5)
    return s


def parse_reports(sock: socket.socket, state: GPSState, buffer: bytes) -> bytes:
    chunk = sock.recv(4096)
    if not chunk:
        raise ConnectionError("gpsd closed connection")
    data = buffer + chunk
    while b"\n" in data:
        line, data = data.split(b"\n", 1)
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            continue
        cls = msg.get("class")
        if cls == "TPV":
            state.fix_mode = int(msg.get("mode") or 0)
            state.lat = msg.get("lat")
            state.lon = msg.get("lon")
            state.alt = msg.get("alt")
            state.speed = float(msg.get("speed") or 0.0)
            state.track = msg.get("track")
            tpv_time = msg.get("time")
            if isinstance(tpv_time, str) and tpv_time:
                state.gps_time_utc = tpv_time
            state.last_seen = datetime.now(timezone.utc)
        elif cls == "SKY":
            state.hdop = msg.get("hdop")
            sats = msg.get("satellites") or []
            state.satellites = sum(1 for s in sats if s.get("used"))
    return data


def should_write(state: GPSState, min_speed: float, max_hdop: float) -> bool:
    if state.fix_mode < 2:
        return False
    if state.lat is None or state.lon is None:
        return False
    if state.hdop is None:
        return False
    if float(state.hdop) > max_hdop:
        return False
    return state.speed >= min_speed


def insert_log(state: GPSState):
    ts = state.gps_time_utc or datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO gps_log(
                timestamp_utc, lat, lon, alt_m, speed_mps, course_deg,
                hdop, satellites, fix_mode
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                state.lat,
                state.lon,
                state.alt,
                state.speed,
                state.track,
                state.hdop,
                state.satellites,
                state.fix_mode,
            ),
        )


def main():
    ensure_runtime_dirs()
    cfg = load_config()
    init_db(
        default_interval_sec=float(cfg.get("log_interval_sec", 1.0)),
        default_min_speed=float(cfg.get("min_speed_write_mps", 0.8)),
        default_max_hdop=float(cfg.get("max_hdop_for_log", 3.0)),
    )

    state = GPSState()
    sock = None
    recv_buffer = b""
    next_write = time.monotonic()

    while True:
        if sock is None:
            try:
                sock = connect_gpsd()
            except OSError:
                time.sleep(2)
                continue

        try:
            recv_buffer = parse_reports(sock, state, recv_buffer)
        except (socket.timeout, TimeoutError):
            pass
        except OSError:
            try:
                sock.close()
            except Exception:
                pass
            sock = None
            recv_buffer = b""
            time.sleep(1)
            continue

        now = time.monotonic()
        if now >= next_write:
            interval = max(fetch_setting("log_interval_sec", 1.0), 0.5)
            min_speed = max(fetch_setting("min_speed_write_mps", 0.8), 0.0)
            max_hdop = max(fetch_setting("max_hdop_for_log", float(cfg.get("max_hdop_for_log", 3.0))), 0.5)
            if should_write(state, min_speed, max_hdop):
                insert_log(state)
            st = os.statvfs("/var/lib/gps-logger")
            free_bytes = st.f_bavail * st.f_frsize
            write_status(state, free_bytes)
            next_write = now + interval


if __name__ == "__main__":
    main()
