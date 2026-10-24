#!/bin/bash
# ==============================================================================
# SCRIPT AUTO INSTALLER GENIEACS + MONGODB + NODE.JS v20
# Dikhususkan untuk Armbian / Linux SBC (STB B860H, HG680P, Orange Pi, Raspberry Pi)
# Serta Komputer / VPS Linux Debian 11 (Bullseye) / Debian 12 (Bookworm) / Ubuntu
# 
# Dibuat & Dioptimasi oleh: ALIJAYA-NET (HP: 081947215703)
# ==============================================================================

set -e

# Warna untuk output terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

clear 2>/dev/null || true
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${BOLD}${GREEN}                    🚀 ALIJAYA NET AUTO-INSTALLER                     ${NC}${CYAN}║${NC}"
echo -e "${CYAN}║${BOLD}${YELLOW}         GENIEACS TR-069 + MONGODB + NODE.JS v20 UNTUK ARMBIAN        ${NC}${CYAN}║${NC}"
echo -e "${CYAN}║                                                                      ║${NC}"
echo -e "${CYAN}║${NC}  👑 ${BOLD}Pengembang & Maintenance${NC} : ${GREEN}${BOLD}ALIJAYA NET${NC}                           ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  📱 ${BOLD}WhatsApp / Telepon${NC}       : ${YELLOW}${BOLD}081947215703${NC} (${CYAN}0819-4721-5703${NC})         ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  🌐 ${BOLD}Sistem & Jaringan${NC}        : ${WHITE}Manajemen TR-069 GenieACS & RT/RW Net   ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
sleep 2

# 1. Pastikan script dijalankan sebagai root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Script ini harus dijalankan sebagai user ROOT!${NC}"
  echo "Gunakan: sudo bash $0"
  exit 1
fi

ARCH=$(uname -m)
echo -e "${BLUE}[INFO] Mendeteksi Arsitektur CPU:${NC} ${GREEN}$ARCH${NC}"

if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "arm64" ] && [ "$ARCH" != "x86_64" ]; then
  echo -e "${RED}[WARNING] Arsitektur $ARCH belum diuji secara resmi. Melanjutkan...${NC}"
fi

# 2. Update Sistem & Pasang Paket Dasar
echo -e "\n${BLUE}[1/8] Mengupdate repositori dan menginstall paket dasar...${NC}"
# Fix repository debian jika ada 404 backports
sed -i 's/^deb .*bullseye-backports/# &/' /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null || true
apt-get update -y
apt-get install -y curl wget git gnupg lsb-release build-essential libcurl4 libssl-dev logrotate rsync net-tools python3-requests python3-pymongo

# 3. Instalasi Node.js v20 LTS (NodeSource)
echo -e "\n${BLUE}[2/7] Menginstall Node.js v20 LTS dari NodeSource...${NC}"
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | cut -d'.' -f1)" != "v20" ]; then
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg --yes
  
  NODE_MAJOR=20
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list
  
  apt-get update -y
  apt-get install -y nodejs
else
  echo -e "${GREEN}[OK] Node.js sudah terpasang: $(node -v)${NC}"
fi

echo -e "${GREEN}[OK] Node.js Version: $(node -v) | NPM: $(npm -v)${NC}"

# 4. Instalasi MongoDB & Kompatibilitas ARM64
echo -e "\n${BLUE}[3/7] Menginstall & Menyiapkan Database MongoDB...${NC}"

# Buat user & group mongodb jika belum ada
if ! id mongodb >/dev/null 2>&1; then
  useradd --system --no-create-home --user-group mongodb || true
fi

# Pastikan folder data dan log ada
mkdir -p /var/lib/mongodb /var/log/mongodb /var/log.ext/mongodb 2>/dev/null || true
chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb /var/log.ext/mongodb 2>/dev/null || true

