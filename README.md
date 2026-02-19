# RasPiGPS (pi-gen custom stage)

Raspberry Pi Zero W 向け GPS ロガーを構築するための `pi-gen` カスタムステージです。ビルドしたイメージをRPiに書き込むと、GPSの記録を自動的に開始します。同時にWiFiアクセスポイントが立ち上がり、WebUIから情報の確認やGPXの取得が可能です。

## 機能

- USB GPS (`gpsd`) から NMEA を取得し SQLite に保存
- 保存項目: タイムスタンプ（GPS時刻優先）/ 緯度 / 経度 / 高度 / 速度 / 方位 / HDOP / 衛星数 / Fix
- SQLite: `WAL` + `synchronous=NORMAL`
- 停止時の書き込み抑制
- 空き容量不足時のローテーション削除（systemd timer）
- Wi-Fi AP (`hostapd` + `dnsmasq`) 構築
- Flask Web UI/API（設定変更、GPX出力、GPSデバイス選択、エラーログ表示）
- GPS時刻によるシステム時刻補正（`gps-time-sync.service`）

## 動作確認済みハードウェア

- GPS受信機: VK-162
  - 製品リンク: [Amazon商品ページ](https://www.amazon.co.jp/dp/B0DPLD99JF)
  - ASIN: `B0DPLD99JF`
  - 搭載チップ: `M8030`

## ビルド環境構築（公式 pi-gen を使用）

1. 公式 `pi-gen` を取得

```bash
git clone https://github.com/RPi-Distro/pi-gen.git
cd pi-gen
```

2. このリポジトリのカスタムステージをコピー

```bash
cp -a /path/to/RasPiGPS/pi-gen-custom/stage2/10-gps-logger ./stage2/
```

3. `pi-gen/config` を作成（例）

```bash
cat > config << 'CFG'
IMG_NAME='raspios-gps-logger'
RELEASE='trixie'
DEPLOY_COMPRESSION='zip'
ENABLE_SSH=1
ENABLE_CLOUD_INIT=0
STAGE_LIST='stage0 stage1 stage2'
LOCALE_DEFAULT='ja_JP.UTF-8'
KEYBOARD_KEYMAP='jp'
KEYBOARD_LAYOUT='Japanese'
TIMEZONE_DEFAULT='Asia/Tokyo'
TARGET_HOSTNAME='gps-logger'

# Example credentials (MUST CHANGE)
FIRST_USER_NAME='gpsadmin'
FIRST_USER_PASS='GpsAdmin!ChangeMe-2026'
DISABLE_FIRST_BOOT_USER_RENAME=1
WPA_COUNTRY='JP'
CFG
```

4. ビルド実行

```bash
./build-docker.sh
# 途中失敗時の再開:
# CONTINUE=1 CONTAINER_NAME=pigen_work ./build-docker.sh
```

## 認証情報の扱い

- `FIRST_USER_NAME` / `FIRST_USER_PASS` は例示値です。必ず変更してください。
- AP の SSID / パスワードはビルドごとにランダム生成されます。
- 生成結果ファイル:
  - ビルドホスト: `deploy/<IMG_FILENAME>-ap-credentials.txt`
  - イメージ内: `/boot/firmware/gps-logger-ap.txt`
  - イメージ内(管理用): `/etc/gps-logger/ap-credentials.txt`

## Web UI / API

- Web UI: `http://192.168.4.1:8080/`
- API:
  - `GET /api/status`
  - `GET/POST /api/settings`
  - `GET /api/export.gpx?start=...&end=...`
  - `GET/POST /api/gps/devices`
  - `GET /api/logs/errors?lines=200`

## 注意事項

- `BOOTSTRAP_NO_CHECK_GPG=1` のような暫定回避設定は、必要性を理解したうえで使用してください。
- 車載利用を想定し、位置情報は移動中のみ記録する設計です（書き込み中の電源断リスク低減のため）。
- この構成は Codex により作成されています。
- 本リポジトリは検証段階の成果物です。動作保証はなく、利用によって生じたいかなる損害についても制作者は責任を負いません。

## License

MIT
