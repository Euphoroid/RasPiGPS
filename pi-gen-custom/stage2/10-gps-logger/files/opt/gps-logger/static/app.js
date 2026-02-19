function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value;
}

function formatNum(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "-";
  return Number(v).toFixed(digits);
}

function formatFix(mode) {
  if (mode === 3) return "3D";
  if (mode === 2) return "2D";
  if (mode === 1) return "NO FIX";
  return "-";
}

function bytesToMiB(bytes) {
  if (!Number.isFinite(bytes)) return "-";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatIsoToLocal(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function setMessage(id, text, isError = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("error", !!isError);
}

async function loadStatus() {
  try {
    const r = await fetch("/api/status", { cache: "no-store" });
    const st = await r.json();
    setText("st-fix", formatFix(st.fix_mode));
    setText("st-sats", st.satellites ?? "-");
    setText("st-hdop", formatNum(st.hdop, 1));
    setText("st-speed", formatNum(st.speed_mps, 2));
    setText("st-lat", formatNum(st.lat, 6));
    setText("st-lon", formatNum(st.lon, 6));
    setText("st-alt", formatNum(st.alt_m, 1));
    setText("st-course", formatNum(st.course_deg, 1));
    setText("st-disk", bytesToMiB(st.disk_free_bytes));
    const src = st.timestamp_source === "gps" ? "GPS" : "System";
    setText("st-updated", `GPS時刻: ${st.timestamp_utc || "-"} (${src})`);
    setText("st-system-time", `システム時刻: ${st.system_timestamp_utc || "-"} / Local: ${formatIsoToLocal(st.system_timestamp_utc)}`);
  } catch (_e) {
    setText("st-updated", "GPS時刻: 取得失敗");
    setText("st-system-time", "システム時刻: 取得失敗");
  }
}

async function loadSettings() {
  try {
    const r = await fetch("/api/settings", { cache: "no-store" });
    if (!r.ok) throw new Error("settings read failed");
    const s = await r.json();
    document.getElementById("set-interval").value = s.log_interval_sec;
    document.getElementById("set-min-speed").value = s.min_speed_write_mps;
    document.getElementById("set-max-hdop").value = s.max_hdop_for_log;
    document.getElementById("set-disk-th").value = s.disk_free_threshold_mb;
    document.getElementById("set-disk-target").value = s.disk_free_target_mb;
  } catch (_e) {
    setMessage("settings-msg", "設定の取得に失敗しました", true);
  }
}

async function saveSettings(ev) {
  ev.preventDefault();
  setMessage("settings-msg", "保存中...");

  const payload = {
    log_interval_sec: Number(document.getElementById("set-interval").value),
    min_speed_write_mps: Number(document.getElementById("set-min-speed").value),
    max_hdop_for_log: Number(document.getElementById("set-max-hdop").value),
    disk_free_threshold_mb: Number(document.getElementById("set-disk-th").value),
    disk_free_target_mb: Number(document.getElementById("set-disk-target").value),
  };

  try {
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await r.json();
    if (!r.ok) {
      setMessage("settings-msg", body.error || "保存に失敗しました", true);
      return;
    }
    setMessage("settings-msg", "設定を保存しました");
  } catch (_e) {
    setMessage("settings-msg", "保存に失敗しました", true);
  }
}

function localToIso(localValue) {
  const dt = new Date(localValue);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.toISOString();
}

function submitGpx(ev) {
  ev.preventDefault();
  const startLocal = document.getElementById("gpx-start").value;
  const endLocal = document.getElementById("gpx-end").value;
  const start = localToIso(startLocal);
  const end = localToIso(endLocal);

  if (!start || !end) {
    setMessage("gpx-msg", "日時を正しく入力してください", true);
    return;
  }
  if (new Date(start) >= new Date(end)) {
    setMessage("gpx-msg", "終了時刻は開始時刻より後にしてください", true);
    return;
  }

  const url = `/api/export.gpx?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
  setMessage("gpx-msg", "ダウンロードを開始します");
  window.location.href = url;
}

async function updateGpxCount() {
  const startLocal = document.getElementById("gpx-start")?.value;
  const endLocal = document.getElementById("gpx-end")?.value;
  const start = localToIso(startLocal || "");
  const end = localToIso(endLocal || "");
  if (!start || !end || new Date(start) >= new Date(end)) {
    setText("gpx-count", "取得点数: -");
    return;
  }
  try {
    const r = await fetch(`/api/export_count?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`, { cache: "no-store" });
    const body = await r.json();
    if (!r.ok) {
      setText("gpx-count", "取得点数: -");
      return;
    }
    setText("gpx-count", `取得点数: ${body.count} 点`);
  } catch (_e) {
    setText("gpx-count", "取得点数: -");
  }
}

function initDefaultRange() {
  const end = new Date();
  const start = new Date(end.getTime() - 60 * 60 * 1000);
  const toLocalInput = (d) => {
    const z = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`;
  };
  document.getElementById("gpx-start").value = toLocalInput(start);
  document.getElementById("gpx-end").value = toLocalInput(end);
}

async function loadGpsDevices() {
  const sel = document.getElementById("gps-device-list");
  if (!sel) return;
  try {
    const r = await fetch("/api/gps/devices", { cache: "no-store" });
    if (!r.ok) throw new Error("scan failed");
    const body = await r.json();
    const devices = body.devices || [];
    const current = body.current_device || "";
    sel.innerHTML = "";

    if (devices.length === 0) {
      const o = document.createElement("option");
      o.value = current || "";
      o.textContent = current || "検出デバイスなし";
      sel.appendChild(o);
    } else {
      devices.forEach((d) => {
        const o = document.createElement("option");
        o.value = d;
        o.textContent = d;
        if (d === current) o.selected = true;
        sel.appendChild(o);
      });
      if (current && !devices.includes(current)) {
        const o = document.createElement("option");
        o.value = current;
        o.textContent = `${current} (現在設定)`;
        o.selected = true;
        sel.appendChild(o);
      }
    }
    setMessage("gps-device-msg", `現在: ${current || "未設定"}`);
  } catch (_e) {
    setMessage("gps-device-msg", "デバイス一覧の取得に失敗しました", true);
  }
}

async function saveGpsDevice(ev) {
  ev.preventDefault();
  const sel = document.getElementById("gps-device-list");
  const device = sel?.value || "";
  if (!device.startsWith("/dev/")) {
    setMessage("gps-device-msg", "有効な /dev パスを選択してください", true);
    return;
  }
  setMessage("gps-device-msg", "適用中...");
  try {
    const r = await fetch("/api/gps/devices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device }),
    });
    const body = await r.json();
    if (!r.ok || !body.ok) {
      const msg = body.error || (body.warnings || []).join("\n") || "適用失敗";
      setMessage("gps-device-msg", msg, true);
      return;
    }
    const warns = body.warnings || [];
    setMessage("gps-device-msg", warns.length ? `適用済み (警告あり: ${warns.join(" / ")})` : "デバイスを適用しました");
    await loadStatus();
  } catch (_e) {
    setMessage("gps-device-msg", "適用に失敗しました", true);
  }
}