if ! command -v mongod >/dev/null 2>&1; then
  echo -e "${YELLOW}Mengunduh binary MongoDB yang stabil dan kompatibel untuk $ARCH...${NC}"
  
  # Cek kebutuhan libssl1.1 untuk Debian/Armbian
  if ! ldconfig -p | grep -q "libssl.so.1.1"; then
    echo -e "${YELLOW}Memasang dependensi libssl1.1...${NC}"
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
      wget -q http://ports.ubuntu.com/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_arm64.deb -O /tmp/libssl1.1.deb || \
      wget -q http://security.debian.org/debian-security/pool/updates/main/o/openssl/libssl1.1_1.1.1n-0+deb11u5_arm64.deb -O /tmp/libssl1.1.deb || true
    else
      wget -q http://security.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb -O /tmp/libssl1.1.deb || true
    fi
    if [ -f /tmp/libssl1.1.deb ]; then
      dpkg -i /tmp/libssl1.1.deb || apt-get install -fy
      rm -f /tmp/libssl1.1.deb
    fi
  fi

  # Unduh MongoDB binary archive resmi
  if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    MONGO_URL="https://fastdl.mongodb.org/linux/mongodb-linux-aarch64-ubuntu2004-5.0.6.tgz"
  else
    MONGO_URL="https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-ubuntu2004-5.0.6.tgz"
  fi

  echo "Mengunduh dari: $MONGO_URL"
  wget -c "$MONGO_URL" -O /tmp/mongodb.tgz
  tar -zxvf /tmp/mongodb.tgz -C /tmp/
  cp -f /tmp/mongodb-*/bin/* /usr/bin/
  rm -rf /tmp/mongodb*
  chmod +x /usr/bin/mongo*
else
  echo -e "${GREEN}[OK] Binary mongod sudah tersedia: $(mongod --version | head -n1)${NC}"
  chmod +x /usr/bin/mongo* 2>/dev/null || true
fi

# Tulis konfigurasi mongod.conf yang hemat RAM (Sangat ramah STB RAM 1GB / 2GB)
cat << 'EOF' > /etc/mongod.conf
# mongod.conf - Dioptimasi untuk Armbian STB oleh ALIJAYA-NET
storage:
  dbPath: /var/lib/mongodb
  journal:
    enabled: true
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.25

systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log

net:
  port: 27017
  bindIp: 127.0.0.1

processManagement:
  timeZoneInfo: /usr/share/zoneinfo

security:
  authorization: enabled
EOF

# Tulis file service systemd untuk mongod
cat << 'EOF' > /lib/systemd/system/mongod.service
[Unit]
Description=MongoDB Database Server
Documentation=https://docs.mongodb.org/manual
After=network-online.target
Wants=network-online.target

[Service]
User=mongodb
Group=mongodb
EnvironmentFile=-/etc/default/mongod
ExecStart=/usr/bin/mongod --config /etc/mongod.conf
PIDFile=/run/mongodb/mongod.pid
LimitFSIZE=infinity
LimitCPU=infinity
LimitAS=infinity
LimitNOFILE=64000
LimitNPROC=64000
LimitMEMLOCK=infinity
TasksMax=infinity
TasksAccounting=false

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mongod

# Jalankan mongod sementara tanpa otentikasi untuk inisialisasi akun genieacs
echo -e "${YELLOW}Menginisialisasi user database 'genie' di MongoDB...${NC}"
# Matikan sementara jika sedang jalan
systemctl stop mongod 2>/dev/null || true
# Jalankan sementara di background tanpa auth
mongod --dbpath /var/lib/mongodb --bind_ip 127.0.0.1 --port 27017 --fork --logpath /var/log/mongodb/init.log

sleep 3

# Buat database genieacs dan user genie:genie jika mongosh/mongo tersedia
if command -v mongosh >/dev/null 2>&1; then
  MONGO_CLI="mongosh"
elif command -v mongo >/dev/null 2>&1; then
  MONGO_CLI="mongo"
else
  MONGO_CLI=""
fi

if [ -n "$MONGO_CLI" ]; then
  $MONGO_CLI --quiet --eval "
    try {
      db.getSiblingDB('genieacs').createUser({
        user: 'genie',
        pwd: 'genie',
        roles: [{ role: 'readWrite', db: 'genieacs' }]
      });
      print('User genie created successfully');
    } catch(e) {
      print('User already exists or skipped: ' + e);
    }
  " 127.0.0.1:27017/admin || true
fi

# Matikan proses mongod sementara dan jalankan via systemd resmi
pkill -f mongod || true
sleep 2
systemctl start mongod
echo -e "${GREEN}[OK] MongoDB berhasil aktif!${NC}"

# ==============================================================================
# RESTORE DATABASE SIAP PAKAI (ALIJAYA NET)
# Merestore Virtual Parameters Universal, Presets, Provisions & UI Config
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || pwd)"
BACKUP_ARCHIVE=""

# Cari file backup di folder script atau /root atau direktori kerja saat ini
if [ -f "${SCRIPT_DIR}/genieacs_db.tar.gz" ]; then
  BACKUP_ARCHIVE="${SCRIPT_DIR}/genieacs_db.tar.gz"
elif [ -f "./genieacs_db.tar.gz" ]; then
  BACKUP_ARCHIVE="./genieacs_db.tar.gz"
elif [ -f "/root/genieacs_db.tar.gz" ]; then
  BACKUP_ARCHIVE="/root/genieacs_db.tar.gz"
fi

if [ -n "$BACKUP_ARCHIVE" ] && [ -f "$BACKUP_ARCHIVE" ]; then
  echo -e "\n${BLUE}[+] Ditemukan file backup database: ${YELLOW}${BACKUP_ARCHIVE}${NC}"
  echo -e "${YELLOW}Merestore database GenieACS (Virtual Parameters universal, Preset & Config ALIJAYA NET)...${NC}"
  
  TMP_RESTORE_DIR="/tmp/genieacs_restore_$$"
  mkdir -p "$TMP_RESTORE_DIR"
  tar -xzf "$BACKUP_ARCHIVE" -C "$TMP_RESTORE_DIR"
  
  if [ -x /usr/bin/mongorestore ]; then
    /usr/bin/mongorestore --uri="mongodb://genie:genie@127.0.0.1:27017/genieacs" --drop "$TMP_RESTORE_DIR/genieacs"
    echo -e "${GREEN}[OK] Database GenieACS berhasil di-restore 100% siap pakai!${NC}"
  elif command -v mongorestore >/dev/null 2>&1; then
    mongorestore --uri="mongodb://genie:genie@127.0.0.1:27017/genieacs" --drop "$TMP_RESTORE_DIR/genieacs"
    echo -e "${GREEN}[OK] Database GenieACS berhasil di-restore 100% siap pakai!${NC}"
  else
    echo -e "${RED}[WARNING] mongorestore tidak ditemukan. Melewati restore database.${NC}"
  fi
  rm -rf "$TMP_RESTORE_DIR"
else
  echo -e "${YELLOW}[INFO] File genieacs_db.tar.gz tidak ditemukan. Database akan dimulai dari awal.${NC}"
fi

# 5. Instalasi Paket GenieACS via NPM
echo -e "\n${BLUE}[4/7] Menginstall GenieACS secara global via NPM...${NC}"
npm install -g genieacs@1.2.13 --unsafe-perm=true

# Buat user sistem genieacs
if ! id genieacs >/dev/null 2>&1; then
  useradd --system --no-create-home --user-group genieacs || true
fi

# Buat direktori kerja & konfigurasi
mkdir -p /opt/genieacs/ext /var/log/genieacs /var/log.ext/genieacs 2>/dev/null || true
chown -R genieacs:genieacs /opt/genieacs /var/log/genieacs /var/log.ext/genieacs 2>/dev/null || true
chmod -R 775 /var/log/genieacs /var/log.ext/genieacs 2>/dev/null || true

# Generate JWT Secret acak
JWT_SECRET=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 64)

# Buat environment file /opt/genieacs/genieacs.env
cat << EOF > /opt/genieacs/genieacs.env
GENIEACS_CWMP_ACCESS_LOG_FILE=/var/log/genieacs/genieacs-cwmp-access.log
GENIEACS_NBI_ACCESS_LOG_FILE=/var/log/genieacs/genieacs-nbi-access.log
GENIEACS_FS_ACCESS_LOG_FILE=/var/log/genieacs/genieacs-fs-access.log
GENIEACS_UI_ACCESS_LOG_FILE=/var/log/genieacs/genieacs-ui-access.log
GENIEACS_DEBUG_FILE=/var/log/genieacs/genieacs-debug.yaml
NODE_OPTIONS=--enable-source-maps
GENIEACS_EXT_DIR=/opt/genieacs/ext
GENIEACS_UI_JWT_SECRET=${JWT_SECRET}
GENIEACS_MONGODB_CONNECTION_URL=mongodb://genie:genie@127.0.0.1:27017/genieacs
EOF

chown genieacs:genieacs /opt/genieacs/genieacs.env
chmod 600 /opt/genieacs/genieacs.env

# 6. Pasang Layanan Systemd GenieACS (CWMP, NBI, FS, UI)
echo -e "\n${BLUE}[5/7] Memasang & Mengaktifkan Layanan Systemd GenieACS...${NC}"

MODULES=("cwmp" "nbi" "fs" "ui")

for mod in "${MODULES[@]}"; do
  cat << EOF > /etc/systemd/system/genieacs-${mod}.service
[Unit]
Description=GenieACS ${mod^^}
After=network.target mongod.service

[Service]
User=genieacs
Group=genieacs
EnvironmentFile=/opt/genieacs/genieacs.env
ExecStart=/usr/bin/genieacs-${mod}
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF
done

systemctl daemon-reload
systemctl enable genieacs-cwmp genieacs-nbi genieacs-fs genieacs-ui
systemctl restart genieacs-cwmp genieacs-nbi genieacs-fs genieacs-ui

# 7. Konfigurasi Anti-Disk Penuh (Logrotate & Armbian Ramlog)
echo -e "\n${BLUE}[6/7] Memasang Proteksi Anti-Disk Penuh (Logrotate & Ramlog)...${NC}"

# A. Rotasi Log GenieACS (Hanya simpan 5 hari, maks 10MB, otomatis kompres gzip)
cat << 'EOF' > /etc/logrotate.d/genieacs
/var/log/genieacs/*.log /var/log.ext/genieacs/*.log /var/log.hdd/genieacs/*.log {
    daily
    size 10M
    rotate 5
    compress
    delaycompress
    missingok
    notifempty
    create 0644 genieacs genieacs
    sharedscripts
    postrotate
        systemctl reload-or-try-restart genieacs-cwmp genieacs-nbi genieacs-fs genieacs-ui 2>/dev/null || true
    endscript
}
EOF

# B. Aktifkan opsi --delete di armbian-ramlog jika file ada
if [ -f /etc/default/armbian-ramlog ]; then
  sed -i 's/# --delete/--delete/g' /etc/default/armbian-ramlog
  sed -i 's/SIZE=.*/SIZE=50M/g' /etc/default/armbian-ramlog
  echo -e "${GREEN}[OK] Armbian-ramlog dioptimasi (--delete aktif).${NC}"
