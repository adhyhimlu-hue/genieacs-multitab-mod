# 🚀 GenieACS Multi-Tab Mod (Informatif, Universal Multi-Vendor & 0-Faults)

[![GitHub Repository](https://img.shields.io/badge/GitHub-alijayanet%2Fgenieacs--multitab--mod-blue?logo=github)](https://github.com/alijayanet/genieacs-multitab-mod)
[![GenieACS Version](https://img.shields.io/badge/GenieACS-v1.2.13%2B-orange?logo=node.js)](https://genieacs.com/)
[![Node.js Version](https://img.shields.io/badge/Node.js-v20%20LTS-green?logo=node.js)](https://nodejs.org/)
[![Database](https://img.shields.io/badge/Database-MongoDB%204.4%2B%20%7C%206.x%20%7C%207.x-brightgreen?logo=mongodb)](https://www.mongodb.com/)
[![Platform](https://img.shields.io/badge/Platform-Armbian%20%7C%20Linux%20SBC%20%7C%20Ubuntu%20%7C%20Debian-yellow?logo=linux)](https://www.armbian.com/)
[![Developer](https://img.shields.io/badge/Developer-ALIJAYA--NET-00bcd4?logo=whatsapp)](https://wa.me/6281947215703)
[![License](https://img.shields.io/badge/License-MIT-purple)](#)

Modifikasi tampilan dan fungsi **GenieACS TR-069 ACS Server** yang dirancang khusus untuk mempermudah operasional teknisi dan pengelola jaringan internet (**RT/RW Net / ISP Mandiri**). Mengubah tampilan standar GenieACS yang kosong/polos menjadi **Multi-Tab Informatif Lengkap**, mendukung tombol **"Add WAN"** langsung dari Web UI, pemantauan port fisik LAN, tabel Multi-SSID & sinyal RSSI klien WiFi, serta dilengkapi **script provision universal bebas fault (0 Faults)** untuk berbagai merk ONT/ONU (ZTE, Huawei, Fiberhome, GM220-S, CIOT, dsb).

---

## 📞 Informasi Pengembang & Layanan Support

Project ini dikembangkan, dioptimasi, dan dipelihara secara resmi oleh **ALIJAYA NET**:
* **Pengembang / Author** : **ALIJAYA NET**
* **WhatsApp / Telepon** : [**081947215703**](https://wa.me/6281947215703) (`+62 819-4721-5703`)
* **Repository Resmi** : [https://github.com/alijayanet/genieacs-multitab-mod](https://github.com/alijayanet/genieacs-multitab-mod)
* **Kebutuhan** : Tanya jawab teknis, panduan instalasi di STB Armbian (B860H, HG680P, dsb), integrasi billing, penyesuaian parameter khusus, dan konsultasi jaringan RT/RW Net.

---

## 🌟 Masalah pada GenieACS Standar vs Solusi Mod Ini

| Fitur | GenieACS Standar Bawaan | GenieACS Multi-Tab Mod (ALIJAYA NET) |
| :--- | :--- | :--- |
| **Tata Letak Tab** | Hanya tab summary bawaan yang sangat sedikit datanya | **6 Tab Lengkap**: Summary, WAN, WLAN, LAN, USER, TR-069 |
| **Tambah WAN (Add WAN)** | Harus buka modem klien atau kirim RPC manual | **Tombol "Add WAN"** langsung di tabel Web UI |
| **Informasi Redaman & Suhu** | Tidak ada parameter RX Power bawaan | **RX Power (dBm)** & Suhu Transceiver (°C) universal otomatis |
| **Monitoring WiFi** | Terpencar dan sering tidak muncul | Tabel **Multi-SSID 1-4**, Channel, Sandi, & **Daftar Klien RSSI** |
| **Monitoring LAN** | Tidak menampilkan port fisik & daftar HP | Tabel **LAN Port 1-4 (Speed/Duplex)** & **Daftar Klien Hosts (IP, MAC)** |
| **Akses Web GUI Modem** | Harus ketik manual IP modem | **Direct Link Klik Langsung** via IP WAN atau IP Gateway |
| **Kestabilan Sesi CWMP** | Sering timbul error `session_terminated` / rpc fault | **0 Faults**, provision bulletproof diuji pada puluhan multi-vendor |

---

## 📑 Struktur Tab & Rincian Fitur

```
┌────────────────────────────────────────────────────────────────────────┐
│                        GENIEACS MULTI-TAB MOD                          │
├───────────┬───────────┬───────────┬───────────┬───────────┬────────────┤
│  SUMMARY  │    WAN    │   WLAN    │    LAN    │   USER    │   TR-069   │
└───────────┴───────────┴───────────┴───────────┴───────────┴────────────┘
```

### 1. 📊 Tab Summary (Ringkasan Lengkap ONT)
* **Status Perangkat**: Indikator titik Online/Offline real-time (threshold 10 menit), waktu Last Inform, dan tombol *Summon*.
* **Identitas Hardware**: Serial Number, Vendor/Manufacturer, Product Class, Versi Hardware & Software, MAC Address.
* **Kualitas Sinyal Optik**: Nilai **Redaman RX Power dalam satuan dBm** dan Suhu Transceiver (°C).
* **Uptime**: Durasi aktif perangkat dan durasi aktif sesi PPPoE.
* **Koneksi Utama**: Username & Password PPPoE, IP WAN yang bisa diklik langsung, Router Gateway IP, WiFi SSID & Password utama, serta jumlah user aktif terhubung.

### 2. 🌐 Tab WAN (Internet, PPPoE & Tambah WAN)
* **Tombol "Add WAN"**: Tersedia tombol pembuatan profil WAN baru langsung dari footer tabel tanpa membuka Web GUI modem pelanggan.
* **Tabel Koneksi PPPoE (WANPPPConnection)**: Menampilkan Enable/Disable, Nama Profil WAN, VLAN ID, Tipe Koneksi, Service List (INTERNET/VOIP/TR069), Username & Password PPPoE, Status NAT, Status Koneksi (Connected/Disconnected), serta Alamat IP Eksternal.
* **Tabel Koneksi IP WAN (WANIPConnection)**: Untuk koneksi berbasis IPoE, DHCP Client, atau Static IP.
* **Tombol Hapus / Ubah**: Dukungan hapus dan ubah parameter WAN secara instan via TR-069.

### 3. 📶 Tab WLAN (WiFi Multi-SSID & Client RSSI)
* **Ringkasan WiFi Utama (SSID 1)**: Nama WiFi, Sandi WiFi (bisa langsung diedit dari Web UI), User aktif terkoneksi, Saluran (Channel), dan Status Radio WiFi.
* **Tabel Multi-SSID (SSID 1 s/d 4)**: Nama SSID, Sandi (KeyPassphrase / PreSharedKey), Mode Keamanan (WPA/WPA2/Open), Channel & Auto Channel, Daya Pancar (Transmit Power), Jumlah Perangkat Terhubung, dan BSSID (MAC WiFi).
* **Tabel Klien WiFi Terkoneksi (Associated Devices)**: Menampilkan MAC Address HP/Laptop klien, Alamat IP klien, Nilai Kualitas Sinyal RSSI (dBm), dan Nama Perangkat (Device Name/Hostname).

### 4. 🔌 Tab LAN (Port Fisik & Daftar Hosts Terkoneksi)
* **Pengaturan Gateway & DHCP**: IP Gateway Router, Subnet Mask, Status DHCP Server, IP Pool Min/Max, dan DNS Servers.
* **Tabel Port Fisik LAN (LAN 1 - 4)**: Status kabel (Up/Down), Kecepatan Port (100 Mbps / 1 Gbps), Mode Duplex (Full/Half), Status Enable, dan MAC Address port LAN.
* **Tabel Daftar Perangkat Klien (Hosts)**: Menampilkan semua HP, Laptop, Access Point, atau STB yang terhubung ke modem lengkap dengan HostName, Alamat IP, MAC Address, Interface Type (Ethernet/WiFi), Status Aktif, dan Sisa Waktu Lease DHCP.

### 5. 👤 Tab USER (Akses Web GUI Modem Jarak Jauh)
* **Kredensial SuperAdmin Universal**: Menampilkan akun admin bawaan pabrik (seperti `telecomadmin` / `adminadmin`, dll).
* **Kredensial User Biasa**: Username & Password login pelanggan.
* **Tautan Akses Cepat**: Tautan klik langsung ke halaman Web GUI modem via IP WAN maupun IP Gateway lokal.

### 6. ⚙️ Tab TR-069 (Manajemen CWMP)
* **Konfigurasi Server ACS**: ACS URL, Periodic Inform Interval (detik), status Enable Inform.
* **Connection Request**: URL Connection Request, Username, dan Password untuk keperluan remote summon dari server.

---

## 🛠️ Cara Instalasi & Penggunaan

Tersedia **2 Metode Instalasi** sesuai dengan kondisi server Anda:

---

### METODE A: Fresh Install (Untuk Server / STB Armbian Baru dari Nol)
Gunakan metode ini jika Anda baru saja menginstall sistem operasi Linux (Armbian/Debian/Ubuntu) dan ingin memasang GenieACS lengkap dengan template multi-tab secara otomatis:

1. **Pastikan Login Sebagai Root**:
   ```bash
   sudo -i
   ```

2. **Clone Repository atau Unduh File Installer**:
   ```bash
   cd /root
   git clone https://github.com/alijayanet/genieacs-multitab-mod.git
   cd genieacs-multitab-mod
   ```

3. **Jalankan Script Auto-Installer**:
   ```bash
   chmod +x install-genieacs-armbian.sh
   bash install-genieacs-armbian.sh
   ```

4. **Selesai**: Script akan menginstall Node.js v20, MongoDB, GenieACS, membuat systemd service, dan otomatis me-restore database siap pakai.

---

### METODE B: Quick Apply Template (Untuk Server yang Sudah Terinstall GenieACS Standar)
Gunakan metode ini jika server Anda **sudah memiliki GenieACS aktif dan sudah ada modem pelanggan yang terdaftar**.

> [!IMPORTANT]
> Script ini **HANYA** memperbarui tampilan tab, virtual parameter, dan script provision.  
> Data modem pelanggan (`devices`) dan user login Anda **TIDAK AKAN TERHAPUS** (100% Aman).

1. **Unduh Paket Template & Script Penerap**:
   ```bash
   cd /root
   git clone https://github.com/alijayanet/genieacs-multitab-mod.git
   cd genieacs-multitab-mod
   ```

2. **Jalankan Script Penerap**:
   ```bash
   chmod +x apply-template.sh
   bash apply-template.sh
   ```

3. **Selesai**: Dalam hitungan detik seluruh tab informatif beserta **Telegram Bot AI Agent** akan langsung aktif! Silakan buka Web UI dan lakukan **Hard Refresh** (`Ctrl + F5`) di browser, lalu masukkan Token Telegram & Chat ID Anda di menu **Admin ➔ Config**.

---

## 🤖 Asisten AI Telegram GenieACS (Powered by Gemini)

Repositori ini sudah dilengkapi modul **Asisten AI Telegram** yang otomatis terpasang sebagai layanan sistem (`genieacs-agent.service`). Anda bisa mengontrol dan memantau seluruh modem pelanggan langsung dari chat Telegram menggunakan nama **Username PPPoE**:

### 🛠️ Fitur Asisten AI Telegram:
1. **Cek Redaman & Status Lengkap**:
   * Ketik: `/cek <username_pppoe>` *(contoh: `/cek cucimotor`)*
   * Atau bahasa santai: _"Cek redaman pelanggan cucimotor dong"_
   * Menampilkan Redaman RX Power (dBm), Suhu, IP WAN, Uptime, Status Online/Offline, dan jumlah user terhubung.
2. **Ganti SSID & Password WiFi Seketika**:
   * Ketik: `/wifi <username_pppoe> <ssid_baru> <password_baru>`
   * Atau bahasa santai: _"Ganti wifi budi01 jadi ALIJAYA-BUDI sandinya 12345678"_
3. **Restart / Reboot Modem Jarak Jauh**:
   * Ketik: `/reboot <username_pppoe>` *(contoh: `/reboot warnet_oki`)*

### ⚙️ Cara Konfigurasi Sangat Mudah (Langsung dari Web UI):
Anda **TIDAK PERLU** mengedit file skrip di server! Cukup buka menu GenieACS Web UI:
1. Masuk ke menu **Admin** ➔ **Config** (`http://<IP-SERVER>:3000/#!/config`).
2. Cari kata kunci: **`agent`**.
3. Isi parameter berikut lalu klik **Save**:
   * `agent.gemini.apiKey` : Masukkan API Key Gemini dari [Google AI Studio](https://aistudio.google.com/)
   * `agent.telegram.botToken` : Masukkan Token Bot Telegram dari [@BotFather](https://t.me/BotFather)
   * `agent.telegram.adminChatId` : Masukkan ID Chat Telegram Anda (bisa didapat via [@userinfobot](https://t.me/userinfobot))
4. Bot akan otomatis aktif dan menyapa Anda di Telegram!

---

## 🌐 Akses Web UI & Port Default

* **Alamat Web UI** : `http://<IP-SERVER>:3000`
* **Default Username** : `admin`
* **Default Password** : `admin` *(dapat diubah di menu Admin -> Users)*
* **CWMP ACS URL** : `http://<IP-SERVER>:7547` (Gunakan URL ini pada settingan TR-069 di modem klien)

---

## 📁 Struktur File Repository

```text
├── README.md                     # Dokumentasi resmi & panduan lengkap
├── install-genieacs-armbian.sh   # Script auto-installer GenieACS + MongoDB + Agent untuk server baru
├── apply-template.sh             # Script pengubah tema & multi-tab untuk server yang sudah aktif
├── agent.py                      # Skrip GenieACS AI Telegram Agent (bertenaga Gemini)
├── genieacs_template_ui.tar.gz   # Arsip template ringan (~17 KB) tanpa data perangkat
└── genieacs_db.tar.gz            # Backup database lengkap (~211 KB) siap pakai
```

---

## 🤝 Dukungan & Kontribusi

Jika Anda menemukan bug, memiliki saran parameter baru, atau membutuhkan bantuan instalasi dan integrasi jaringan:
* **Pengembang** : **ALIJAYA NET**
* **WhatsApp** : [**081947215703**](https://wa.me/6281947215703) (`0819-4721-5703`)
* **Issues / Feedback** : Silakan buat tiket melalui tab [Issues di GitHub](https://github.com/alijayanet/genieacs-multitab-mod/issues).

---

<p align="center">
  <b>Dikembangkan dengan ❤️ oleh ALIJAYA NET</b><br>
  <i>Solusi Manajemen Jaringan TR-069 & RT/RW Net yang Praktis dan Andal</i>
</p>
