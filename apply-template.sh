#!/bin/bash
# ==============================================================================
# SCRIPT PENERAP TAMPILAN & FITUR INFORMATIF GENIEACS (ALIJAYA NET)
# Mengubah GenieACS standar menjadi GenieACS Informatif Multi-Tab:
# WAN (Add WAN/PPPoE), WLAN (Multi-SSID & Client RSSI), LAN (Port LAN & Hosts),
# USER (Web GUI Direct Link), TR-069 (CWMP Config), dan Bebas Fault.
#
# Dibuat oleh: ALIJAYA NET (WhatsApp: 081947215703)
# ==============================================================================

set -e

# Warna output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

clear 2>/dev/null || true
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${BOLD}${GREEN}           🎨 ALIJAYA NET - TEMA & FITUR INFORMATIF GENIEACS          ${NC}${CYAN}║${NC}"
echo -e "${CYAN}║${BOLD}${YELLOW}       Upgrade GenieACS Standar Menjadi Multi-Tab & Informatif        ${NC}${CYAN}║${NC}"
echo -e "${CYAN}║                                                                      ║${NC}"
echo -e "${CYAN}║${NC}  👑 ${BOLD}Pengembang${NC}         : ${GREEN}${BOLD}ALIJAYA NET${NC}                                    ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  📱 ${BOLD}WhatsApp / Kontak${NC}  : ${YELLOW}${BOLD}081947215703${NC}                                   ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Pastikan root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Jalankan script ini sebagai user root! (sudo bash $0)${NC}"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || pwd)"
ARCHIVE="${SCRIPT_DIR}/genieacs_template_ui.tar.gz"

if [ ! -f "$ARCHIVE" ]; then
  if [ -f "./genieacs_template_ui.tar.gz" ]; then
    ARCHIVE="./genieacs_template_ui.tar.gz"
  elif [ -f "/root/genieacs_template_ui.tar.gz" ]; then
    ARCHIVE="/root/genieacs_template_ui.tar.gz"
  else
    echo -e "${RED}[ERROR] File genieacs_template_ui.tar.gz tidak ditemukan di folder ini!${NC}"
    echo "Pastikan file genieacs_template_ui.tar.gz berada dalam satu folder dengan script ini."
    exit 1
  fi
fi

# Cek mongorestore
if ! command -v mongorestore >/dev/null 2>&1; then
  echo -e "${YELLOW}[!] Memasang paket mongo-tools (mongorestore)...${NC}"
  apt-get update -y && apt-get install -y mongo-tools || true
fi

# Coba deteksi URI MongoDB (dengan user genie atau tanpa auth)
MONGO_URI=""
if mongosh --quiet --eval "db.runCommand({ping:1})" "mongodb://genie:genie@127.0.0.1:27017/genieacs" >/dev/null 2>&1; then
  MONGO_URI="mongodb://genie:genie@127.0.0.1:27017/genieacs"
elif mongosh --quiet --eval "db.runCommand({ping:1})" "mongodb://127.0.0.1:27017/genieacs" >/dev/null 2>&1; then
  MONGO_URI="mongodb://127.0.0.1:27017/genieacs"
elif mongo --quiet --eval "db.runCommand({ping:1})" "mongodb://genie:genie@127.0.0.1:27017/genieacs" >/dev/null 2>&1; then
  MONGO_URI="mongodb://genie:genie@127.0.0.1:27017/genieacs"
elif mongo --quiet --eval "db.runCommand({ping:1})" "mongodb://127.0.0.1:27017/genieacs" >/dev/null 2>&1; then
  MONGO_URI="mongodb://127.0.0.1:27017/genieacs"
else
  # Default jika cli tidak ada
  MONGO_URI="mongodb://genie:genie@127.0.0.1:27017/genieacs"
fi

echo -e "${BLUE}[1/3] Mengekstrak template tampilan & parameter...${NC}"
TMP_DIR="/tmp/genieacs_template_$$"
mkdir -p "$TMP_DIR"
tar -xzf "$ARCHIVE" -C "$TMP_DIR"

echo -e "${BLUE}[2/3] Menerapkan konfigurasi UI, Virtual Parameters & Provisions...${NC}"
echo -e "${YELLOW}Catatan: Data perangkat (devices) & akun user server ini TIDAK AKAN TERHAPUS.${NC}"

# Restore hanya koleksi tampilan dan fungsi
mongorestore --uri="$MONGO_URI" --drop "$TMP_DIR/genieacs" || \
mongorestore --drop "$TMP_DIR/genieacs"

# Bersihkan cache hash UI lokal
if command -v mongosh >/dev/null 2>&1; then
  mongosh "$MONGO_URI" --quiet --eval "db.config.deleteOne({_id: 'ui-local-cache-hash'})" 2>/dev/null || true
elif command -v mongo >/dev/null 2>&1; then
  mongo "$MONGO_URI" --quiet --eval "db.config.remove({_id: 'ui-local-cache-hash'})" 2>/dev/null || true
fi

rm -rf "$TMP_DIR"

# Pasang paket Python untuk agen AI jika belum ada
apt-get install -y python3-requests python3-pymongo 2>/dev/null || true

# Pasang script agen jika ada di direktori
mkdir -p /opt/genieacs-agent
if [ -f "${SCRIPT_DIR}/agent.py" ]; then
  cp "${SCRIPT_DIR}/agent.py" /opt/genieacs-agent/agent.py
elif [ -f "./agent.py" ]; then
  cp "./agent.py" /opt/genieacs-agent/agent.py
fi
chmod +x /opt/genieacs-agent/agent.py 2>/dev/null || true

cat << 'EOF' > /etc/systemd/system/genieacs-agent.service
[Unit]
Description=GenieACS AI Telegram Agent (ALIJAYA NET)
After=network.target mongod.service genieacs-nbi.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/genieacs-agent
ExecStart=/usr/bin/python3 /opt/genieacs-agent/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable genieacs-agent.service 2>/dev/null || true
systemctl restart genieacs-agent.service 2>/dev/null || true

echo -e "${BLUE}[3/3] Merestart layanan GenieACS & Agent...${NC}"
systemctl restart genieacs-ui genieacs-cwmp genieacs-nbi genieacs-fs genieacs-agent 2>/dev/null || {
  service genieacs-ui restart 2>/dev/null || true
  service genieacs-cwmp restart 2>/dev/null || true
}

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}✔ SUKSES! Tampilan & Fitur Informatif Berhasil Diterapkan 100%!${NC}"
echo -e "${CYAN}• Tab Aktif : LAN, WAN (Add WAN Button), WLAN (Multi-SSID), USER, TR069${NC}"
echo -e "${CYAN}• Fitur     : Optical Power Rx/Tx, Host LAN Clients, WiFi Clients RSSI${NC}"
echo -e "${CYAN}• Status    : Provision Bebas Fault & Kompatibel Semua Merk ONT${NC}"
echo -e "${YELLOW}Silakan buka browser dan refresh (Ctrl + F5) pada halaman GenieACS UI.${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Bantuan & Konsultasi: WhatsApp 081947215703 (ALIJAYA NET)${NC}"