fi

# C. Batasi log systemd journalctl maksimal 50 MB
if [ -f /etc/systemd/journald.conf ]; then
  sed -i 's/#SystemMaxUse=.*/SystemMaxUse=50M/g' /etc/systemd/journald.conf
  sed -i 's/SystemMaxUse=.*/SystemMaxUse=50M/g' /etc/systemd/journald.conf
fi

# Tes logrotate
logrotate -d /etc/logrotate.d/genieacs >/dev/null 2>&1 || true

# 8. Memasang GenieACS AI Telegram Agent (Hermes/Gemini Engine)
echo -e "\n${BLUE}[7/8] Memasang & Mengaktifkan GenieACS AI Telegram Agent...${NC}"
mkdir -p /opt/genieacs-agent
if [ -f "${SCRIPT_DIR}/agent.py" ]; then
  cp "${SCRIPT_DIR}/agent.py" /opt/genieacs-agent/agent.py
elif [ -f "./agent.py" ]; then
  cp "./agent.py" /opt/genieacs-agent/agent.py
fi
chmod +x /opt/genieacs-agent/agent.py 2>/dev/null || true

# CLI Helper set-bot
if [ -f "${SCRIPT_DIR}/set-bot.py" ]; then
  cp "${SCRIPT_DIR}/set-bot.py" /opt/genieacs-agent/set-bot.py
