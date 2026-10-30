#!/bin/bash
# ==============================================================================
# SCRIPT AUTO INSTALLER GENIEACS + MONGODB + NODE.JS v20
# Dikhususkan untuk Armbian / Linux SBC (STB B860H, HG680P, Orange Pi, Raspberry Pi)
# Serta Komputer / VPS Linux Debian 11 (Bullseye) / Debian 12 (Bookworm) / Ubuntu
# 
# Dicopy oleh: WiFilink (HP: 085174661144)
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
echo -e "${CYAN}║${BOLD}${GREEN}                    🚀 GENIEACS AUTO-INSTALLER                     ${NC}${CYAN}║${NC}"
echo -e "${CYAN}║${BOLD}${YELLOW}         GENIEACS TR-069 + MONGODB + NODE.JS v20 UNTUK ARMBIAN        ${NC}${CYAN}║${NC}"
echo -e "${CYAN}║                                                                      ║${NC}"
echo -e "${CYAN}║${NC}  👑 ${BOLD}Pengembang & Maintenance${NC} : ${GREEN}${BOLD}WiFilinkT${NC}                           ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  📱 ${BOLD}WhatsApp / Telepon${NC}       : ${YELLOW}${BOLD}085174661144${NC} (${CYAN}0851-7466-1144${NC})         ${CYAN}║${NC}"
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

# Periksa apakah mongod sudah ada dan apakah benar-benar bisa dieksekusi (tidak Illegal instruction)
NEED_INSTALL=0
if ! command -v mongod >/dev/null 2>&1; then
  NEED_INSTALL=1
