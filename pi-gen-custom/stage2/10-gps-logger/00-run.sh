#!/bin/bash -e

install -d "${ROOTFS_DIR}/opt/gps-logger"
install -d "${ROOTFS_DIR}/opt/gps-logger/templates"
install -d "${ROOTFS_DIR}/opt/gps-logger/static"
install -d "${ROOTFS_DIR}/etc/gps-logger"
install -d "${ROOTFS_DIR}/etc/systemd/system"
install -d "${ROOTFS_DIR}/etc/hostapd"
install -d "${ROOTFS_DIR}/etc/dnsmasq.d"
install -d "${ROOTFS_DIR}/etc/NetworkManager/conf.d"
install -d "${ROOTFS_DIR}/etc/default"
install -d "${ROOTFS_DIR}/var/lib/gps-logger"
install -d "${ROOTFS_DIR}/run/gps-logger"
install -d "${ROOTFS_DIR}/boot/firmware"

install -m 0644 files/etc/gps-logger/config.json "${ROOTFS_DIR}/etc/gps-logger/config.json"
install -m 0755 files/opt/gps-logger/db.py "${ROOTFS_DIR}/opt/gps-logger/db.py"
install -m 0755 files/opt/gps-logger/gps_logger.py "${ROOTFS_DIR}/opt/gps-logger/gps_logger.py"
install -m 0755 files/opt/gps-logger/gps_time_sync.py "${ROOTFS_DIR}/opt/gps-logger/gps_time_sync.py"
install -m 0755 files/opt/gps-logger/rotate_logs.py "${ROOTFS_DIR}/opt/gps-logger/rotate_logs.py"
install -m 0755 files/opt/gps-logger/webapp.py "${ROOTFS_DIR}/opt/gps-logger/webapp.py"
install -m 0644 files/opt/gps-logger/templates/index.html "${ROOTFS_DIR}/opt/gps-logger/templates/index.html"
install -m 0644 files/opt/gps-logger/static/styles.css "${ROOTFS_DIR}/opt/gps-logger/static/styles.css"
install -m 0644 files/opt/gps-logger/static/app.js "${ROOTFS_DIR}/opt/gps-logger/static/app.js"

install -m 0644 files/etc/systemd/system/gps-logger.service "${ROOTFS_DIR}/etc/systemd/system/gps-logger.service"
install -m 0644 files/etc/systemd/system/gps-web.service "${ROOTFS_DIR}/etc/systemd/system/gps-web.service"
install -m 0644 files/etc/systemd/system/gps-time-sync.service "${ROOTFS_DIR}/etc/systemd/system/gps-time-sync.service"
install -m 0644 files/etc/systemd/system/gps-ap-net.service "${ROOTFS_DIR}/etc/systemd/system/gps-ap-net.service"
install -m 0644 files/etc/systemd/system/gps-rotate.service "${ROOTFS_DIR}/etc/systemd/system/gps-rotate.service"
install -m 0644 files/etc/systemd/system/gps-rotate.timer "${ROOTFS_DIR}/etc/systemd/system/gps-rotate.timer"

install -m 0644 files/etc/hostapd/hostapd.conf "${ROOTFS_DIR}/etc/hostapd/hostapd.conf"
install -m 0644 files/etc/default/hostapd "${ROOTFS_DIR}/etc/default/hostapd"
install -m 0644 files/etc/dnsmasq.d/gps-logger.conf "${ROOTFS_DIR}/etc/dnsmasq.d/gps-logger.conf"
install -m 0644 files/etc/NetworkManager/conf.d/90-gps-logger-unmanaged.conf "${ROOTFS_DIR}/etc/NetworkManager/conf.d/90-gps-logger-unmanaged.conf"
install -m 0644 files/etc/default/gpsd "${ROOTFS_DIR}/etc/default/gpsd"

AP_SUFFIX="$(tr -dc 'A-Z0-9' < /dev/urandom | head -c 4)"
AP_SSID="GPS-LOGGER-${AP_SUFFIX}"
AP_PASS="$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)"
BUILD_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CREDS_FILE="${ROOTFS_DIR}/tmp/gps-logger-ap-credentials.txt"

sed -i "s/^ssid=.*/ssid=${AP_SSID}/" "${ROOTFS_DIR}/etc/hostapd/hostapd.conf"
sed -i "s/^wpa_passphrase=.*/wpa_passphrase=${AP_PASS}/" "${ROOTFS_DIR}/etc/hostapd/hostapd.conf"
sed -i "s/\"ap_ssid\": \".*\"/\"ap_ssid\": \"${AP_SSID}\"/" "${ROOTFS_DIR}/etc/gps-logger/config.json"
sed -i "s/\"ap_passphrase\": \".*\"/\"ap_passphrase\": \"${AP_PASS}\"/" "${ROOTFS_DIR}/etc/gps-logger/config.json"

cat > "${CREDS_FILE}" <<EOF
build_utc=${BUILD_TS}
ssid=${AP_SSID}
password=${AP_PASS}
EOF

install -m 0600 "${CREDS_FILE}" "${ROOTFS_DIR}/etc/gps-logger/ap-credentials.txt"
install -m 0644 "${CREDS_FILE}" "${ROOTFS_DIR}/boot/firmware/gps-logger-ap.txt"

if [ -n "${DEPLOY_DIR:-}" ]; then
  mkdir -p "${DEPLOY_DIR}"
  cp "${CREDS_FILE}" "${DEPLOY_DIR}/${IMG_FILENAME:-gps-logger}-ap-credentials.txt"
  chmod 0600 "${DEPLOY_DIR}/${IMG_FILENAME:-gps-logger}-ap-credentials.txt"
fi

rm -f "${CREDS_FILE}"

if ! grep -q "^interface wlan0$" "${ROOTFS_DIR}/etc/dhcpcd.conf"; then
  cat <<'DHCPCD_EOF' >> "${ROOTFS_DIR}/etc/dhcpcd.conf"

interface wlan0
static ip_address=192.168.4.1/24
nohook wpa_supplicant
DHCPCD_EOF
fi

on_chroot <<'CHROOT_EOF'
set -e
systemctl unmask hostapd || true
systemctl enable gps-ap-net.service
systemctl enable hostapd
systemctl enable dnsmasq
systemctl enable gpsd
systemctl enable gps-time-sync.service
systemctl enable gps-logger.service
systemctl enable gps-web.service
systemctl enable gps-rotate.timer

# Boot acceleration: disable long wait/update paths not required for logger operation.
systemctl disable NetworkManager-wait-online.service 2>/dev/null || true
systemctl disable systemd-networkd-wait-online.service 2>/dev/null || true
systemctl disable apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
systemctl disable cloud-init.service cloud-config.service cloud-final.service cloud-init-local.service 2>/dev/null || true
CHROOT_EOF