async function loadErrorLogs() {
  const box = document.getElementById("error-log");
  if (!box) return;
  box.textContent = "読み込み中...";
  try {
    const r = await fetch("/api/logs/errors?lines=200", { cache: "no-store" });
    const body = await r.json();
    if (!r.ok) {
      box.textContent = body.error || "ログ取得に失敗しました";
      return;
    }
    box.textContent = body.log || "warning 以上のログはありません。";
  } catch (_e) {
    box.textContent = "ログ取得に失敗しました";
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("refresh-status").addEventListener("click", loadStatus);
  document.getElementById("settings-form").addEventListener("submit", saveSettings);
  document.getElementById("gpx-form").addEventListener("submit", submitGpx);
  document.getElementById("gpx-start").addEventListener("change", updateGpxCount);
  document.getElementById("gpx-end").addEventListener("change", updateGpxCount);
  document.getElementById("scan-gps-device").addEventListener("click", loadGpsDevices);
  document.getElementById("gps-device-form").addEventListener("submit", saveGpsDevice);
  document.getElementById("refresh-errors").addEventListener("click", loadErrorLogs);

  initDefaultRange();
  await Promise.all([loadStatus(), loadSettings(), loadGpsDevices(), loadErrorLogs(), updateGpxCount()]);
  setInterval(loadStatus, 10000);
});