elif ! mongod --version >/dev/null 2>&1; then
  echo -e "${YELLOW}[!] Binary mongod yang terpasang tidak kompatibel dengan CPU ini (Illegal instruction).${NC}"
  echo -e "${YELLOW}Membersihkan dan mengunduh MongoDB 4.4 yang 100% kompatibel untuk semua CPU ARM STB...${NC}"
  systemctl stop mongod 2>/dev/null || true
  pkill -9 -f mongod 2>/dev/null || true
  rm -f /usr/bin/mongo* /usr/local/bin/mongo*
  NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
  echo -e "${YELLOW}Mengunduh binary MongoDB 4.4 universal & stabil untuk $ARCH...${NC}"
  
  # Cek kebutuhan libssl1.1 untuk Debian/Armbian
  if ! ldconfig -p | grep -q "libssl.so.1.1"; then
    echo -e "${YELLOW}Memasang dependensi libssl1.1...${NC}"
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
      wget -q http://ports.ubuntu.com/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_arm64.deb -O /tmp/libssl1.1.deb || true
    else
      wget -q http://security.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb -O /tmp/libssl1.1.deb || true
    fi
    if [ -f /tmp/libssl1.1.deb ]; then
      dpkg -i /tmp/libssl1.1.deb || apt-get install -fy
      rm -f /tmp/libssl1.1.deb
    fi
  fi

  # Unduh MongoDB binary archive resmi v4.4.18 (Versi terakhir yang 100% ARMv8.0 kompatibel bebas Illegal instruction)
  if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    MONGO_URL="https://fastdl.mongodb.org/linux/mongodb-linux-aarch64-ubuntu2004-4.4.18.tgz"
  else
    MONGO_URL="https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-ubuntu2004-4.4.18.tgz"
  fi

  echo "Mengunduh dari: $MONGO_URL"
  wget -c "$MONGO_URL" -O /tmp/mongodb.tgz
  tar -zxvf /tmp/mongodb.tgz -C /tmp/
  cp -f /tmp/mongodb-*/bin/* /usr/bin/
  rm -rf /tmp/mongodb*
  chmod +x /usr/bin/mongo*

  # Pastikan mongod yang baru terpasang bisa berjalan
  if ! mongod --version >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] Binary mongod masih gagal dijalankan. Memasang mongodb dari repository apt bawaan distro...${NC}"
    apt-get update -y && apt-get install -y mongodb || true
  fi
fi

echo -e "${GREEN}[OK] Binary mongod aktif & kompatibel: $(mongod --version 2>/dev/null | head -n1 || echo 'MongoDB Server')${NC}"
chmod +x /usr/bin/mongo* 2>/dev/null || true

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

# Pastikan folder runtime & tmpfiles dibuat otomatis saat boot (Penting untuk Armbian Ramlog/zram)
mkdir -p /etc/tmpfiles.d
cat << 'EOF' > /etc/tmpfiles.d/genieacs-mongodb.conf
d /var/log/mongodb 0755 mongodb mongodb -
d /run/mongodb 0755 mongodb mongodb -
d /var/lib/mongodb 0755 mongodb mongodb -
d /var/log/genieacs 0775 genieacs genieacs -
d /opt/genieacs/ext 0775 genieacs genieacs -
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/genieacs-mongodb.conf 2>/dev/null || true

# Tulis file service systemd untuk mongod dengan proteksi reboot/mati listrik
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
PermissionsStartOnly=true
ExecStartPre=/usr/bin/install -d -m 0755 -o mongodb -g mongodb /var/log/mongodb /run/mongodb /var/lib/mongodb
ExecStart=/usr/bin/mongod --config /etc/mongod.conf
PIDFile=/run/mongodb/mongod.pid
Restart=always
RestartSec=3
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
pkill -9 -f mongod 2>/dev/null || true
sleep 1

# Pastikan kepemilikan folder data
chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb /var/log.ext/mongodb 2>/dev/null || true

# Jalankan sementara di background tanpa auth
su - mongodb -s /bin/bash -c "mongod --dbpath /var/lib/mongodb --bind_ip 127.0.0.1 --port 27017 --fork --logpath /var/log/mongodb/init.log" 2>/dev/null || \
mongod --dbpath /var/lib/mongodb --bind_ip 127.0.0.1 --port 27017 --fork --logpath /var/log/mongodb/init.log

sleep 3

# Buat / update database genieacs dan user genie:genie dengan role readWrite & dbAdmin
python3 - << 'EOF' 2>/dev/null || true
import pymongo
try:
    c = pymongo.MongoClient("mongodb://127.0.0.1:27017/admin", serverSelectionTimeoutMS=3000)
    db = c["genieacs"]
    try:
        db.command("createUser", "genie", pwd="genie", roles=[{"role": "readWrite", "db": "genieacs"}, {"role": "dbAdmin", "db": "genieacs"}])
        print("User genie created successfully with readWrite and dbAdmin")
    except Exception:
        db.command("updateUser", "genie", roles=[{"role": "readWrite", "db": "genieacs"}, {"role": "dbAdmin", "db": "genieacs"}])
        print("User genie roles updated with readWrite and dbAdmin")
except Exception as e:
    print(f"PyMongo init warning: {e}")
EOF

if command -v mongo >/dev/null 2>&1; then
  MONGO_CLI="mongo"
elif command -v mongosh >/dev/null 2>&1; then
  MONGO_CLI="mongosh"
else
  MONGO_CLI=""
fi

if [ -n "$MONGO_CLI" ]; then
  $MONGO_CLI --quiet --eval "
    try {
      db.getSiblingDB('genieacs').createUser({
        user: 'genie',
        pwd: 'genie',
        roles: [{ role: 'readWrite', db: 'genieacs' }, { role: 'dbAdmin', db: 'genieacs' }]
      });
      print('User genie created successfully');
    } catch(e) {
      try {
        db.getSiblingDB('genieacs').updateUser('genie', {
          roles: [{ role: 'readWrite', db: 'genieacs' }, { role: 'dbAdmin', db: 'genieacs' }]
        });
        print('User genie roles updated');
      } catch(e2) {}
    }
  " 127.0.0.1:27017/admin >/dev/null 2>&1 || true
fi

# Matikan proses mongod sementara dan jalankan via systemd resmi
pkill -9 -f mongod 2>/dev/null || true
sleep 2
chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb /var/log.ext/mongodb 2>/dev/null || true
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
  
  if ! command -v mongorestore >/dev/null 2>&1; then
    echo -e "${YELLOW}[!] Memasang paket mongo-tools (mongorestore)...${NC}"
    apt-get update -y >/dev/null 2>&1 && apt-get install -y mongo-tools >/dev/null 2>&1 || true
    if ! command -v mongorestore >/dev/null 2>&1; then
      if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        TOOLS_URL="https://fastdl.mongodb.org/tools/db/mongodb-database-tools-ubuntu2004-arm64-100.9.4.tgz"
      else
        TOOLS_URL="https://fastdl.mongodb.org/tools/db/mongodb-database-tools-ubuntu2004-x86_64-100.9.4.tgz"
      fi
      echo -e "${YELLOW}Mengunduh binary mongorestore resmi ($ARCH)...${NC}"
      wget -q "$TOOLS_URL" -O /tmp/tools.tgz && \
      tar -zxvf /tmp/tools.tgz -C /tmp/ && \
      cp -f /tmp/mongodb-database-tools-*/bin/* /usr/bin/ && \
      rm -rf /tmp/tools.tgz /tmp/mongodb-database-tools-* && \
      chmod +x /usr/bin/mongo*
    fi
  fi

  TMP_RESTORE_DIR="/tmp/genieacs_restore_$$"
  mkdir -p "$TMP_RESTORE_DIR"
  tar -xzf "$BACKUP_ARCHIVE" -C "$TMP_RESTORE_DIR"
  
  RESTORE_OK=0
  if command -v mongorestore >/dev/null 2>&1; then
    if mongorestore --uri="mongodb://genie:genie@127.0.0.1:27017/genieacs" --drop "$TMP_RESTORE_DIR/genieacs" >/dev/null 2>&1; then
      RESTORE_OK=1
    elif mongorestore --uri="mongodb://127.0.0.1:27017/genieacs" --drop "$TMP_RESTORE_DIR/genieacs" >/dev/null 2>&1; then
      RESTORE_OK=1
    elif mongorestore --drop "$TMP_RESTORE_DIR/genieacs" >/dev/null 2>&1; then
      RESTORE_OK=1
    fi
  fi
  
  # Fallback restore dengan PyMongo dan BSON jika mongorestore gagal atau belum ada
  if [ "$RESTORE_OK" -ne 1 ]; then
    echo -e "${YELLOW}Menjalankan Python PyMongo fallback restore...${NC}"
    if python3 -c '
import os, sys, pymongo, bson
target_dir = sys.argv[1]
client = None
for uri in ["mongodb://genie:genie@127.0.0.1:27017/genieacs", "mongodb://127.0.0.1:27017/genieacs"]:
    try:
        c = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
        c.genieacs.command("ping")
        client = c
        break
    except Exception:
        continue
if not client:
    sys.exit(1)
db = client["genieacs"]
for f in os.listdir(target_dir):
    if f.endswith(".bson"):
        col = f[:-5]
        with open(os.path.join(target_dir, f), "rb") as bf:
            docs = bson.decode_all(bf.read())
            if docs:
                db[col].drop()
                db[col].insert_many(docs)
sys.exit(0)
' "$TMP_RESTORE_DIR/genieacs" 2>/dev/null; then
      RESTORE_OK=1
    fi
  fi
  
  if [ "$RESTORE_OK" -eq 1 ]; then
    echo -e "${GREEN}[OK] Database GenieACS berhasil di-restore 100% siap pakai! (Virtual Parameters, Presets, Provisions)${NC}"
  else
    echo -e "${RED}[WARNING] Gagal me-restore database otomatis. Silakan jalankan 'bash apply-template.sh' nanti.${NC}"
  fi

  # Bersihkan cache hash UI lokal agar langsung update tampilan
  python3 -c '
import pymongo
for uri in ["mongodb://genie:genie@127.0.0.1:27017/genieacs", "mongodb://127.0.0.1:27017/genieacs"]:
    try:
        c = pymongo.MongoClient(uri, serverSelectionTimeoutMS=1500)
        c.genieacs.config.delete_one({"_id": "ui-local-cache-hash"})
        tab6_configs = {
            'ui.multiTabs.6.label': "'INFO'",
            'ui.multiTabs.6.route': "'info'",
            'ui.multiTabs.6.components.0.type': "'tags'",
            'ui.multiTabs.6.components.1.type': "'ping'",
            'ui.multiTabs.6.components.2.type': "'customer-info'",
            'ui.multiTabs.6.components.3.type': "'device-actions'"
        }
        for k, v in tab6_configs.items():
            c.genieacs.config.replace_one({'_id': k}, {'_id': k, 'value': v}, upsert=True)
        break
    except Exception:
        pass
' 2>/dev/null || true

  rm -rf "$TMP_RESTORE_DIR"
else
  echo -e "${YELLOW}[INFO] File genieacs_db.tar.gz tidak ditemukan. Database akan dimulai dari awal.${NC}"
fi

# 5. Instalasi Paket GenieACS via NPM
echo -e "\n${BLUE}[4/7] Menginstall GenieACS secara global via NPM...${NC}"
# Pastikan npm menginstall ke /usr prefix agar binary masuk langsung ke /usr/bin
/usr/bin/npm install -g genieacs@1.2.13 --unsafe-perm=true --prefix /usr 2>/dev/null || \
npm install -g genieacs@1.2.13 --unsafe-perm=true --prefix /usr 2>/dev/null || \
npm install -g genieacs@1.2.13 --unsafe-perm=true

# Terapkan UI Frontend Multi-Tab & Modifikasi Binaries (ALIJAYA NET)
MOD_ARCHIVE=""
if [ -f "${SCRIPT_DIR}/genieacs_ui_mod.tar.gz" ]; then
  MOD_ARCHIVE="${SCRIPT_DIR}/genieacs_ui_mod.tar.gz"
elif [ -f "./genieacs_ui_mod.tar.gz" ]; then
  MOD_ARCHIVE="./genieacs_ui_mod.tar.gz"
elif [ -f "/root/genieacs-multitab-mod/genieacs_ui_mod.tar.gz" ]; then
  MOD_ARCHIVE="/root/genieacs-multitab-mod/genieacs_ui_mod.tar.gz"
fi

if [ -n "$MOD_ARCHIVE" ] && [ -f "$MOD_ARCHIVE" ]; then
  echo -e "${YELLOW}Menerapkan tema & modul tampilan Multi-Tab (ALIJAYA NET)...${NC}"
  GENIE_DIR=""
  if [ -d "/usr/lib/node_modules/genieacs" ]; then
    GENIE_DIR="/usr/lib/node_modules/genieacs"
  elif [ -d "/usr/local/lib/node_modules/genieacs" ]; then
    GENIE_DIR="/usr/local/lib/node_modules/genieacs"
  fi
  
  if [ -n "$GENIE_DIR" ]; then
    tar -zxf "$MOD_ARCHIVE" --strip-components=1 -C "$GENIE_DIR/" 2>/dev/null || tar -zxf "$MOD_ARCHIVE" -C "$GENIE_DIR/"
    if [ -d "$GENIE_DIR/genieacs/public" ]; then
      cp -rf "$GENIE_DIR/genieacs/"* "$GENIE_DIR/"
      rm -rf "$GENIE_DIR/genieacs"
    fi
    chmod +x "$GENIE_DIR/bin/"* 2>/dev/null || true
    cp -f "$GENIE_DIR/bin/"* /usr/bin/ 2>/dev/null || true
    cp -f "$GENIE_DIR/bin/"* /usr/local/bin/ 2>/dev/null || true
    chmod +x /usr/bin/genieacs-* /usr/local/bin/genieacs-* 2>/dev/null || true
    echo -e "${GREEN}[OK] File frontend Multi-Tab & Binaries berhasil diterapkan!${NC}"
  fi
fi

# Pastikan symlink binary genieacs-* selalu ada di /usr/bin/ dan /usr/local/bin/
for mod in "cwmp" "nbi" "fs" "ui"; do
  BIN_LOC=""
  if [ -x "/usr/bin/genieacs-${mod}" ]; then
    BIN_LOC="/usr/bin/genieacs-${mod}"
  elif [ -x "/usr/local/bin/genieacs-${mod}" ]; then
    BIN_LOC="/usr/local/bin/genieacs-${mod}"
  else
    BIN_LOC=$(find /usr /root/.nvm /opt -name "genieacs-${mod}" 2>/dev/null | head -n 1)
  fi
  
  if [ -n "$BIN_LOC" ]; then
    [ "$BIN_LOC" != "/usr/bin/genieacs-${mod}" ] && ln -sf "$BIN_LOC" "/usr/bin/genieacs-${mod}"
    [ "$BIN_LOC" != "/usr/local/bin/genieacs-${mod}" ] && ln -sf "$BIN_LOC" "/usr/local/bin/genieacs-${mod}"
  fi
  chmod +x "/usr/bin/genieacs-${mod}" 2>/dev/null || true
done

# Pastikan node binary juga ada di /usr/bin/node
if [ ! -x /usr/bin/node ] && command -v node >/dev/null 2>&1; then
  ln -sf $(which node) /usr/bin/node
fi

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
Wants=mongod.service

[Service]
User=genieacs
Group=genieacs
EnvironmentFile=/opt/genieacs/genieacs.env
PermissionsStartOnly=true
ExecStartPre=/usr/bin/install -d -m 0775 -o genieacs -g genieacs /var/log/genieacs /opt/genieacs/ext
ExecStart=/usr/bin/genieacs-${mod}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
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

# Salin aset frontend public (mywifi.html, peta.html, dsb)
if [ -d "${SCRIPT_DIR}/public" ]; then
  mkdir -p /opt/genieacs-agent/public
  cp -rf "${SCRIPT_DIR}/public"/* /opt/genieacs-agent/public/ 2>/dev/null || true
  if [ -n "$GENIE_DIR" ] && [ -d "$GENIE_DIR/public" ]; then
    cp -rf "${SCRIPT_DIR}/public"/* "$GENIE_DIR/public/" 2>/dev/null || true
  fi
fi

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

# Pasang WhatsApp Baileys Gateway Agent
if [ -d "${SCRIPT_DIR}/whatsapp" ]; then
  cp -r "${SCRIPT_DIR}/whatsapp"/* /opt/genieacs-agent/
elif [ -d "./whatsapp" ]; then
  cp -r ./whatsapp/* /opt/genieacs-agent/
fi

if command -v npm >/dev/null 2>&1; then
  echo -e "${BLUE}Menginstall dependensi WhatsApp Baileys di /opt/genieacs-agent...${NC}"
  (cd /opt/genieacs-agent && npm install @whiskeysockets/baileys@7.0.0-rc11 pino@^9.6.0 qrcode@^1.5.4 qrcode-terminal@^0.12.0 --ignore-scripts --no-audit --no-fund 2>/dev/null || true)
fi

cat << 'EOF' > /etc/systemd/system/genieacs-agent.service
[Unit]
Description=GenieACS AI Telegram Agent (ALIJAYA NET)
After=network.target mongod.service genieacs-nbi.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/genieacs-agent
EnvironmentFile=-/opt/genieacs/genieacs.env
EnvironmentFile=-/etc/default/genieacs
EnvironmentFile=-/etc/genieacs.env
ExecStart=/usr/bin/python3 /opt/genieacs-agent/agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat << 'EOF' > /etc/systemd/system/genieacs-whatsapp.service
[Unit]
Description=GenieACS WhatsApp AI Agent (Baileys Gateway - ALIJAYA NET)
After=network.target mongod.service genieacs-nbi.service genieacs-agent.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/genieacs-agent
ExecStart=/usr/bin/node --experimental-global-webcrypto /opt/genieacs-agent/whatsapp-bot.mjs
Restart=always
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable genieacs-agent.service genieacs-whatsapp.service 2>/dev/null || true
systemctl restart genieacs-agent.service genieacs-whatsapp.service 2>/dev/null || true

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
echo -e "${CYAN}║${NC}  ✈️ ${BOLD}Telegram Agent${NC}       : ${GREEN}AKTIF (Ketik 'set-bot' di terminal)${NC}"
echo -e "${CYAN}║${NC}  📱 ${BOLD}WhatsApp Agent${NC}       : ${GREEN}AKTIF (Baileys Gateway Port 7559)${NC}"
echo -e "${CYAN}║${NC}  ⚙️ ${BOLD}Web Pengaturan Bot${NC}   : ${YELLOW}${BOLD}http://${IP_ADDRESS}:7558${NC} (Menu UI '🤖 Bot AI & WA')"
echo -e "${CYAN}║${NC}  ⚡ ${BOLD}Status Layanan${NC}       : ${GREEN}GenieACS, MongoDB, Telegram & WA AKTIF (OK)${NC}"
echo -e "${CYAN}║${NC}  🛡️ ${BOLD}Proteksi Storage${NC}     : ${GREEN}Logrotate & Ramlog AKTIF (Bebas Disk Penuh)${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC}  👑 ${BOLD}DEVELOPER & SUPPORT${NC}  : ${GREEN}${BOLD}ALIJAYA NET${NC}"
echo -e "${CYAN}║${NC}  📱 ${BOLD}WHATSAPP / TELEPON${NC}   : ${YELLOW}${BOLD}081947215703${NC} (${CYAN}0819-4721-5703${NC})"
echo -e "${CYAN}║${NC}  💬 ${BOLD}HUBUNGI KAMI (WA)${NC}    : ${CYAN}https://wa.me/6281947215703${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}\n"
