#!/usr/bin/env python3
# ==============================================================================
# ALIJAYA NET - GenieACS AI Telegram Agent (Full Multi-Tab & Operations Mod)
# Pengembang: ALIJAYA NET (WhatsApp: 081947215703)
# ==============================================================================

import os
import sys
import shutil
import re
import time
import json
import logging
import subprocess
import requests
import pymongo
from urllib.parse import quote
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer as DefaultHTTPServer
except ImportError:
    from http.server import HTTPServer as DefaultHTTPServer
try:
    from http.server import ThreadingHTTPServer as DefaultHTTPServer
except ImportError:
    from http.server import HTTPServer as DefaultHTTPServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("GenieACSAgent")

MONGO_URI = "mongodb://genie:genie@127.0.0.1:27017/genieacs"
NBI_URL = "http://127.0.0.1:7557"

USER_STATES = {}
SEEN_DEVICES = set()
NOTIFIED_DROPS = {} # device_id -> timestamp

def get_db():
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        return client['genieacs']
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        return None

def get_config():
    db = get_db()
    if db is None:
        return {}
    cfgs = db.config.find({"_id": {"$regex": "^agent\\."}})
    res = {}
    for c in cfgs:
        val = str(c.get("value", "")).strip()
        while len(val) >= 2 and ((val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"'))):
            val = val[1:-1].strip()
        res[c["_id"]] = val.strip()
    return res

BRAND_NAME = "ALIJAYA NET"
BRAND_PHONE = "081947215703"

def update_branding(cfgs):
    global BRAND_NAME, BRAND_PHONE
    b_name = cfgs.get("agent.brand.name", "").strip()
    b_phone = cfgs.get("agent.brand.phone", "").strip()
    BRAND_NAME = b_name if b_name else "ALIJAYA NET"
    BRAND_PHONE = b_phone if b_phone else "081947215703"

def is_valid_token(val):
    if not val:
        return False
    if "MASUKKAN_" in val:
        return False
    return True

def parse_admin_chat_ids(val):
    if not val or not is_valid_token(val):
        return []
    cleaned = val.replace(";", ",").replace("\n", ",")
    return [x.strip() for x in cleaned.split(",") if x.strip()]

def is_authorized(sender_id, admin_ids):
    if not admin_ids:
        return False
    return str(sender_id) in admin_ids

# ==============================================================================
# KEYBOARD MARKUPS
# ==============================================================================

def get_main_menu_keyboard():
    return {
        "keyboard": [
            [{"text": "🔍 Cek Modem"}, {"text": "⚠️ Cek Redaman Kritis"}],
            [{"text": "👥 Daftar Klien WiFi"}, {"text": "🆕 Modem Belum Setting"}],
            [{"text": "🌐 Tambah / Set WAN"}, {"text": "🔄 Reboot Modem"}],
            [{"text": "📶 Ubah WiFi / Sandi"}, {"text": "📊 Status Server STB"}],
            [{"text": "❓ Bantuan / Help"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def get_device_inline_keyboard(pppoe_user, dev_id=None, wifi_enabled=True):
    target = pppoe_user if pppoe_user else dev_id
    wifi_toggle_text = "🚫 Matikan WiFi" if wifi_enabled else "📶 Hidupkan WiFi"
    wifi_toggle_action = f"wifioff:{target}" if wifi_enabled else f"wifion:{target}"
    
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Reboot Modem", "callback_data": f"reboot:{target}"},
                {"text": "⚡ Refresh Data", "callback_data": f"refresh:{target}"}
            ],
            [
                {"text": "👥 Cek Klien HP", "callback_data": f"klien:{target}"},
                {"text": "🌐 Set WAN PPPoE", "callback_data": f"prompt_wan:{target}"}
            ],
            [
                {"text": "📶 Ganti SSID", "callback_data": f"prompt_ssid:{target}"},
                {"text": "🔑 Ganti Sandi", "callback_data": f"prompt_pass:{target}"}
            ],
            [
                {"text": wifi_toggle_text, "callback_data": wifi_toggle_action},
                {"text": "⚠️ Factory Reset", "callback_data": f"prompt_fr:{target}"}
            ]
        ]
    }

# ==============================================================================
# GENIEACS CORE OPERATIONS
# ==============================================================================


def normalize_phone(phone_str):
    if not phone_str:
        return ""
    digits = re.sub(r"\D", "", str(phone_str))
    if digits.startswith("62"):
        return "0" + digits[2:]
    return digits

def get_phone_variations(phone_str):
    if not phone_str:
        return []
    digits = re.sub(r"\D", "", str(phone_str))
    if len(digits) < 8:
        return [str(phone_str).strip()]
    if digits.startswith("62"):
        local = "0" + digits[2:]
        intl = digits
    elif digits.startswith("0"):
        local = digits
        intl = "62" + digits[1:]
    else:
        local = "0" + digits
        intl = "62" + digits
    return list(set([local, intl, f"+{intl}", f"wa:{local}", f"wa:{intl}"]))

def find_device_by_phone(phone_str):
    if not phone_str:
        return None
    db = get_db()
    if db is None:
        return None
    variations = get_phone_variations(phone_str)
    digits = re.sub(r"\D", "", str(phone_str))
    local = "0" + digits[2:] if digits.startswith("62") else digits

    dev = db.devices.find_one({
        "$or": [
            {"_tags": {"$in": variations}},
            {"tags": {"$in": variations}},
            {"_tags": {"$regex": local}},
            {"tags": {"$regex": local}}
        ]
    })
    return dev

def add_device_tag(dev_id, tag_str):
    clean_tag = tag_str.strip()
    db = get_db()
    if db is not None:
        try:
            db.devices.update_one({"_id": dev_id}, {"$addToSet": {"_tags": clean_tag}})
        except Exception:
            pass
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tags/{quote(clean_tag)}"
        r = requests.post(url, timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def remove_device_tag(dev_id, tag_str):
    clean_tag = tag_str.strip()
    db = get_db()
    if db is not None:
        try:
            db.devices.update_one({"_id": dev_id}, {"$pull": {"_tags": clean_tag}})
        except Exception:
            pass
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tags/{quote(clean_tag)}"
        r = requests.delete(url, timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def get_device_pppoe_username(dev):
    if not dev:
        return "Unknown"
    vp = dev.get("VirtualParameters", {})
    pppoe = vp.get("pppoeUsername", {}).get("_value")
    if pppoe and pppoe not in ["0", "undefined", "null"]:
        return str(pppoe).strip()
    wandev = dev.get("InternetGatewayDevice", {}).get("WANDevice", {})
    for wk in wandev:
        if wk.startswith("_"): continue
        wcds = wandev[wk].get("WANConnectionDevice", {})
        for ck in wcds:
            if ck.startswith("_"): continue
            ppps = wcds[ck].get("WANPPPConnection", {})
            for pk in ppps:
                if pk.startswith("_"): continue
                u = ppps[pk].get("Username", {}).get("_value")
                if u:
                    return str(u).strip()
    return dev.get("_deviceId", {}).get("_SerialNumber") or dev.get("_id", "Unknown")

def get_customer_friendly_summary(dev):
    if not dev:
        return "❌ Perangkat Anda tidak ditemukan."
    vp = dev.get("VirtualParameters", {})
    igd = dev.get("InternetGatewayDevice", {})
    
    pppoe = get_device_pppoe_username(dev)
    
    # Redaman
    rx = vp.get("RXPower", {}).get("_value") or "-"
    rx_badge = ""
    if rx != "-":
        try:
            rx_val = float(str(rx).replace("dBm", "").strip())
            if rx_val >= -24.0:
                rx_badge = "(Sinyal Bagus 🟢)"
            elif rx_val >= -27.0:
                rx_badge = "(Normal 🟡)"
            else:
                rx_badge = "(Lemah / Redaman Tinggi 🔴)"
        except Exception:
            pass
        if not str(rx).endswith("dBm"):
            rx = f"{rx} dBm"

    uptime = vp.get("getdeviceuptime", {}).get("_value") or vp.get("uptimeDevice", {}).get("_value") or "-"
    
    wlan1 = igd.get("LANDevice", {}).get("1", {}).get("WLANConfiguration", {}).get("1", {})
    ssid = wlan1.get("SSID", {}).get("_value") or vp.get("WlanSSID", {}).get("_value") or "-"
    wifi_pass = (
        wlan1.get("KeyPassphrase", {}).get("_value") or
        wlan1.get("PreSharedKey", {}).get("1", {}).get("KeyPassphrase", {}).get("_value") or
        vp.get("WlanPassword", {}).get("_value") or
        "(Tersimpan di Modem)"
    )
    
    clients = (
        wlan1.get("TotalAssociations", {}).get("_value") or
        vp.get("activedevices", {}).get("_value") or
        "0"
    )
    
    last_inform = dev.get("_lastInform")
    online_str = "Offline 🔴"
    if last_inform:
        diff_sec = (time.time() - last_inform.timestamp())
        if diff_sec < 600:
            online_str = "Online (Normal) 🟢"
        else:
            online_str = f"Offline ({int(diff_sec//60)} mnt lalu) 🔴"

    return (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"  📶 *STATUS LAYANAN WIFI ANDA*\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"• *ID Pelanggan*   : `{pppoe}`\n"
        f"• *Status Koneksi* : {online_str}\n"
        f"• *Nama WiFi (SSID)*: `{ssid}`\n"
        f"• *Kata Sandi*     : `{wifi_pass}`\n"
        f"• *Kualitas Sinyal*: `{rx}` {rx_badge}\n"
        f"• *Perangkat Konek*: `{clients} HP/Laptop`\n"
        f"• *Waktu Aktif*    : `{uptime}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Perintah Mandiri:*\n"
        f"• `wifi <nama_baru> <sandi_baru>` ➔ Ganti nama & sandi\n"
        f"• `pass <sandi_baru>` ➔ Ganti sandi saja (min. 8 huruf/angka)\n"
        f"• `ssid <nama_baru>` ➔ Ganti nama WiFi saja\n"
        f"• `reboot` ➔ Restart modem jika koneksi berat"
    )

def find_device(query_str):
    db = get_db()
    if db is None:
        return None
    q = query_str.strip()
    reg = {"$regex": q, "$options": "i"}

    dev = db.devices.find_one({
        "$or": [
            {"_tags": reg},
            {"tags": reg},
            {"VirtualParameters.pppoeUsername._value": reg},
            {"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.Username._value": reg},
            {"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.2.WANPPPConnection.1.Username._value": reg},
            {"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.3.WANPPPConnection.1.Username._value": reg},
            {"VirtualParameters.WlanSSID._value": reg},
            {"InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID._value": reg},
            {"_id": reg},
            {"_deviceId._SerialNumber": reg},
            {"DeviceID.SerialNumber._value": reg},
            {"VirtualParameters.pppoeIP._value": q},
            {"VirtualParameters.MacAddress._value": reg},
            {"VirtualParameters.PonMac._value": reg},
            {"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.ExternalIPAddress._value": q}
        ]
    })
    return dev

def get_device_summary(dev):
    if not dev:
        return None, "❌ Perangkat modem tidak ditemukan. Pastikan Username PPPoE atau Serial Number benar.", True
    
    dev_id = dev.get("_id", "Unknown")
    vp = dev.get("VirtualParameters", {})
    igd = dev.get("InternetGatewayDevice", {})
    did = dev.get("_deviceId", {})
    
    # 1. Identitas PPPoE / Nama Pelanggan
    pppoe = vp.get("pppoeUsername", {}).get("_value")
    if not pppoe:
        wandev = igd.get("WANDevice", {})
        for wk in wandev:
            if wk.startswith("_"): continue
            wcds = wandev[wk].get("WANConnectionDevice", {})
            for ck in wcds:
                if ck.startswith("_"): continue
                ppps = wcds[ck].get("WANPPPConnection", {})
                for pk in ppps:
                    if pk.startswith("_"): continue
                    u = ppps[pk].get("Username", {}).get("_value")
                    if u:
                        pppoe = u
                        break
    
    has_pppoe = bool(pppoe and pppoe not in ["0", "undefined", "null"])
    display_user = pppoe if has_pppoe else "(Belum Terisi / ONT Baru)"
    
    # 2. Redaman & Sinyal Optik
    rx = vp.get("RXPower", {}).get("_value") or "-"
    rx_badge = ""
    if rx != "-":
        try:
            rx_val = float(str(rx).replace("dBm", "").strip())
            if rx_val >= -23.0:
                rx_badge = "(Sangat Bagus 🟢)"
            elif rx_val >= -26.0:
                rx_badge = "(Normal 🟡)"
            else:
                rx_badge = "(Kritis / Drop 🔴)"
        except Exception:
            pass
        if not str(rx).endswith("dBm"):
            rx = f"{rx} dBm"
        
    temp = vp.get("gettemp", {}).get("_value") or vp.get("temp", {}).get("_value") or "-"
    if temp != "-" and not str(temp).endswith("°C"):
        temp = f"{temp} °C"
        
    uptime = vp.get("getdeviceuptime", {}).get("_value") or vp.get("uptimeDevice", {}).get("_value") or "-"
    
    ip = vp.get("pppoeIP", {}).get("_value") or "-"
    if ip == "-":
        wandev = igd.get("WANDevice", {})
        for wk in wandev:
            if wk.startswith("_"): continue
            wcds = wandev[wk].get("WANConnectionDevice", {})
            for ck in wcds:
                if ck.startswith("_"): continue
                ppps = wcds[ck].get("WANPPPConnection", {})
                for pk in ppps:
                    if pk.startswith("_"): continue
                    ext_ip = ppps[pk].get("ExternalIPAddress", {}).get("_value")
                    if ext_ip and ext_ip != "0.0.0.0":
                        ip = ext_ip
                        break
    
    wlan1 = igd.get("LANDevice", {}).get("1", {}).get("WLANConfiguration", {}).get("1", {})
    ssid = wlan1.get("SSID", {}).get("_value") or vp.get("WlanSSID", {}).get("_value") or "-"
    wifi_pass = (
        wlan1.get("KeyPassphrase", {}).get("_value") or
        wlan1.get("PreSharedKey", {}).get("1", {}).get("KeyPassphrase", {}).get("_value") or
        vp.get("WlanPassword", {}).get("_value") or
        "(Tersimpan Aman di Modem)"
    )
    
    wifi_enable_val = str(wlan1.get("Enable", {}).get("_value", "true")).lower()
    wifi_is_on = wifi_enable_val not in ["false", "0"]
    
    clients = (
        wlan1.get("TotalAssociations", {}).get("_value") or
        vp.get("activedevices", {}).get("_value") or
        "0"
    )
    
    last_inform = dev.get("_lastInform")
    online_str = "Offline 🔴"
    if last_inform:
        diff_sec = (time.time() - last_inform.timestamp())
        if diff_sec < 600:
            online_str = "Online (Aktif) 🟢"
        else:
            online_str = f"Offline ({int(diff_sec//60)} mnt lalu) 🔴"
            
    mfr = did.get("_Manufacturer") or dev.get("DeviceID", {}).get("Manufacturer", {}).get("_value") or "-"
    model = did.get("_ProductClass") or dev.get("DeviceID", {}).get("ProductClass", {}).get("_value") or "-"
    sn = did.get("_SerialNumber") or dev.get("DeviceID", {}).get("SerialNumber", {}).get("_value") or dev_id
    mac = vp.get("MacAddress", {}).get("_value") or vp.get("PonMac", {}).get("_value") or "-"
    
    res = (
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"  👤 *PELANGGAN : {display_user.upper()}*\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"• *Akun PPPoE*    : `{display_user}`\n"
        f"• *Status ONT*    : {online_str}\n"
        f"• *Redaman (RX)*  : `{rx}` {rx_badge}\n"
        f"• *Suhu Transceiver*: `{temp}`\n"
        f"• *IP WAN PPPoE*  : `{ip}`\n"
        f"• *Uptime Modem*  : `{uptime}`\n"
        f"• *Nama WiFi*     : `{ssid}` ({'Radio ON 🟢' if wifi_is_on else 'Radio OFF 🔴'})\n"
        f"• *Sandi WiFi*    : `{wifi_pass}`\n"
        f"• *User Konek*    : `{clients} perangkat`\n"
        f"• *Model Hardware*: {mfr} {model}\n"
        f"• *Serial Number* : `{sn}`\n"
        f"• *MAC Address*   : `{mac}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 *{BRAND_NAME} TR-069 Management*"
    )
    return display_user, res, wifi_is_on

def get_device_clients(dev):
    if not dev:
        return "❌ Perangkat modem tidak ditemukan."
    
    dev_id = dev.get("_id", "Unknown")
    vp = dev.get("VirtualParameters", {})
    pppoe = vp.get("pppoeUsername", {}).get("_value") or dev_id
    
    igd = dev.get("InternetGatewayDevice", {})
    lan = igd.get("LANDevice", {}).get("1", {})
    hosts = lan.get("Hosts", {}).get("Host", {})
    
    client_list = []
    for k, h in hosts.items():
        if k.startswith("_"): continue
        ip = h.get("IPAddress", {}).get("_value")
        mac = h.get("MACAddress", {}).get("_value")
        name = h.get("HostName", {}).get("_value") or "Perangkat WiFi"
        active = str(h.get("Active", {}).get("_value", "true")).lower()
        if ip or mac:
            is_act = active not in ["false", "0"]
            client_list.append({
                "name": name,
                "ip": ip or "-",
                "mac": mac or "-",
                "active": is_act
            })
            
    if not client_list:
        return (
            f"👥 *DAFTAR PERANGKAT KLIEN TERKONEKSI*\n"
            f"👤 *Pelanggan*: `{pppoe}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Tidak ada data klien yang tersimpan di memori TR-069 saat ini.\n"
            f"Ketik `/refresh {pppoe}` untuk memperbarui data langsung dari modem."
        )
        
    lines = [
        f"👥 *DAFTAR PERANGKAT KLIEN TERKONEKSI*",
        f"👤 *Pelanggan*: `{pppoe.upper()}`",
        f"━━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, c in enumerate(client_list[:15], start=1):
        status_icon = "🟢" if c["active"] else "⚪"
        lines.append(f"{idx}. 📱 *{c['name']}* {status_icon}")
        lines.append(f"   • IP: `{c['ip']}` | MAC: `{c['mac']}`")
        
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 Total Terdeteksi: *{len(client_list)} perangkat*")
    return "\n".join(lines)

def get_bad_rx_summary():
    db = get_db()
    if db is None:
        return "❌ Gagal membuka database MongoDB."
        
    bad_list = []
    cursor = db.devices.find({"VirtualParameters.RXPower": {"$exists": True}})
    
    for dev in cursor:
        vp = dev.get("VirtualParameters", {})
        did = dev.get("_deviceId", {})
        dev_id = dev.get("_id", "")
        
        pppoe = vp.get("pppoeUsername", {}).get("_value")
        if not pppoe or pppoe in ["0", "undefined"]:
            pppoe = did.get("_SerialNumber") or dev_id
            
        rx_raw = vp.get("RXPower", {}).get("_value")
        try:
            rx_val = float(str(rx_raw).replace("dBm", "").strip())
            if rx_val < -26.0 or rx_val > -5.0:
                mfr = did.get("_Manufacturer", "")
                model = did.get("_ProductClass", "")
                bad_list.append({
                    "pppoe": pppoe,
                    "rx": rx_val,
                    "model": f"{mfr} {model}".strip()
                })
        except Exception:
            pass
            
    bad_list.sort(key=lambda x: x["rx"])
    
    if not bad_list:
        return "🎉 *SEMUA REDAMAN NORMAL!*\nTidak ditemukan modem dengan redaman kritis (seluruhnya di atas -26 dBm)."
        
    lines = [
        "⚠️ *DAFTAR MODEM REDAMAN KRITIS / DROP (< -26 dBm)*",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, b in enumerate(bad_list[:20], start=1):
        tag = "🔴 Kritis" if b["rx"] < -28.0 else "🟡 Waspada"
        lines.append(f"{idx}. 👤 *{b['pppoe']}* : `{b['rx']} dBm` ({tag})")
        if b["model"]:
            lines.append(f"   • Perangkat: {b['model']}")
            
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"Total bermasalah: *{len(bad_list)} pelanggan*.")
    lines.append("👉 _Ketik `/cek <username>` untuk melihat rincian pelanggan._")
    return "\n".join(lines)

def get_unconfigured_onts():
    db = get_db()
    if db is None:
        return "❌ Gagal membuka database MongoDB."
        
    cursor = db.devices.find({
        "$or": [
            {"VirtualParameters.pppoeUsername": {"$exists": False}},
            {"VirtualParameters.pppoeUsername._value": {"$in": ["", None, "0", "undefined"]}}
        ]
    })
    
    unconf_list = []
    for d in cursor:
        dev_id = d.get("_id", "")
        if "DISCOVERYSERVICE" in dev_id.upper():
            continue
        did = d.get("_deviceId", {})
        sn = did.get("_SerialNumber") or d.get("DeviceID", {}).get("SerialNumber", {}).get("_value") or dev_id
        mfr = did.get("_Manufacturer") or d.get("DeviceID", {}).get("Manufacturer", {}).get("_value") or "-"
        model = did.get("_ProductClass") or d.get("DeviceID", {}).get("ProductClass", {}).get("_value") or "-"
        
        last_inform = d.get("_lastInform")
        ago_str = "-"
        if last_inform:
            ago_str = f"{int((time.time() - last_inform.timestamp()) // 60)} mnt lalu"
            
        unconf_list.append({
            "sn": sn,
            "hw": f"{mfr} {model}".strip(),
            "ago": ago_str
        })
        
    if not unconf_list:
        return "✅ *Tidak ada ONT Baru*: Semua modem yang terhubung sudah memiliki konfigurasi PPPoE."
        
    lines = [
        "🆕 *DAFTAR MODEM BARU BELUM DISETTING PPPoE*",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    for idx, u in enumerate(unconf_list[:15], start=1):
        lines.append(f"{idx}. 📡 *SN*: `{u['sn']}` ({u['hw']})")
        lines.append(f"   • Terakhir Kontak: {u['ago']}")
        lines.append(f"   • Format: `/addwan {u['sn']} <user> <pass>`")
        
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"Total ONT baru: *{len(unconf_list)} perangkat*.")
    return "\n".join(lines)

def set_wifi_credentials(dev, new_ssid=None, new_password=None):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    
    param_values = []
    if new_ssid:
        param_values.append(["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID", new_ssid, "xsd:string"])
    if new_password:
        param_values.append(["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.KeyPassphrase", new_password, "xsd:string"])
        param_values.append(["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.KeyPassphrase", new_password, "xsd:string"])
        param_values.append(["VirtualParameters.WlanPassword", new_password, "xsd:string"])
        
    if not param_values:
        return False, "Tidak ada data SSID atau Sandi yang diubah."
        
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        body = {
            "name": "setParameterValues",
            "parameterValues": param_values
        }
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            return True, f"Berhasil mengirim instruksi ganti WiFi ke modem `{dev_id}`."
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except requests.exceptions.Timeout:
        return True, f"Instruksi ganti WiFi telah dikirim ke antrean modem `{dev_id}`."
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def set_wifi_power(dev, enable=True):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    val_str = "true" if enable else "false"
    
    param_values = [
        ["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.Enable", val_str, "xsd:boolean"],
        ["InternetGatewayDevice.LANDevice.1.WLANConfiguration.2.Enable", val_str, "xsd:boolean"]
    ]
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        body = {
            "name": "setParameterValues",
            "parameterValues": param_values
        }
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            action_txt = "diaktifkan kembali 🟢" if enable else "dimatikan 🔴"
            return True, f"Radio pemancar WiFi modem `{dev_id}` berhasil {action_txt}."
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except requests.exceptions.Timeout:
        action_txt = "diaktifkan 🟢" if enable else "dimatikan 🔴"
        return True, f"Instruksi radio WiFi {action_txt} telah dikirim ke antrean modem `{dev_id}`."
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def add_or_set_wan_pppoe(dev, pppoe_user, pppoe_pass, vlan_id=None):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    igd = dev.get("InternetGatewayDevice", {})
    wandev = igd.get("WANDevice", {})

    target_path = None
    for wk in wandev:
        if wk.startswith("_"): continue
        wcds = wandev[wk].get("WANConnectionDevice", {})
        for ck in wcds:
            if ck.startswith("_"): continue
            ppps = wcds[ck].get("WANPPPConnection", {})
            for pk in ppps:
                if pk.startswith("_"): continue
                p = ppps[pk]
                name = str(p.get("Name", {}).get("_value", "")).upper()
                cur_user = str(p.get("Username", {}).get("_value", ""))
                
                if "INTERNET" in name or cur_user == pppoe_user:
                    target_path = f"InternetGatewayDevice.WANDevice.{wk}.WANConnectionDevice.{ck}.WANPPPConnection.{pk}"
                    break
                elif not target_path and cur_user == "":
                    target_path = f"InternetGatewayDevice.WANDevice.{wk}.WANConnectionDevice.{ck}.WANPPPConnection.{pk}"
            if target_path and "INTERNET" in target_path:
                break
        if target_path and "INTERNET" in target_path:
            break

    if not target_path:
        add_url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        add_body = {
            "name": "addObject",
            "objectName": "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection."
        }
        try:
            requests.post(add_url, json=add_body, timeout=8)
        except Exception:
            pass
        target_path = "InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1"

    param_values = [
        [f"{target_path}.Enable", "true", "xsd:boolean"],
        [f"{target_path}.Username", pppoe_user, "xsd:string"],
        [f"{target_path}.Password", pppoe_pass, "xsd:string"],
        [f"{target_path}.ConnectionType", "IP_Routed", "xsd:string"],
        [f"{target_path}.NATEnabled", "true", "xsd:boolean"]
    ]

    if vlan_id:
        param_values.extend([
            [f"{target_path}.X_CT-COM_VlanID", str(vlan_id), "xsd:unsignedInt"],
            [f"{target_path}.X_ZTE-COM_VlanID", str(vlan_id), "xsd:unsignedInt"],
            [f"{target_path}.X_HW_VLAN", str(vlan_id), "xsd:unsignedInt"],
            [f"{target_path}.VLANID", str(vlan_id), "xsd:unsignedInt"]
        ])

    url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
    body = {
        "name": "setParameterValues",
        "parameterValues": param_values
    }
    try:
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            vlan_text = f"\n• *VLAN ID*: `{vlan_id}`" if vlan_id else ""
            return True, (
                f"✅ *Berhasil Menyetel Koneksi WAN PPPoE!*\n"
                f"• *Modem*: `{dev_id}`\n"
                f"• *Username PPPoE*: `{pppoe_user}`\n"
                f"• *Password PPPoE*: `{pppoe_pass}`"
                f"{vlan_text}\n"
                f"• *Profil Path*: `{target_path}`\n"
                f"• *Status*: Tugas terkirim ke modem via TR-069."
            )
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def set_superadmin_password(dev, new_pass):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    
    param_values = [
        ["InternetGatewayDevice.UserInterface.Password", new_pass, "xsd:string"],
        ["InternetGatewayDevice.UserInterface.X_ZTE-COM_AdminAccount.Password", new_pass, "xsd:string"],
        ["InternetGatewayDevice.X_CT-COM_TeleComAccount.Password", new_pass, "xsd:string"],
        ["InternetGatewayDevice.UserInterface.X_HW_AdminAccount.Password", new_pass, "xsd:string"]
    ]
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        body = {
            "name": "setParameterValues",
            "parameterValues": param_values
        }
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            return True, f"Perintah ubah sandi SuperAdmin Web ONT berhasil dikirim ke `{dev_id}`."
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def ping_diagnostics_task(dev, host="8.8.8.8"):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    param_values = [
        ["InternetGatewayDevice.IPPingDiagnostics.DiagnosticsState", "Requested", "xsd:string"],
        ["InternetGatewayDevice.IPPingDiagnostics.Host", host, "xsd:string"],
        ["InternetGatewayDevice.IPPingDiagnostics.NumberOfRepetitions", "3", "xsd:unsignedInt"]
    ]
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        body = {
            "name": "setParameterValues",
            "parameterValues": param_values
        }
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            return True, f"Perintah Ping Diagnostics ke `{host}` berhasil dikirim ke modem `{dev_id}` via TR-069."
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except requests.exceptions.Timeout:
        return True, f"Perintah Ping Diagnostics ke `{host}` berhasil dikirim ke antrean modem `{dev_id}`."
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def factory_reset_device(dev):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        body = {"name": "factoryReset"}
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            return True, f"Perintah FACTORY RESET berhasil dikirim ke modem `{dev_id}`. Modem akan kembali ke setelan pabrik."
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def reboot_device_task(dev):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        body = {"name": "reboot"}
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            return True, f"Perintah Restart berhasil dikirim ke modem `{dev_id}`."
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except requests.exceptions.Timeout:
        return True, f"Perintah Restart telah dikirim ke antrean modem `{dev_id}`."
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def refresh_device_task(dev):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    try:
        url = f"{NBI_URL}/devices/{quote(dev_id)}/tasks?connection_request"
        body = {"name": "refreshObject", "objectName": ""}
        r = requests.post(url, json=body, timeout=10)
        if r.status_code in [200, 202]:
            return True, f"Modem `{dev_id}` berhasil di-summon/refresh."
        else:
            return False, f"GenieACS merespon HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"Gagal menghubungi GenieACS NBI: {e}"

def get_server_stats():
    try:
        df_out = subprocess.check_output("df -h / | tail -n 1", shell=True).decode().split()
        disk_used = f"{df_out[2]} / {df_out[1]} ({df_out[4]})"
        free_out = subprocess.check_output("free -m | grep Mem:", shell=True).decode().split()
        ram_used = f"{free_out[2]} MB / {free_out[1]} MB"
        load_out = subprocess.check_output("uptime", shell=True).decode().strip()
        temp_out = "N/A"
        try:
            temp_raw = subprocess.check_output("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null", shell=True).decode().strip()
            if temp_raw:
                temp_out = f"{float(temp_raw)/1000:.1f} °C"
        except Exception:
            pass

        return (
            "📊 *STATUS SERVER STB ARMBIAN*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• *RAM Terpakai*: `{ram_used}`\n"
            f"• *Penyimpanan (eMMC/SD)*: `{disk_used}`\n"
            f"• *Suhu CPU STB*: `{temp_out}`\n"
            f"• *Uptime Server*: `{load_out.split('up ')[1].split(',')[0] if 'up ' in load_out else '-'}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 *GenieACS TR-069 & MongoDB: Normal*"
        )
    except Exception as e:
        return f"Gagal membaca status server: {e}"

# ==============================================================================
# GEMINI AI ASSISTANT FALLBACK
# ==============================================================================

def ask_gemini_ai(gemini_key, model_name, user_prompt, sender_id):
    if not is_valid_token(gemini_key):
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    system_instruction = (
        f"Anda adalah Asisten AI Resmi dari {BRAND_NAME} untuk Manajemen TR-069 GenieACS RT/RW Net.\n"
        f"Kontak CS/WhatsApp: {BRAND_PHONE}.\n"
        "Bantu teknisi lapangan menjawab pertanyaan teknis secara singkat, ramah, dan profesional seputar "
        "modem ONT (ZTE, Huawei, Fiberhome, GM220-S), redaman optik (standar bagus -14 s/d -24 dBm), "
        "koneksi PPPoE, WiFi, atau cara menggunakan perintah bot ini (/cek, /redaman, /ontbaru, /klien, /addwan, /wifioff, /wifion, /reboot)."
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_instruction}\n\nPertanyaan teknisi: {user_prompt}"}
                ]
            }
        ]
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=12)
        if r.status_code == 200:
            data = r.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception as e:
        logger.warning(f"Gemini API request failed: {e}")
    return None

# ==============================================================================
# TELEGRAM API HELPERS
# ==============================================================================

def send_telegram(token, chat_id, text, parse_mode="Markdown", reply_markup=None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")

def answer_callback(token, callback_id, text, show_alert=False):
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id, "text": text, "show_alert": show_alert}, timeout=8)
    except Exception as e:
        logger.error(f"Failed to answer callback: {e}")

def register_bot_commands(token):
    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    commands = [
        {"command": "menu", "description": "Tampilkan Menu Tombol Cepat"},
        {"command": "cek", "description": "Cek redaman & status: /cek <user_atau_sn>"},
        {"command": "redaman", "description": "Audit modem redaman kritis / drop"},
        {"command": "ontbaru", "description": "Cek modem baru belum disetting PPPoE"},
        {"command": "klien", "description": "Cek HP/laptop terhubung: /klien <user>"},
        {"command": "addwan", "description": "Tambah/Set WAN: /addwan <sn> <user> <pass> [vlan]"},
        {"command": "wifioff", "description": "Matikan pemancar WiFi: /wifioff <user>"},
        {"command": "wifion", "description": "Hidupkan pemancar WiFi: /wifion <user>"},
        {"command": "ssid", "description": "Ganti nama WiFi saja: /ssid <user> <nama>"},
        {"command": "pass", "description": "Ganti sandi WiFi saja: /pass <user> <sandi>"},
        {"command": "wifi", "description": "Ganti SSID & Sandi: /wifi <user> <ssid> <sandi>"},
        {"command": "ping", "description": "Diagnostik Ping TR-069: /ping <user> [host]"},
        {"command": "superadmin", "description": "Ganti sandi admin web ONT: /superadmin <user> <pass>"},
        {"command": "reboot", "description": "Restart modem pelanggan: /reboot <user>"},
        {"command": "factoryreset", "description": "Reset modem ke setelan pabrik: /factoryreset <user>"},
        {"command": "server", "description": "Cek status CPU, RAM & Suhu STB"},
        {"command": "help", "description": "Panduan lengkap penggunaan bot"}
    ]
    try:
        requests.post(url, json={"commands": commands}, timeout=8)
        logger.info("Bot commands registered successfully with Telegram.")
    except Exception as e:
        logger.warning(f"Could not register bot commands: {e}")

# ==============================================================================
# MESSAGE & CALLBACK HANDLERS
# ==============================================================================

def handle_callback_query(token, sender_id, cb_data, callback_id):
    logger.info(f"Handling callback: {cb_data} from {sender_id}")
    parts = cb_data.split(":", 1)
    act = parts[0]
    target = parts[1] if len(parts) > 1 else ""

    if act == "reboot" and target:
        dev = find_device(target)
        if not dev:
            answer_callback(token, callback_id, f"Modem {target} tidak ditemukan!", show_alert=True)
            return
        ok, msg = reboot_device_task(dev)
        answer_callback(token, callback_id, "Perintah Reboot terkirim!", show_alert=False)
        send_telegram(token, sender_id, f"{'✅' if ok else '❌'} {msg}")
        return

    if act == "refresh" and target:
        dev = find_device(target)
        if not dev:
            answer_callback(token, callback_id, f"Modem {target} tidak ditemukan!", show_alert=True)
            return
        refresh_device_task(dev)
        answer_callback(token, callback_id, "Memperbarui data dari modem...", show_alert=False)
        time.sleep(1.5)
        fresh_dev = find_device(target)
        pppoe, summary, wifi_on = get_device_summary(fresh_dev)
        kb = get_device_inline_keyboard(pppoe, fresh_dev.get("_id"), wifi_on)
        send_telegram(token, sender_id, summary, reply_markup=kb)
        return

    if act == "klien" and target:
        dev = find_device(target)
        if not dev:
            answer_callback(token, callback_id, f"Modem {target} tidak ditemukan!", show_alert=True)
            return
        answer_callback(token, callback_id, "Mengambil daftar klien...", show_alert=False)
        msg = get_device_clients(dev)
        send_telegram(token, sender_id, msg)
        return

    if act == "wifioff" and target:
        dev = find_device(target)
        if not dev:
            answer_callback(token, callback_id, f"Modem {target} tidak ditemukan!", show_alert=True)
            return
        ok, msg = set_wifi_power(dev, enable=False)
        answer_callback(token, callback_id, "WiFi dinonaktifkan!", show_alert=False)
        send_telegram(token, sender_id, f"{'✅' if ok else '❌'} {msg}")
        return

    if act == "wifion" and target:
        dev = find_device(target)
        if not dev:
            answer_callback(token, callback_id, f"Modem {target} tidak ditemukan!", show_alert=True)
            return
        ok, msg = set_wifi_power(dev, enable=True)
        answer_callback(token, callback_id, "WiFi diaktifkan!", show_alert=False)
        send_telegram(token, sender_id, f"{'✅' if ok else '❌'} {msg}")
        return

    if act == "prompt_fr" and target:
        answer_callback(token, callback_id, "Peringatan Reset Pabrik", show_alert=False)
        confirm_kb = {
            "inline_keyboard": [
                [
                    {"text": "⚠️ Ya, Reset Pabrik", "callback_data": f"do_fr:{target}"},
                    {"text": "❌ Batal", "callback_data": "cancel_fr"}
                ]
            ]
        }
        send_telegram(token, sender_id, (
            f"⚠️ *KONFIRMASI FACTORY RESET*\n"
            f"Apakah Anda yakin ingin mereset modem pelanggan `{target}` ke setelan pabrik?\n"
            f"_Seluruh konfigurasi WAN, WiFi, dan sandi akan kembali ke standar bawaan pabrik._"
        ), reply_markup=confirm_kb)
        return

    if act == "do_fr" and target:
        dev = find_device(target)
        if not dev:
            answer_callback(token, callback_id, f"Modem {target} tidak ditemukan!", show_alert=True)
            return
        ok, msg = factory_reset_device(dev)
        answer_callback(token, callback_id, "Sinyal Reset Terkirim", show_alert=False)
        send_telegram(token, sender_id, f"{'✅' if ok else '❌'} {msg}")
        return

    if act == "cancel_fr":
        answer_callback(token, callback_id, "Dibatalkan", show_alert=False)
        send_telegram(token, sender_id, "✅ Operasi Factory Reset dibatalkan.")
        return

    if act == "prompt_ssid" and target:
        answer_callback(token, callback_id, "Ganti Nama WiFi", show_alert=False)
        USER_STATES[sender_id] = {"action": "wait_ssid", "target": target}
        send_telegram(token, sender_id, (
            f"📶 *Ganti Nama WiFi untuk Pelanggan: `{target}`*\n"
            f"Silakan ketik nama WiFi baru yang Anda inginkan:\n"
            f"_(Bisa langsung ketik namanya saja atau gunakan `/ssid {target} <nama_baru>`)_"
        ))
        return

    if act == "prompt_pass" and target:
        answer_callback(token, callback_id, "Ganti Sandi WiFi", show_alert=False)
        USER_STATES[sender_id] = {"action": "wait_pass", "target": target}
        send_telegram(token, sender_id, (
            f"🔑 *Ganti Sandi WiFi untuk Pelanggan: `{target}`*\n"
            f"Silakan ketik sandi WiFi baru (minimal 8 karakter):\n"
            f"_(Bisa langsung ketik sandinya saja atau gunakan `/pass {target} <sandi_baru>`)_"
        ))
        return

    if act == "prompt_wan" and target:
        answer_callback(token, callback_id, "Set WAN PPPoE", show_alert=False)
        USER_STATES[sender_id] = {"action": "wait_wan", "target": target}
        send_telegram(token, sender_id, (
            f"🌐 *Set Koneksi WAN PPPoE untuk: `{target}`*\n\n"
            f"Silakan ketik data dengan format:\n"
            f"`<user_pppoe> <password_pppoe> [vlan_id]`\n\n"
            f"_Contoh tanpa VLAN:_ `{target} 12345678`\n"
            f"_Contoh dengan VLAN:_ `{target} 12345678 100`"
        ))
        return

def process_agent_command(user_text, sender_id="admin", is_admin=True, gemini_key="", gemini_model="gemini-1.5-flash", registered_tag=None):
    raw = str(user_text or "").strip()
    if not raw:
        return ("⚠️ Pesan kosong.", None)

    txt = raw
    clean_txt = txt.lstrip("/!#").strip()
    parts = clean_txt.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    # 0. Resolusi Modem Pelanggan dari Tag Nomor WhatsApp Pengirim
    customer_dev = None
    if not is_admin:
        if registered_tag:
            customer_dev = find_device(registered_tag)
        if not customer_dev and sender_id:
            customer_dev = find_device_by_phone(sender_id)
            if customer_dev:
                registered_tag = customer_dev.get("_id")

    # 1. Menu & Help
    if cmd in ["menu", "start", "bantuan", "help"]:
        if is_admin:
            menu_text = (
                f"🤖 *{BRAND_NAME} - GenieACS TR-069 AI Bot*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📌 *Daftar Perintah Admin:*\n"
                "• `cek <user_pppoe/sn>` ➔ Status lengkap & redaman ONT\n"
                "• `redaman` ➔ Audit massal redaman kritis (< -26 dBm)\n"
                "• `ontbaru` ➔ Cek modem baru belum tersetting\n"
                "• `klien <user>` ➔ Daftar HP/laptop terhubung WiFi\n"
                "• `reboot <user>` ➔ Restart modem pelanggan\n"
                "• `wifion <user>` & `wifioff <user>` ➔ On/Off Radio WiFi\n"
                "• `wifi <user> <ssid> <sandi>` ➔ Ubah WiFi & Sandi\n"
                "• `ssid <user> <nama>` ➔ Ubah nama WiFi\n"
                "• `pass <user> <sandi>` ➔ Ubah sandi WiFi\n"
                "• `addwan <sn> <user> <pass> [vlan]` ➔ Tambah/Set WAN PPPoE\n"
                "• `superadmin <user> <sandi>` ➔ Ubah sandi web ONT\n"
                "• `ping <user> [host]` ➔ Uji ping TR-069 jarak jauh\n"
                "• `factoryreset <user>` ➔ Reset setelan pabrik\n"
                "• `tag <user> <wa>` ➔ Tautkan nomor WA pelanggan ke modem\n• `untag <user> <wa>` ➔ Hapus nomor WA pelanggan dari modem\n• `server` / `status` ➔ Status CPU, RAM, Suhu STB\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👑 *CS: {BRAND_NAME} ({BRAND_PHONE})*"
            )
            return (menu_text, get_main_menu_keyboard())
        else:
            if customer_dev:
                pppoe_user = get_device_pppoe_username(customer_dev)
                cust_menu = (
                    f"👋 *Halo! Layanan Mandiri WiFi {BRAND_NAME}*\n"
                    f"Modem Terdeteksi: *{pppoe_user}*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Fitur yang dapat Anda gunakan:\n"
                    "• `cek` ➔ Cek nama WiFi, kata sandi & status sinyal\n"
                    "• `wifi <nama_baru> <sandi_baru>` ➔ Ganti nama WiFi & sandi sekaligus\n"
                    "• `pass <sandi_baru>` ➔ Ganti sandi WiFi saja (min. 8 karakter)\n"
                    "• `ssid <nama_baru>` ➔ Ganti nama WiFi saja\n"
                    "• `reboot` ➔ Restart modem jika koneksi internet terasa lambat\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📞 *Butuh Bantuan Teknisi?* Hubungi CS di {BRAND_PHONE}"
                )
            else:
                clean_s = normalize_phone(sender_id)
                cust_menu = (
                    f"👋 *Halo! Selamat Datang di Layanan Otomatis {BRAND_NAME}*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"Nomor WhatsApp Anda (*{clean_s or sender_id}*) belum terdaftar pada modem mana pun.\n\n"
                    "📝 *Cara Menghubungkan:*\n"
                    "Ketik: `daftar <id_pppoe>`\n"
                    "_Contoh:_ `daftar cucimotor`\n\n"
                    f"Atau hubungi Layanan Bantuan / CS di {BRAND_PHONE}."
                )
            return (cust_menu, None)

    # 2. Cek Redaman Kritis
    if cmd in ["redaman", "los"]:
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin / Teknisi.", None)
        return (get_bad_rx_summary(), get_main_menu_keyboard())

    # 3. Modem Belum Setting / ONT Baru
    if cmd in ["ontbaru", "unconf", "newont"]:
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin / Teknisi.", None)
        return (get_unconfigured_onts(), get_main_menu_keyboard())

    # 4. Cek Server Stats
    if cmd in ["server", "status"]:
        if not rest and is_admin:
            return (get_server_stats(), get_main_menu_keyboard())

    # 5. Cek Modem / ONT Status
    if cmd in ["cek", "info"]:
        target = rest
        if not target and registered_tag:
            target = registered_tag

        if not is_admin:
            dev_target = customer_dev or (find_device(target) if target else None)
            if not dev_target:
                return ("⚠️ Nomor WhatsApp Anda belum terhubung ke modem. Ketik `daftar <id_pppoe>` terlebih dahulu.", None)
            return (get_customer_friendly_summary(dev_target), None)

        if not target:
            return ("⚠️ Silakan sertakan Username PPPoE atau Serial Number.\n_Contoh:_ `cek cucimotor`", None)

        dev = find_device(target)
        if not dev:
            return (f"❌ Modem `{target}` tidak ditemukan di database GenieACS.", None)

        pppoe_user, summary_text, wifi_on = get_device_summary(dev)
        dev_id = dev.get("_id")
        kb = get_device_inline_keyboard(pppoe_user, dev_id, wifi_on)
        return (summary_text, kb)

    # 6. Klien WiFi Terhubung
    if cmd in ["klien", "client", "clients"]:
        target = rest or registered_tag
        if not target:
            return ("⚠️ Gunakan: `klien <username_pppoe/sn>`", None)
        dev = find_device(target)
        if not dev:
            return (f"❌ Modem `{target}` tidak ditemukan.", None)
        return (get_device_clients(dev), None)

    # 7. Reboot ONT
    if cmd in ["reboot", "restart"]:
        target = rest or registered_tag
        if not target:
            return ("⚠️ Gunakan: `reboot <username_pppoe/sn>`", None)
        dev = find_device(target)
        if not dev:
            return (f"❌ Modem `{target}` tidak ditemukan.", None)
        ok, msg = reboot_device_task(dev)
        if not is_admin and ok:
            p_name = get_device_pppoe_username(dev)
            return (
                f"🔄 *Perintah Restart Terkirim!*\n"
                f"Modem Anda (*{p_name}*) sedang memulai ulang (reboot).\n"
                f"Mohon tunggu sekitar 1-2 menit hingga lampu PON/Internet menyala stabil kembali.",
                None
            )
        return (f"{'✅' if ok else '❌'} {msg}", None)

    # 8. WiFi ON / OFF
    if cmd == "wifioff":
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin.", None)
        target = rest
        if not target:
            return ("⚠️ Gunakan: `wifioff <username/sn>`", None)
        dev = find_device(target)
        if not dev:
            return (f"❌ Modem `{target}` tidak ditemukan.", None)
        ok, msg = set_wifi_power(dev, enable=False)
        return (f"{'✅' if ok else '❌'} {msg}", None)

    if cmd == "wifion":
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin.", None)
        target = rest
        if not target:
            return ("⚠️ Gunakan: `wifion <username/sn>`", None)
        dev = find_device(target)
        if not dev:
            return (f"❌ Modem `{target}` tidak ditemukan.", None)
        ok, msg = set_wifi_power(dev, enable=True)
        return (f"{'✅' if ok else '❌'} {msg}", None)

    # 9. Ubah WiFi (SSID & Password)
    if cmd == "wifi":
        sub_parts = rest.split()
        if is_admin and len(sub_parts) >= 3:
            target, new_ssid, new_pass = sub_parts[0], sub_parts[1], sub_parts[2]
            dev = find_device(target)
            if not dev:
                return (f"❌ Modem `{target}` tidak ditemukan.", None)
            ok, msg = set_wifi_credentials(dev, new_ssid=new_ssid, new_password=new_pass)
            if ok:
                return (f"✅ *Berhasil Mengubah Pengaturan WiFi!*\n• Pelanggan: `{target}`\n• SSID: `{new_ssid}`\n• Sandi: `{new_pass}`\nStatus: Terkirim via TR-069.", None)
            return (f"❌ Gagal: {msg}", None)
        elif not is_admin:
            dev_target = customer_dev or (find_device(registered_tag) if registered_tag else None)
            if not dev_target:
                return ("⚠️ Nomor Anda belum terhubung ke modem mana pun. Ketik `daftar <id_pppoe>` terlebih dahulu.", None)
            if len(sub_parts) < 2:
                return ("⚠️ Format salah. Gunakan:\n`wifi <nama_wifi_baru> <sandi_baru>`\n_Contoh:_ `wifi MyHome SandiRahasia123`", None)
            new_ssid, new_pass = sub_parts[0], sub_parts[1]
            if len(new_pass) < 8:
                return ("⚠️ Kata sandi WiFi minimal harus 8 karakter demi keamanan WPA2-PSK.\n_Contoh:_ `wifi MyHome SandiRahasia123`", None)
            ok, msg = set_wifi_credentials(dev_target, new_ssid=new_ssid, new_password=new_pass)
            if ok:
                return (
                    f"✅ *WiFi Anda Berhasil Diperbarui!*\n"
                    f"• Nama WiFi Baru : *{new_ssid}*\n"
                    f"• Sandi Baru : *{new_pass}*\n\n"
                    f"Pengaturan telah dikirim ke modem. Silakan sambungkan kembali perangkat HP/Laptop Anda dengan kata sandi baru.",
                    None
                )
            return (f"❌ Gagal memperbarui WiFi: {msg}", None)
        else:
            if is_admin:
                return ("⚠️ Format salah. Gunakan:\n`wifi <user> <nama_wifi_baru> <sandi_baru>`\n_Contoh:_ `wifi cucimotor Alijaya-Net 12345678`", None)
            else:
                return ("⚠️ Format salah. Gunakan:\n`wifi <nama_wifi_baru> <sandi_baru>`\n_Contoh:_ `wifi WiFi-Saya SandiRahasia123`", None)

    # 10. Ubah SSID saja
    if cmd == "ssid":
        if is_admin:
            sub_parts = rest.split(maxsplit=1)
            if len(sub_parts) >= 2:
                target, new_ssid = sub_parts[0], sub_parts[1]
                dev = find_device(target)
                if not dev:
                    return (f"❌ Modem `{target}` tidak ditemukan.", None)
                ok, msg = set_wifi_credentials(dev, new_ssid=new_ssid)
                if ok:
                    return (f"✅ *Berhasil Mengubah SSID!*\n• Pelanggan: `{target}`\n• SSID Baru: `{new_ssid}`", None)
                return (f"❌ Gagal: {msg}", None)
            return ("⚠️ Gunakan: `ssid <username_pppoe> <nama_baru>`", None)
        else:
            dev_target = customer_dev or (find_device(registered_tag) if registered_tag else None)
            if not dev_target:
                return ("⚠️ Nomor Anda belum terhubung ke modem mana pun. Ketik `daftar <id_pppoe>` terlebih dahulu.", None)
            if not rest:
                return ("⚠️ Format salah. Gunakan:\n`ssid <nama_wifi_baru>`\n_Contoh:_ `ssid MyHome-WiFi`", None)
            new_ssid = rest.strip()
            ok, msg = set_wifi_credentials(dev_target, new_ssid=new_ssid)
            if ok:
                return (
                    f"✅ *Nama WiFi Berhasil Diubah!*\n"
                    f"• Nama WiFi Baru : *{new_ssid}*\n\n"
                    f"Pengaturan telah dikirim ke modem. Silakan sambungkan kembali perangkat HP Anda.",
                    None
                )
            return (f"❌ Gagal mengubah nama WiFi: {msg}", None)

    # 11. Ubah Password saja
    if cmd in ["pass", "password", "sandi"]:
        if is_admin:
            sub_parts = rest.split(maxsplit=1)
            if len(sub_parts) >= 2:
                target, new_pass = sub_parts[0], sub_parts[1]
                if len(new_pass) < 8:
                    return ("⚠️ Kata sandi minimal 8 karakter.", None)
                dev = find_device(target)
                if not dev:
                    return (f"❌ Modem `{target}` tidak ditemukan.", None)
                ok, msg = set_wifi_credentials(dev, new_password=new_pass)
                if ok:
                    return (f"✅ *Berhasil Mengubah Sandi WiFi!*\n• Pelanggan: `{target}`\n• Sandi Baru: `{new_pass}`", None)
                return (f"❌ Gagal: {msg}", None)
            return ("⚠️ Gunakan: `pass <username_pppoe> <sandi_baru>`", None)
        else:
            dev_target = customer_dev or (find_device(registered_tag) if registered_tag else None)
            if not dev_target:
                return ("⚠️ Nomor Anda belum terhubung ke modem mana pun. Ketik `daftar <id_pppoe>` terlebih dahulu.", None)
            if not rest:
                return ("⚠️ Format salah. Gunakan:\n`pass <sandi_baru>`\n_Contoh:_ `pass SandiRahasia123`", None)
            new_pass = rest.split()[0].strip()
            if len(new_pass) < 8:
                return ("⚠️ Kata sandi minimal harus 8 karakter demi keamanan WPA2-PSK.\n_Contoh:_ `pass SandiRahasia123`", None)
            ok, msg = set_wifi_credentials(dev_target, new_password=new_pass)
            if ok:
                return (
                    f"✅ *Kata Sandi WiFi Berhasil Diubah!*\n"
                    f"• Kata Sandi Baru : *{new_pass}*\n\n"
                    f"Pengaturan telah dikirim ke modem. Silakan sambungkan kembali perangkat HP/Laptop Anda dengan kata sandi baru.",
                    None
                )
            return (f"❌ Gagal mengubah kata sandi: {msg}", None)

    # 12. Add/Set WAN PPPoE
    if cmd == "addwan":
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin.", None)
        sub_parts = rest.split()
        if len(sub_parts) >= 3:
            target = sub_parts[0]
            pppoe_user = sub_parts[1]
            pppoe_pass = sub_parts[2]
            vlan_id = sub_parts[3] if len(sub_parts) > 3 else None
            dev = find_device(target)
            if not dev:
                return (f"❌ Modem `{target}` tidak ditemukan.", None)
            ok, msg = add_or_set_wan_pppoe(dev, pppoe_user, pppoe_pass, vlan_id)
            return (f"{'✅' if ok else '❌'} {msg}", None)
        return ("⚠️ Format salah. Gunakan:\n`addwan <sn/user> <user_pppoe> <pass_pppoe> [vlan_id]`", None)

    # 13. Superadmin Password
    if cmd == "superadmin":
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin.", None)
        sub_parts = rest.split(maxsplit=1)
        if len(sub_parts) >= 2:
            target, new_pass = sub_parts[0], sub_parts[1]
            dev = find_device(target)
            if not dev:
                return (f"❌ Modem `{target}` tidak ditemukan.", None)
            ok, msg = set_superadmin_password(dev, new_pass)
            return (f"{'✅' if ok else '❌'} {msg}", None)
        return ("⚠️ Gunakan: `superadmin <username/sn> <password_baru>`", None)

    # 14. Factory Reset
    if cmd == "factoryreset":
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin.", None)
        target = rest
        if not target:
            return ("⚠️ Gunakan: `factoryreset <username/sn>`", None)
        dev = find_device(target)
        if not dev:
            return (f"❌ Modem `{target}` tidak ditemukan.", None)
        ok, msg = factory_reset_device(dev)
        return (f"{'✅' if ok else '❌'} {msg}", None)

    # 15. Ping Diagnostics
    if cmd == "ping":
        sub_parts = rest.split()
        if sub_parts:
            target = sub_parts[0]
            host = sub_parts[1] if len(sub_parts) > 1 else "8.8.8.8"
            dev = find_device(target)
            if not dev:
                return (f"❌ Modem `{target}` tidak ditemukan.", None)
            ok, msg = ping_diagnostics_task(dev, host)
            return (f"{'✅' if ok else '❌'} {msg}", None)
        return ("⚠️ Gunakan: `ping <username/sn> [host]`", None)

    # 15.5. Tagging Nomor WhatsApp Pelanggan (Admin)
    if cmd == "tag":
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin.", None)
        sub_parts = rest.split()
        if len(sub_parts) < 2:
            return ("⚠️ Format salah. Gunakan:\n`tag <username_pppoe/sn> <nomor_wa>`\n_Contoh:_ `tag cucimotor 081234567890`", None)
        target_user, raw_phone = sub_parts[0], sub_parts[1]
        dev = find_device(target_user)
        if not dev:
            return (f"❌ Modem `{target_user}` tidak ditemukan.", None)
        clean_phone = normalize_phone(raw_phone)
        if len(clean_phone) < 8:
            return (f"⚠️ Nomor WhatsApp `{raw_phone}` tidak valid.", None)
        add_device_tag(dev["_id"], clean_phone)
        pppoe_name = get_device_pppoe_username(dev)
        return (
            f"✅ *Tag WhatsApp Berhasil Ditambahkan!*\n"
            f"• Pelanggan : `{pppoe_name}`\n"
            f"• Device ID : `{dev.get('_id')}`\n"
            f"• Nomor Tag : `{clean_phone}`\n\n"
            f"Pelanggan kini dapat langsung chat bot untuk cek status & ubah WiFi secara mandiri!",
            None
        )

    if cmd == "untag":
        if not is_admin:
            return ("⛔ Perintah ini khusus untuk Admin.", None)
        sub_parts = rest.split()
        if len(sub_parts) < 2:
            return ("⚠️ Format salah. Gunakan:\n`untag <username_pppoe/sn> <nomor_wa>`\n_Contoh:_ `untag cucimotor 081234567890`", None)
        target_user, raw_phone = sub_parts[0], sub_parts[1]
        dev = find_device(target_user)
        if not dev:
            return (f"❌ Modem `{target_user}` tidak ditemukan.", None)
        clean_phone = normalize_phone(raw_phone)
        remove_device_tag(dev["_id"], clean_phone)
        return (f"🗑️ Tag `{clean_phone}` berhasil dihapus dari modem `{target_user}`.", None)

    # 15.6. Pendaftaran Mandiri Pelanggan (Customer Self-Registration)
    if cmd == "daftar":
        if not rest:
            return ("⚠️ Format salah. Gunakan:\n`daftar <id_pppoe>`\n_Contoh:_ `daftar cucimotor`", None)
        target_user = rest.split()[0]
        dev = find_device(target_user)
        if not dev:
            return (f"❌ Pelanggan `{target_user}` tidak ditemukan di sistem GenieACS. Pastikan ID PPPoE Anda benar.", None)
        clean_phone = normalize_phone(sender_id)
        if clean_phone and len(clean_phone) >= 8:
            add_device_tag(dev["_id"], clean_phone)
        pppoe_name = get_device_pppoe_username(dev)
        return (
            f"✅ *Pendaftaran Layanan Mandiri Berhasil!*\n"
            f"Nomor WhatsApp Anda (*{clean_phone or sender_id}*) kini telah terhubung ke modem: *{pppoe_name}*.\n\n"
            f"Silakan gunakan perintah mandiri berikut kapan saja:\n"
            f"• `cek` ➔ Cek nama WiFi, kata sandi & status sinyal\n"
            f"• `wifi <nama_baru> <sandi_baru>` ➔ Ganti nama & sandi WiFi\n"
            f"• `pass <sandi_baru>` ➔ Ganti sandi WiFi saja (min. 8 karakter)\n"
            f"• `ssid <nama_baru>` ➔ Ganti nama WiFi saja\n"
            f"• `reboot` ➔ Restart modem jika koneksi lambat",
            None
        )

    # 16. Fallback Gemini AI / Percakapan Cerdas
    if gemini_key:
        ai_reply = ask_gemini_ai(gemini_key, gemini_model, raw, sender_id)
        return (ai_reply, None)

    # Default if not understood
    if is_admin:
        return (f"⚠️ Perintah `{raw}` tidak dikenali. Ketik `menu` untuk melihat daftar perintah.", get_main_menu_keyboard())
    else:
        return (f"👋 Halo! Nomor Anda belum terdaftar. Ketik `daftar <id_pelanggan>` untuk menghubungkan akun internet Anda.", None)


def handle_incoming_message(token, chat_id, user_text, gemini_key, model_name):
    txt = user_text.strip()
    state = USER_STATES.get(chat_id)

    # Menu Buttons Handlers khusus Telegram
    if txt in ["🔍 Cek Modem"]:
        USER_STATES[chat_id] = {"action": "wait_cek"}
        send_telegram(token, chat_id, "🔍 *Cek Modem*: Silakan ketik Username PPPoE atau Serial Number (contoh: `cucimotor`):")
        return

    if txt in ["⚠️ Cek Redaman Kritis", "/redaman", "/los"]:
        send_telegram(token, chat_id, get_bad_rx_summary(), reply_markup=get_main_menu_keyboard())
        return

    if txt in ["🆕 Modem Belum Setting", "/ontbaru", "/unconf"]:
        send_telegram(token, chat_id, get_unconfigured_onts(), reply_markup=get_main_menu_keyboard())
        return

    if txt in ["📊 Status Server", "/server", "/status"]:
        send_telegram(token, chat_id, get_server_stats(), reply_markup=get_main_menu_keyboard())
        return

    # Check conversation state jika user mengklik tombol Cek Modem
    if state and state.get("action") == "wait_cek":
        USER_STATES.pop(chat_id, None)
        dev = find_device(txt)
        if not dev:
            send_telegram(token, chat_id, f"❌ Modem `{txt}` tidak ditemukan di database GenieACS.", reply_markup=get_main_menu_keyboard())
            return
        pppoe_user, summary_text, wifi_on = get_device_summary(dev)
        dev_id = dev.get("_id")
        send_telegram(token, chat_id, summary_text, reply_markup=get_device_inline_keyboard(pppoe_user, dev_id, wifi_on))
        return

    # Jalankan perintah melalui unified command processor
    reply_text, markup = process_agent_command(
        user_text=txt,
        sender_id=chat_id,
        is_admin=True,
        gemini_key=gemini_key,
        gemini_model=model_name
    )
    send_telegram(token, chat_id, reply_text, reply_markup=markup or get_main_menu_keyboard())


def check_proactive_alerts(token, admin_ids):
    try:
        db = get_db()
        if db is None:
            return
            
        cursor = db.devices.find({"VirtualParameters.RXPower": {"$exists": True}})
        for d in cursor:
            vp = d.get("VirtualParameters", {})
            rx_dict = vp.get("RXPower", {})
            rx_val = rx_dict.get("_value") if isinstance(rx_dict, dict) else None
            
            if rx_val is None:
                continue
                
            try:
                rx_float = float(rx_val)
                dev_id = d.get("_id", "Unknown")
                pppoe = vp.get("pppoeUsername", {}).get("_value") if isinstance(vp.get("pppoeUsername"), dict) else dev_id
                
                if rx_float < -27.0 or rx_float > -8.0:
                    alert_key = f"{dev_id}_bad_rx"
                    last_alert = ALERT_HISTORY.get(alert_key, 0)
                    now = time.time()
                    
                    if (now - last_alert) > 3600:
                        ALERT_HISTORY[alert_key] = now
                        drop_msg = (
                            f"🚨 *[ALERT REDAMAN DROP KRITIS]*\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"• *Pelanggan*: `{pppoe.upper()}`\n"
                            f"• *Redaman Saat Ini*: `{rx_val} dBm` 🔴\n"
                            f"• *Penyebab*: Kemungkinan kabel optik terjepit, kotor, atau patchcord bermasalah.\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"👉 _Segera lakukan pengecekan fisik di lapangan._"
                        )
                        for aid in admin_ids:
                            send_telegram(token, aid, drop_msg)

                        # Kirim notifikasi ke WhatsApp Admin jika aktif
                        try:
                            cfgs = get_config()
                            wa_enabled = cfgs.get("agent.whatsapp.enabled", "true").lower() == "true"
                            wa_admins = cfgs.get("agent.whatsapp.admin_numbers", BRAND_PHONE)
                            if wa_enabled and wa_admins:
                                wa_list = [w.strip() for w in wa_admins.replace(";", ",").split(",") if w.strip()]
                                for wa_no in wa_list:
                                    requests.post("http://127.0.0.1:7559/send", json={"to": wa_no, "text": drop_msg}, timeout=2.0)
                        except Exception:
                            pass
            except Exception:
                pass
                
    except Exception as e:
        logger.error(f"Error in watchdog: {e}")


HTML_CONFIG_PAGE = """<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pengaturan Bot AI & WhatsApp - ALIJAYA NET</title>
  <style>
    :root {
      --bg: #0b1120;
      --card: #1e293b;
      --card-inner: #0f172a;
      --border: #334155;
      --primary: #06b6d4;
      --primary-hover: #0891b2;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 20px; display: flex; justify-content: center; }
    .container { width: 100%; max-width: 680px; background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
    .header { text-align: center; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }
    .header h2 { font-size: 1.45rem; color: var(--primary); display: flex; align-items: center; justify-content: center; gap: 8px; }
    .header p { color: var(--text-muted); font-size: 0.85rem; margin-top: 4px; }
    
    /* Tabs Navigation */
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    .tab-btn { flex: 1; padding: 10px 12px; background: transparent; border: 1px solid transparent; border-radius: 8px; color: var(--text-muted); font-weight: 600; font-size: 0.9rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 6px; }
    .tab-btn:hover { background: rgba(255,255,255,0.05); color: #fff; }
    .tab-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
    
    .tab-pane { display: none; }
    .tab-pane.active { display: block; animation: fadeIn 0.2s ease-in-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

    .form-group { margin-bottom: 16px; }
    label { display: block; font-size: 0.88rem; font-weight: 600; margin-bottom: 6px; color: var(--text); }
    .hint { font-size: 0.78rem; color: var(--text-muted); margin-top: 4px; line-height: 1.4; }
    input[type="text"], input[type="password"], select, textarea {
      width: 100%; padding: 10px 14px; background: var(--card-inner); border: 1px solid var(--border); border-radius: 8px; color: #fff; font-size: 0.92rem; outline: none; transition: border 0.2s;
    }
    input:focus, select:focus, textarea:focus { border-color: var(--primary); }
    textarea { resize: vertical; min-height: 60px; }

    /* WhatsApp Status Card */
    .status-card { background: var(--card-inner); border: 1px solid var(--border); border-radius: 10px; padding: 18px; margin-bottom: 18px; text-align: center; }
    .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 0.82rem; font-weight: 600; text-transform: uppercase; margin-bottom: 10px; }
    .badge-open { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid var(--success); }
    .badge-qr { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid var(--warning); }
    .badge-connecting { background: rgba(6, 182, 212, 0.2); color: #22d3ee; border: 1px solid var(--primary); }
    .badge-disconnected { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid var(--danger); }

    .qr-box { margin-top: 12px; }
    .qr-box img { width: 230px; height: 230px; background: #fff; padding: 8px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.6); }

    .btn-row { display: flex; gap: 12px; margin-top: 22px; }
    button { flex: 1; padding: 11px 16px; border: none; border-radius: 8px; font-weight: 600; font-size: 0.92rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
    .btn-save { background: var(--primary); color: #000; }
    .btn-save:hover { background: var(--primary-hover); }
    .btn-test { background: #334155; color: #fff; }
    .btn-test:hover { background: #475569; }
    .btn-logout { background: #7f1d1d; color: #fca5a5; border: 1px solid #ef4444; padding: 6px 14px; font-size: 0.85rem; border-radius: 6px; margin-top: 10px; display: inline-flex; }
    .btn-logout:hover { background: #991b1b; color: #fff; }
    .btn-reset-wa {
      background: #7f1d1d;
      color: #fca5a5;
      border: 1px solid #ef4444;
      padding: 9px 18px;
      font-size: 0.88rem;
      font-weight: 600;
      border-radius: 8px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .btn-reset-wa:hover {
      background: #991b1b;
      color: #fff;
      box-shadow: 0 0 10px rgba(239, 68, 68, 0.4);
    }

    .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 0.9rem; display: none; }
    .alert-success { background: rgba(16, 185, 129, 0.2); border: 1px solid var(--success); color: #34d399; }
    .alert-error { background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #f87171; }
    .back-link { display: inline-block; margin-top: 18px; text-decoration: none; color: var(--primary); font-size: 0.85rem; font-weight: 500; }
    .back-link:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2>🤖 Pengaturan Bot AI (Telegram & WhatsApp)</h2>
      <p>Panel Kontrol TR-069 GenieACS, Bot Telegram & Gateway WhatsApp Baileys</p>
    </div>

    <div id="alertBox" class="alert"></div>

    <div class="tabs">
      <button type="button" class="tab-btn active" onclick="switchTab('tab-wa')">📱 WhatsApp (Baileys)</button>
      <button type="button" class="tab-btn" onclick="switchTab('tab-tg')">✈️ Telegram Bot</button>
      <button type="button" class="tab-btn" onclick="switchTab('tab-brand')">🏢 Brand & AI</button>
    </div>

    <form id="botForm">
      <!-- TAB 1: WHATSAPP (BAILEYS) -->
      <div id="tab-wa" class="tab-pane active">
        <div class="status-card">
          <span id="waBadge" class="badge badge-connecting">MEMUAT STATUS...</span>
          
          <div id="waConnectedBox" style="display: none;">
            <p style="color: #34d399; font-weight: 600; font-size: 1.05rem;">✅ Bot WhatsApp Siap Digunakan</p>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 4px;">Akun: <b id="waUser" style="color: #fff;">-</b></p>
            <button type="button" class="btn-logout" onclick="logoutWA()">🔴 Putus Koneksi / Logout</button>
          </div>

          <div id="waQrBox" class="qr-box" style="display: none;">
            <p style="font-size: 0.88rem; color: #fbbf24; font-weight: 600; margin-bottom: 6px;">📷 Pindai Kode QR WhatsApp</p>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 12px;">Buka WhatsApp di HP ➔ <b>Perangkat Tertaut</b> ➔ <b>Tautkan Perangkat</b></p>
            <img id="waQrImg" src="" alt="WhatsApp QR Code" />
            <p style="font-size: 0.75rem; color: var(--primary); margin-top: 8px;">Auto-refresh aktif setiap 3 detik 🔄</p>
          </div>

          <div id="waOfflineBox" style="display: none;">
            <p style="color: #f87171; font-size: 0.88rem;">⚠️ Service WhatsApp belum aktif di port 7559.<br>Pastikan daemon <code>genieacs-whatsapp.service</code> sedang berjalan.</p>
          </div>

          <div class="session-actions" style="margin-top: 18px; border-top: 1px solid var(--border); padding-top: 14px; text-align: center;">
            <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px;">
              Ingin mengganti nomor bot WhatsApp baru atau membuat ulang QR Code?
            </p>
            <button type="button" class="btn-reset-wa" onclick="resetWA()">
              🗑️ Hapus Sesi WhatsApp (Ganti Nomor Bot / Buat QR Baru)
            </button>
          </div>
        </div>

        <div class="form-group">
          <label>Status Layanan Bot WhatsApp:</label>
          <select id="wa_enabled" name="wa_enabled">
            <option value="true">Aktif (Enabled) 🟢</option>
            <option value="false">Nonaktif (Disabled) 🔴</option>
          </select>
        </div>

        <div class="form-group">
          <label>Nomor WhatsApp Admin / Teknisi:</label>
          <textarea id="wa_admin_numbers" name="wa_admin_numbers" placeholder="Contoh: 081947215703, 081234567890"></textarea>
          <div class="hint">Nomor yang memiliki hak akses perintah administratif (cek, redaman, reboot, wifion/off, ssid, dll). Pisahkan koma jika lebih dari satu.</div>
        </div>
      </div>

      <!-- TAB 2: TELEGRAM BOT -->
      <div id="tab-tg" class="tab-pane">
        <div class="form-group">
          <label>Status Layanan Bot Telegram:</label>
          <select id="bot_enabled" name="enabled">
            <option value="true">Aktif (Enabled) 🟢</option>
            <option value="false">Nonaktif (Disabled) 🔴</option>
          </select>
        </div>

        <div class="form-group">
          <label>Token Bot Telegram:</label>
          <input type="text" id="bot_token" name="token" placeholder="Contoh: 123456789:AAFMD7X_xxxxxxxxxxxxxx">
          <div class="hint">Dapatkan dari @BotFather di Telegram.</div>
        </div>

        <div class="form-group">
          <label>Admin Chat ID / ID Grup Telegram:</label>
          <input type="text" id="admin_id" name="admin_id" placeholder="Contoh: 567858628 atau 567858628, -100987654321">
          <div class="hint">Dapatkan ID Anda dari @userinfobot. Bisa isi beberapa ID dipisah koma.</div>
        </div>

        <div style="margin-top: 14px;">
          <button type="button" id="btnTest" class="btn-test">🧪 Tes Kirim Pesan Telegram</button>
        </div>
      </div>

      <!-- TAB 3: BRANDING & AI -->
      <div id="tab-brand" class="tab-pane">
        <div class="form-group">
          <label>Nama Brand / ISP / RT-RW Net:</label>
          <input type="text" id="brand_name" name="brand_name" placeholder="ALIJAYA NET">
          <div class="hint">Nama usaha yang akan tampil pada header pesan Telegram & WhatsApp.</div>
        </div>

        <div class="form-group">
          <label>Nomor Telepon / WhatsApp Customer Service:</label>
          <input type="text" id="brand_phone" name="brand_phone" placeholder="081947215703">
          <div class="hint">Nomor kontak layanan bantuan pada footer pesan.</div>
        </div>

        <div class="form-group">
          <label>Google Gemini API Key (Opsional):</label>
          <input type="password" id="gemini_key" name="gemini_key" placeholder="AIzaSyDxxxxxxxxxxxxxxxxxxxx">
          <div class="hint">Untuk asisten AI percakapan cerdas. Kosongkan jika tidak memakai.</div>
        </div>
      </div>

      <div class="btn-row">
        <button type="submit" class="btn-save">💾 Simpan Semua Pengaturan</button>
      </div>
    </form>

    <div style="text-align: center;">
      <a href="/" class="back-link" id="backToAcs">⬅️ Kembali ke Dashboard GenieACS</a>
    </div>
  </div>

  <script>
    document.getElementById('backToAcs').href = window.location.protocol + '//' + window.location.hostname + ':3000';

    function switchTab(tabId) {
      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      document.getElementById(tabId).classList.add('active');
      event.currentTarget.classList.add('active');
    }

    function showAlert(msg, isSuccess) {
      const box = document.getElementById('alertBox');
      box.textContent = msg;
      box.className = 'alert ' + (isSuccess ? 'alert-success' : 'alert-error');
      box.style.display = 'block';
      box.scrollIntoView({ behavior: 'smooth' });
    }

    // Load initial config
    fetch('/api/config')
      .then(r => r.json())
      .then(data => {
        document.getElementById('bot_enabled').value = data.enabled || 'true';
        document.getElementById('bot_token').value = data.token || '';
        document.getElementById('admin_id').value = data.admin_id || '';
        document.getElementById('brand_name').value = data.brand_name || 'ALIJAYA NET';
        document.getElementById('brand_phone').value = data.brand_phone || '081947215703';
        document.getElementById('gemini_key').value = data.gemini_key || '';
        document.getElementById('wa_enabled').value = data.wa_enabled || 'true';
        document.getElementById('wa_admin_numbers').value = data.wa_admin_numbers || data.brand_phone || '081947215703';
      })
      .catch(e => console.error(e));

    // WhatsApp Live Status Polling
    function pollWhatsAppStatus() {
      fetch('/api/whatsapp/status')
        .then(r => r.json())
        .then(st => {
          const badge = document.getElementById('waBadge');
          const connBox = document.getElementById('waConnectedBox');
          const qrBox = document.getElementById('waQrBox');
          const offBox = document.getElementById('waOfflineBox');
          const qrImg = document.getElementById('waQrImg');
          const waUser = document.getElementById('waUser');

          if (!st || st.connection === 'disconnected' || st.error) {
            badge.className = 'badge badge-disconnected';
            badge.textContent = 'TERPUTUS / OFFLINE';
            connBox.style.display = 'none';
            qrBox.style.display = 'none';
            offBox.style.display = 'block';
          } else if (st.connection === 'open') {
            badge.className = 'badge badge-open';
            badge.textContent = 'TERHUBUNG (CONNECTED) 🟢';
            const userStr = st.user ? (st.user.id || st.user.name || 'Bot Terhubung') : 'Aktif';
            waUser.textContent = userStr.replace(':1@s.whatsapp.net', '').replace('@s.whatsapp.net', '');
            connBox.style.display = 'block';
            qrBox.style.display = 'none';
            offBox.style.display = 'none';
          } else if (st.qrImage || st.qr || st.connection === 'qr') {
            badge.className = 'badge badge-qr';
            badge.textContent = 'MENUNGGU PINDAI QR 🟡';
            qrImg.src = st.qrImage;
            qrBox.style.display = 'block';
            connBox.style.display = 'none';
            offBox.style.display = 'none';
          } else if (st.connection === 'connecting') {
            badge.className = 'badge badge-connecting';
            badge.textContent = 'MENGHUBUNGKAN... ⏳';
            connBox.style.display = 'none';
            qrBox.style.display = 'none';
            offBox.style.display = 'none';
          } else {
            badge.className = 'badge badge-disconnected';
            badge.textContent = (st.connection || 'LOGGED OUT').toUpperCase();
            connBox.style.display = 'none';
            qrBox.style.display = 'none';
            offBox.style.display = 'none';
          }
        })
        .catch(() => {
          const badge = document.getElementById('waBadge');
          badge.className = 'badge badge-disconnected';
          badge.textContent = 'OFFLINE';
        });
    }

    pollWhatsAppStatus();
    setInterval(pollWhatsAppStatus, 3000);

    function resetWA() {
      if (!confirm('Apakah Anda yakin ingin MENGHAPUS SESI WHATSAPP? Data sesi login lama akan dibersihkan agar Anda dapat mengganti nomor WhatsApp bot baru.')) {
        return;
      }
      const badge = document.getElementById('waBadge');
      badge.className = 'badge badge-connecting';
      badge.textContent = 'MENGHAPUS SESI & RESET... ⏳';

      fetch('/api/whatsapp/reset', { method: 'POST' })
        .then(r => r.json())
        .then(res => {
          showAlert('✅ Sesi WhatsApp lama berhasil dihapus! Menyiapkan QR Code baru...', true);
          setTimeout(pollWhatsAppStatus, 1500);
        })
        .catch(err => showAlert('❌ Gagal menghapus sesi: ' + err.message, false));
    }

    function logoutWA() {
      resetWA();
    }

    // Save Form Handler
    document.getElementById('botForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const payload = {
        enabled: document.getElementById('bot_enabled').value,
        token: document.getElementById('bot_token').value,
        admin_id: document.getElementById('admin_id').value,
        brand_name: document.getElementById('brand_name').value,
        brand_phone: document.getElementById('brand_phone').value,
        gemini_key: document.getElementById('gemini_key').value,
        wa_enabled: document.getElementById('wa_enabled').value,
        wa_admin_numbers: document.getElementById('wa_admin_numbers').value
      };

      fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(r => r.json())
      .then(res => {
        if (res.success) {
          showAlert('✅ Konfigurasi bot berhasil disimpan dan langsung diterapkan!', true);
        } else {
          showAlert('❌ Gagal menyimpan: ' + (res.message || 'Error MongoDB'), false);
        }
      })
      .catch(err => showAlert('❌ Gagal menghubungi server: ' + err.message, false));
    });

    // Test Telegram Handler
    document.getElementById('btnTest').addEventListener('click', function() {
      const token = document.getElementById('bot_token').value;
      const admin_id = document.getElementById('admin_id').value;
      if (!token || !admin_id) {
        showAlert('Token Telegram dan Admin Chat ID harus diisi untuk pengujian!', false);
        return;
      }
      this.textContent = '⏳ Mengirim...';
      this.disabled = true;

      fetch('/api/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token, admin_id: admin_id })
      })
      .then(r => r.json())
      .then(res => {
        if (res.success) {
          showAlert('✅ Notifikasi tes berhasil terkirim ke Telegram Anda!', true);
        } else {
          showAlert('❌ Gagal mengirim tes: ' + (res.message || 'Periksa token & chat ID'), false);
        }
      })
      .catch(err => showAlert('❌ Error: ' + err.message, false))
      .finally(() => {
        this.textContent = '🧪 Tes Kirim Pesan Telegram';
        this.disabled = false;
      });
    });
  </script>
</body>
</html>
"""


class BotConfigHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONFIG_PAGE.encode("utf-8"))
        elif self.path == "/api/config":
            cfgs = get_config()
            data = {
                "enabled": cfgs.get("agent.enabled", "true"),
                "token": cfgs.get("agent.telegram.botToken", ""),
                "admin_id": cfgs.get("agent.telegram.adminChatId", ""),
                "brand_name": cfgs.get("agent.brand.name", BRAND_NAME),
                "brand_phone": cfgs.get("agent.brand.phone", BRAND_PHONE),
                "gemini_key": cfgs.get("agent.gemini.apiKey", ""),
                "wa_enabled": cfgs.get("agent.whatsapp.enabled", "true"),
                "wa_admin_numbers": cfgs.get("agent.whatsapp.admin_numbers", cfgs.get("agent.brand.phone", BRAND_PHONE))
            }
            self.send_json(data)
        elif self.path == "/api/whatsapp/status":
            try:
                r = requests.get("http://127.0.0.1:7559/status", timeout=5.0)
                self.send_json(r.json())
            except Exception as e:
                self.send_json({"connection": "disconnected", "error": str(e)})
        elif self.path == "/api/whatsapp/lid_mappings":
            try:
                r = requests.get("http://127.0.0.1:7559/lid_mappings", timeout=2.5)
                self.send_json(r.json())
            except Exception as e:
                self.send_json({"error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            req = json.loads(body)
        except Exception:
            req = {}

        if self.path == "/api/config":
            db = get_db()
            if db is None:
                self.send_json({"success": False, "message": "Gagal terhubung ke MongoDB"})
                return

            configs_to_save = {
                "agent.enabled": req.get("enabled", "true"),
                "agent.telegram.botToken": f'"{req.get("token", "").strip()}"',
                "agent.telegram.adminChatId": f'"{req.get("admin_id", "").strip()}"',
                "agent.brand.name": f'"{req.get("brand_name", BRAND_NAME).strip()}"',
                "agent.brand.phone": f'"{req.get("brand_phone", BRAND_PHONE).strip()}"',
                "agent.gemini.apiKey": f'"{req.get("gemini_key", "").strip()}"',
                "agent.whatsapp.enabled": f'"{req.get("wa_enabled", "true").strip()}"',
                "agent.whatsapp.admin_numbers": f'"{req.get("wa_admin_numbers", BRAND_PHONE).strip()}"'
            }

            for k, v in configs_to_save.items():
                db.config.update_one({"_id": k}, {"$set": {"value": v}}, upsert=True)

            # Notifikasi reload ke service WhatsApp
            try:
                requests.post("http://127.0.0.1:7559/reload_admins", timeout=1.0)
            except Exception:
                pass

            logger.info("Konfigurasi bot berhasil disimpan melalui Web UI (Port 7558)!")
            self.send_json({"success": True, "message": "Konfigurasi berhasil disimpan"})

        elif self.path in ["/api/whatsapp/logout", "/api/whatsapp/reset"]:
            try:
                requests.post("http://127.0.0.1:7559/logout", timeout=4.0)
            except Exception:
                pass

            auth_dirs = [
                "/opt/genieacs-agent/auth_info_baileys",
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_info_baileys")
            ]
            for ad in auth_dirs:
                if os.path.exists(ad):
                    try:
                        import shutil
                        shutil.rmtree(ad, ignore_errors=True)
                    except Exception:
                        pass

            try:
                import subprocess
                subprocess.run(["systemctl", "restart", "genieacs-whatsapp.service"], check=False)
            except Exception:
                pass

            self.send_json({"success": True, "message": "Sesi WhatsApp berhasil dihapus dan bot direset"})

        elif self.path == "/api/agent_command":
            text = req.get("text", "")
            sender = req.get("sender", "anonymous")
            is_admin = bool(req.get("isAdmin", False))
            push_name = req.get("pushName", "")
            reg_tag = req.get("registeredTag", None)

            cfgs = get_config()
            gemini_key = cfgs.get("agent.gemini.apiKey", "")
            gemini_model = cfgs.get("agent.gemini.model", "gemini-1.5-flash")

            try:
                reply_text, _ = process_agent_command(
                    user_text=text,
                    sender_id=sender,
                    is_admin=is_admin,
                    gemini_key=gemini_key,
                    gemini_model=gemini_model,
                    registered_tag=reg_tag
                )
                self.send_json({"success": True, "reply": reply_text})
            except Exception as e:
                logger.error(f"Error handling agent_command '{text}': {e}", exc_info=True)
                self.send_json({"success": False, "reply": f"⚠️ Terjadi error internal saat memproses perintah `{text}`: {e}"})

        elif self.path == "/api/test":
            token = req.get("token", "").strip()
            admin_id = req.get("admin_id", "").strip()
            if not token or not admin_id:
                self.send_json({"success": False, "message": "Token dan Chat ID tidak boleh kosong!"})
                return

            ids = parse_admin_chat_ids(admin_id)
            test_msg = f"🧪 *Tes Notifikasi Bot GenieACS*\n━━━━━━━━━━━━━━━━━━━━\nKoneksi berhasil! Bot siap digunakan ({BRAND_NAME})."
            success_count = 0
            err_msg = ""
            for aid in ids:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                try:
                    r = requests.post(url, json={"chat_id": aid, "text": test_msg, "parse_mode": "Markdown"}, timeout=8)
                    if r.status_code == 200:
                        success_count += 1
                    else:
                        err_msg = r.text
                except Exception as e:
                    err_msg = str(e)

            if success_count > 0:
                self.send_json({"success": True})
            else:
                self.send_json({"success": False, "message": err_msg})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, *args):
        pass


def start_web_server(port=7558):
    try:
        server = DefaultHTTPServer(("0.0.0.0", port), BotConfigHandler)
        logger.info(f"Bot Web Config UI berjalan di http://0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Gagal menjalankan Bot Web Config server di port {port}: {e}")

def main():
    logger.info("Starting ALIJAYA NET GenieACS AI Agent Service...")
    web_thread = threading.Thread(target=start_web_server, args=(7558,), daemon=True)
    web_thread.start()
    last_update_id = 0
    notified_online = False
    last_watchdog_time = 0
    
    while True:
        try:
            cfgs = get_config()
            update_branding(cfgs)
            enabled = cfgs.get("agent.enabled", "true").lower() == "true"
            token = cfgs.get("agent.telegram.botToken", "")
            admin_cfg_str = cfgs.get("agent.telegram.adminChatId", "")
            admin_ids = parse_admin_chat_ids(admin_cfg_str)
            gemini_key = cfgs.get("agent.gemini.apiKey", "")
            gemini_model = cfgs.get("agent.gemini.model", "gemini-1.5-flash")
            
            if not enabled:
                logger.info("Agent is disabled in config (agent.enabled=false). Sleeping...")
                time.sleep(30)
                continue
                
            if not is_valid_token(token):
                logger.info("Menunggu konfigurasi token Telegram di GenieACS Web UI (Admin -> Config)...")
                time.sleep(15)
                continue
                
            if not notified_online:
                register_bot_commands(token)
                greeting = (
                    f"🚀 *{BRAND_NAME} GenieACS Bot Aktif!*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Menu interaktif, audit redaman, deteksi ONT baru & kontrol TR-069 siap melayani.\n"
                    "Ketik `/menu` atau klik tombol di bawah untuk mulai."
                )
                for aid in admin_ids:
                    send_telegram(token, aid, greeting, reply_markup=get_main_menu_keyboard())
                notified_online = True
                logger.info(f"Bot Telegram berhasil terhubung dan siap melayani ({BRAND_NAME})!")

            # Periodic Watchdog (setiap 60 detik)
            now = time.time()
            if (now - last_watchdog_time) >= 60:
                check_proactive_alerts(token, admin_ids)
                last_watchdog_time = now

            # Poll Telegram Updates
            poll_url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id + 1}&timeout=15"
            r = requests.get(poll_url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                for upd in data.get("result", []):
                    last_update_id = upd.get("update_id", last_update_id)
                    
                    cb = upd.get("callback_query")
                    if cb:
                        cb_id = cb.get("id")
                        cb_sender = str(cb.get("from", {}).get("id", ""))
                        cb_data = cb.get("data", "")
                        if admin_ids and not is_authorized(cb_sender, admin_ids):
                            answer_callback(token, cb_id, f"Akses ditolak! Bukan Admin/Teknisi {BRAND_NAME}.", show_alert=True)
                            continue
                        handle_callback_query(token, cb_sender, cb_data, cb_id)
                        continue

                    msg = upd.get("message", {})
                    chat = msg.get("chat", {})
                    sender_id = str(chat.get("id", ""))
                    text = msg.get("text", "")
                    
                    if admin_ids and not is_authorized(sender_id, admin_ids):
                        logger.warning(f"Unauthorized chat from {sender_id}: {text}")
                        send_telegram(token, sender_id, f"⛔ Akses Ditolak: ID Anda ({sender_id}) bukan Admin/Teknisi {BRAND_NAME}.")
                        continue
                        
                    if text:
                        logger.info(f"Received command: '{text}' from {sender_id}")
                        handle_incoming_message(token, sender_id, text, gemini_key, gemini_model)
            else:
                logger.warning(f"Telegram polling returned HTTP {r.status_code}")
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Agent loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