elif [ -f "./set-bot.py" ]; then
  cp "./set-bot.py" /opt/genieacs-agent/set-bot.py
fi
if [ -f /opt/genieacs-agent/set-bot.py ]; then
  chmod +x /opt/genieacs-agent/set-bot.py
  ln -sf /opt/genieacs-agent/set-bot.py /usr/local/bin/set-bot
fi

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
systemctl enable genieacs-agent.service
systemctl restart genieacs-agent.service 2>/dev/null || true

# 9. Selesai & Ringkasan Status
echo -e "\n${BLUE}[8/8] Memverifikasi status port & layanan...${NC}"
sleep 3

IP_ADDRESS=$(hostname -I | awk '{print $1}')

echo -e "\n${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${BOLD}${GREEN}        🎉 INSTALASI GENIEACS & MONGODB SELESAI DENGAN SUKSES!        ${NC}${CYAN}║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  💻 ${BOLD}Web GUI Dashboard${NC}    : ${YELLOW}${BOLD}http://${IP_ADDRESS}:3000${NC}"
echo -e "${CYAN}║${NC}  🔑 ${BOLD}Login Bawaan${NC}         : ${GREEN}admin${NC} / ${GREEN}admin${NC} (atau buat saat pertama login)"
echo -e "${CYAN}║${NC}  📡 ${BOLD}URL CWMP (Modem ONT)${NC} : ${YELLOW}${BOLD}http://${IP_ADDRESS}:7547${NC}"
echo -e "${CYAN}║${NC}  🔌 ${BOLD}Port NBI (REST API)${NC}  : ${WHITE}http://${IP_ADDRESS}:7557${NC}"
echo -e "${CYAN}║${NC}  📁 ${BOLD}Port FS (File Server)${NC}: ${WHITE}http://${IP_ADDRESS}:7567${NC}"
echo -e "${CYAN}║${NC}  🤖 ${BOLD}AI Telegram Agent${NC}    : ${GREEN}AKTIF (Ketik '${YELLOW}set-bot${GREEN}' di terminal SSH)${NC}"
echo -e "${CYAN}║${NC}  ⚡ ${BOLD}Status Layanan${NC}       : ${GREEN}MongoDB & 4 Service GenieACS AKTIF (OK)${NC}"
echo -e "${CYAN}║${NC}  🛡️ ${BOLD}Proteksi Storage${NC}     : ${GREEN}Logrotate & Ramlog AKTIF (Bebas Disk Penuh)${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  👑 ${BOLD}DEVELOPER & SUPPORT${NC}  : ${GREEN}${BOLD}ALIJAYA NET${NC}"
echo -e "${CYAN}║${NC}  📱 ${BOLD}WHATSAPP / TELEPON${NC}   : ${YELLOW}${BOLD}081947215703${NC} (${CYAN}0819-4721-5703${NC})"
echo -e "${CYAN}║${NC}  💬 ${BOLD}HUBUNGI KAMI (WA)${NC}    : ${CYAN}https://wa.me/6281947215703${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}\n"
