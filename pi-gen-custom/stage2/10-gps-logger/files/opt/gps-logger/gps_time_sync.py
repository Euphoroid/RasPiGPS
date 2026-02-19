#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import time
from datetime import datetime, timezone

STATUS_PATH = "/run/gps-logger/time-sync-status.json"


def connect_gpsd() -> socket.socket:
    s = socket.create_connection(("127.0.0.1", 2947), timeout=10)
    s.sendall(b'?WATCH={"enable":true,"json":true};\n')
    s.settimeout(10)
    return s


def parse_gps_time(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def set_system_time(epoch_sec: int) -> tuple[bool, str]:
    cmd = ["/bin/date", "-u", "-s", f"@{epoch_sec}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode == 0, out


def write_status(payload: dict) -> None:
    os.makedirs("/run/gps-logger", exist_ok=True)
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, STATUS_PATH)


def main():
    synced = False
    buffer = b""
    sock = None
    while True:
        if sock is None:
            try:
                sock = connect_gpsd()
            except OSError as e:
                write_status({"ok": False, "state": "gpsd_connect_failed", "error": str(e)})
                time.sleep(5)
                continue

        try:
            chunk = sock.recv(4096)
        except OSError as e:
            write_status({"ok": False, "state": "gpsd_read_failed", "error": str(e)})
            try:
                sock.close()
            except OSError:
                pass
            sock = None
            time.sleep(2)
            continue

        if not chunk:
            time.sleep(1)
            continue

        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8", errors="ignore"))
            except json.JSONDecodeError:
                continue

            if msg.get("class") != "TPV":
                continue
            mode = int(msg.get("mode") or 0)
            gps_dt = parse_gps_time(msg.get("time") or "")
            if mode < 2 or gps_dt is None:
                continue
            if gps_dt.year < 2020:
                continue

            now = datetime.now(timezone.utc)
            drift = abs((gps_dt - now).total_seconds())

            if drift > 2.0:
                ok, out = set_system_time(int(gps_dt.timestamp()))
                write_status({
                    "ok": ok,
                    "state": "set_time",
                    "gps_time_utc": gps_dt.isoformat(),
                    "drift_sec_before_set": drift,
                    "message": out,
                })
                if ok:
                    synced = True
            else:
                write_status({
                    "ok": True,
                    "state": "in_sync",
                    "gps_time_utc": gps_dt.isoformat(),
                    "drift_sec": drift,
                })
                synced = True

            if synced:
                # Keep running for periodic correction with low CPU cost.
                time.sleep(30)


if __name__ == "__main__":
    main()
