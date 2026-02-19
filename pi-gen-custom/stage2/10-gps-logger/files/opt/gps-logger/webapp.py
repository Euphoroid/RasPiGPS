#!/usr/bin/env python3
import json
import os
import glob
import subprocess
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from flask import Flask, Response, jsonify, render_template, request

from db import fetch_setting, get_conn, init_db, set_setting

CONFIG_PATH = "/etc/gps-logger/config.json"
STATUS_PATH = "/run/gps-logger/status.json"
GPSD_DEFAULT_PATH = "/etc/default/gpsd"

app = Flask(__name__, template_folder="templates", static_folder="static")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def read_status() -> dict:
    if not os.path.exists(STATUS_PATH):
        return {}
    with open(STATUS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_cmd(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    out = proc.stdout if proc.stdout.strip() else proc.stderr
    return proc.returncode, out.strip()


def scan_gps_devices() -> list[str]:
    candidates = set()
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/serial/by-id/*"):
        for path in glob.glob(pattern):
            if os.path.exists(path):
                candidates.add(path)
    return sorted(candidates)


def read_gpsd_device() -> str:
    if not os.path.exists(GPSD_DEFAULT_PATH):
        return ""
    with open(GPSD_DEFAULT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("DEVICES="):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                return raw.split()[0] if raw else ""
    return ""


def set_gpsd_device(device: str) -> None:
    lines = []
    replaced = False
    if os.path.exists(GPSD_DEFAULT_PATH):
        with open(GPSD_DEFAULT_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    out = []
    for line in lines:
        if line.startswith("DEVICES="):
            out.append(f'DEVICES="{device}"\n')
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f'DEVICES="{device}"\n')
    with open(GPSD_DEFAULT_PATH, "w", encoding="utf-8") as f:
        f.writelines(out)


def restart_services(units: list[str]) -> list[str]:
    errors = []
    for unit in units:
        code, out = run_cmd(["systemctl", "restart", unit])
        if code != 0:
            errors.append(f"{unit}: {out}")
    return errors


def to_iso8601(v: str) -> str:
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid datetime")
    return dt.astimezone(timezone.utc).isoformat()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    status = read_status()
    return jsonify(status)


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    cfg = load_config()
    if request.method == "GET":
        return jsonify({
            "log_interval_sec": fetch_setting("log_interval_sec", float(cfg.get("log_interval_sec", 1.0))),
            "min_speed_write_mps": fetch_setting("min_speed_write_mps", float(cfg.get("min_speed_write_mps", 0.8))),
            "disk_free_threshold_mb": float(cfg.get("disk_free_threshold_mb", 200)),
            "disk_free_target_mb": float(cfg.get("disk_free_target_mb", 300)),
        })

    body = request.get_json(force=True, silent=True) or {}
    try:
        log_interval = float(body.get("log_interval_sec", fetch_setting("log_interval_sec", 1.0)))
        min_speed = float(body.get("min_speed_write_mps", fetch_setting("min_speed_write_mps", 0.8)))
        disk_threshold = float(body.get("disk_free_threshold_mb", cfg.get("disk_free_threshold_mb", 200)))
        disk_target = float(body.get("disk_free_target_mb", cfg.get("disk_free_target_mb", 300)))
    except (TypeError, ValueError):
        return jsonify({"error": "settings must be numeric"}), 400

    if log_interval < 0.5:
        return jsonify({"error": "log_interval_sec must be >= 0.5"}), 400
    if min_speed < 0:
        return jsonify({"error": "min_speed_write_mps must be >= 0"}), 400
    if disk_target <= disk_threshold:
        return jsonify({"error": "disk_free_target_mb must be > disk_free_threshold_mb"}), 400

    with get_conn() as conn:
        set_setting(conn, "log_interval_sec", str(log_interval))
        set_setting(conn, "min_speed_write_mps", str(min_speed))

    cfg["disk_free_threshold_mb"] = disk_threshold
    cfg["disk_free_target_mb"] = disk_target
    save_config(cfg)

    return jsonify({"ok": True})


@app.route("/api/export.gpx")
def api_export_gpx():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "start and end are required"}), 400

    try:
        start_iso = to_iso8601(start)
        end_iso = to_iso8601(end)
    except ValueError:
        return jsonify({"error": "datetime must be ISO8601"}), 400

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT timestamp_utc, lat, lon, alt_m, speed_mps, course_deg
            FROM gps_log
            WHERE timestamp_utc >= ? AND timestamp_utc <= ?
              AND lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY timestamp_utc ASC
            """,
            (start_iso, end_iso),
        ).fetchall()

    trkpts = []
    for r in rows:
        ele = "" if r["alt_m"] is None else f"<ele>{r['alt_m']:.2f}</ele>"
        speed = "" if r["speed_mps"] is None else f"<speed>{r['speed_mps']:.3f}</speed>"
        course = "" if r["course_deg"] is None else f"<course>{r['course_deg']:.2f}</course>"
        trkpts.append(
            (
                f"<trkpt lat=\"{r['lat']:.8f}\" lon=\"{r['lon']:.8f}\">"
                f"{ele}<time>{escape(r['timestamp_utc'])}</time>{speed}{course}</trkpt>"
            )
        )

    gpx = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<gpx version=\"1.1\" creator=\"gps-logger\" xmlns=\"http://www.topografix.com/GPX/1/1\">"
        "<trk><name>gps-log</name><trkseg>"
        + "".join(trkpts)
        + "</trkseg></trk></gpx>"
    )

    return Response(
        gpx,
        mimetype="application/gpx+xml",
        headers={"Content-Disposition": "attachment; filename=gps-log.gpx"},
    )


@app.route("/api/gps/devices", methods=["GET", "POST"])
def api_gps_devices():
    cfg = load_config()
    if request.method == "GET":
        current = str(cfg.get("gps_device") or read_gpsd_device() or "")
        return jsonify({
            "current_device": current,
            "devices": scan_gps_devices(),
        })

    body = request.get_json(force=True, silent=True) or {}
    device = str(body.get("device") or "").strip()
    if not device.startswith("/dev/"):
        return jsonify({"error": "device must be an absolute /dev path"}), 400
    if len(device) > 200:
        return jsonify({"error": "device path too long"}), 400

    cfg["gps_device"] = device
    save_config(cfg)
    set_gpsd_device(device)
    errors = restart_services(["gpsd.service", "gps-logger.service"])

    return jsonify({
        "ok": len(errors) == 0,
        "device": device,
        "warnings": errors,
    })


@app.route("/api/logs/errors")
def api_error_logs():
    raw_lines = request.args.get("lines", "200")
    try:
        lines = int(raw_lines)
    except ValueError:
        lines = 200
    lines = min(max(lines, 20), 500)

    cmd = [
        "journalctl",
        "--no-pager",
        "-b",
        "-n",
        str(lines),
        "-p",
        "warning..alert",
        "-u",
        "gps-logger.service",
        "-u",
        "gps-web.service",
        "-u",
        "gpsd.service",
        "-u",
        "hostapd.service",
        "-u",
        "dnsmasq.service",
    ]
    code, out = run_cmd(cmd)
    if code != 0:
        return jsonify({"error": out or "failed to read logs"}), 500
    return jsonify({"lines": lines, "log": out})


def main():
    cfg = load_config()
    init_db(
        default_interval_sec=float(cfg.get("log_interval_sec", 1.0)),
        default_min_speed=float(cfg.get("min_speed_write_mps", 0.8)),
    )
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
