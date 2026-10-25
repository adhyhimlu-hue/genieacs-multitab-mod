#!/usr/bin/env python3
# ==============================================================================
# ALIJAYA NET - GenieACS AI Telegram Agent (Full Multi-Tab & Operations Mod)
# Pengembang: ALIJAYA NET (WhatsApp: 081947215703)
# ==============================================================================

import time
import json
import logging
import subprocess
import requests
import pymongo
from urllib.parse import quote

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

def find_device(query_str):
    db = get_db()
    if db is None:
        return None
    q = query_str.strip()
    reg = {"$regex": q, "$options": "i"}

    dev = db.devices.find_one({
        "$or": [
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

def handle_incoming_message(token, chat_id, user_text, gemini_key, model_name):
    txt = user_text.strip()
    state = USER_STATES.get(chat_id)

    # 1. Menu Buttons Handlers
    if txt in ["/start", "/menu", "❓ Bantuan / Help", "/help"]:
        USER_STATES.pop(chat_id, None)
        welcome = (
            f"🤖 *{BRAND_NAME} - GenieACS TR-069 AI Bot*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Gunakan tombol menu di bawah untuk aksi cepat, atau ketik perintah langsung:\n\n"
            "📌 *Daftar Perintah Lengkap:*\n"
            "• `/cek <user_atau_sn>` ➔ Rincian detail & redaman ONT\n"
            "• `/redaman` ➔ Audit massal redaman kritis (< -26 dBm)\n"
            "• `/ontbaru` ➔ Cek modem baru belum disetting\n"
            "• `/klien <user>` ➔ Daftar HP/laptop terkoneksi ke WiFi\n"
            "• `/addwan <sn> <user> <pass> [vlan]` ➔ Tambah/Set WAN\n"
            "• `/wifioff <user>` & `/wifion <user>` ➔ On/Off Radio WiFi\n"
            "• `/ssid <user> <nama>` ➔ Ubah nama WiFi\n"
            "• `/pass <user> <sandi>` ➔ Ubah sandi WiFi\n"
            "• `/wifi <user> <ssid> <sandi>` ➔ Ubah WiFi & Sandi\n"
            "• `/ping <user> [host]` ➔ Tes Ping TR-069 jarak jauh\n"
            "• `/superadmin <user> <sandi>` ➔ Ubah sandi web ONT\n"
            "• `/reboot <user>` ➔ Restart modem pelanggan\n"
            "• `/factoryreset <user>` ➔ Reset setelan pabrik\n"
            "• `/server` ➔ Status CPU, RAM, Suhu STB\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 *Pengembang / CS: {BRAND_NAME} ({BRAND_PHONE})*"
        )
        send_telegram(token, chat_id, welcome, reply_markup=get_main_menu_keyboard())
        return

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

    if txt in ["👥 Daftar Klien WiFi"]:
        USER_STATES[chat_id] = {"action": "wait_klien"}
        send_telegram(token, chat_id, "👥 *Cek Klien*: Silakan ketik Username PPPoE atau Serial Number untuk melihat daftar HP terhubung:")
        return

    if txt == "🔄 Reboot Modem":
        USER_STATES[chat_id] = {"action": "wait_reboot"}
        send_telegram(token, chat_id, "🔄 *Reboot Modem*: Silakan ketik Username PPPoE atau Serial Number (contoh: `cucimotor`):")
        return

    if txt == "🌐 Tambah / Set WAN":
        send_telegram(token, chat_id, (
            "🌐 *Tambah / Set Koneksi WAN PPPoE*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Format:\n"
            "`/addwan <SN_atau_User> <User_PPPoE> <Pass_PPPoE> [VLAN_ID]`\n\n"
            "_Contoh Tanpa VLAN:_\n"
            "`/addwan CIOT157197A8 budi01 12345678`\n\n"
            "_Contoh Dengan VLAN:_\n"
            "`/addwan CIOT157197A8 budi01 12345678 100`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "*(Bisa gunakan Serial Number modem baru atau Username yang sudah ada)*"
        ))
        return

    if txt == "📶 Ubah WiFi / Sandi":
        send_telegram(token, chat_id, (
            "📶 *Ubah Nama & Sandi WiFi*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• Ganti SSID saja: `/ssid <user> <nama_baru>`\n"
            "• Ganti Sandi saja: `/pass <user> <sandi_baru>`\n"
            "• Ganti Keduanya : `/wifi <user> <ssid_baru> <sandi_baru>`\n"
            "• On/Off Pemancar: `/wifioff <user>` atau `/wifion <user>`"
        ))
        return

    if txt in ["📊 Status Server STB", "/server"]:
        send_telegram(token, chat_id, get_server_stats(), reply_markup=get_main_menu_keyboard())
        return

    # 2. State-Based Replies (Conversational context)
    if state:
        st_act = state.get("action")
        target = state.get("target")

        if st_act == "wait_cek":
            USER_STATES.pop(chat_id, None)
            dev = find_device(txt)
            pppoe, summary, wifi_on = get_device_summary(dev)
            kb = get_device_inline_keyboard(pppoe, dev.get("_id") if dev else None, wifi_on) if dev else None
            send_telegram(token, chat_id, summary, reply_markup=kb)
            return

        if st_act == "wait_klien":
            USER_STATES.pop(chat_id, None)
            dev = find_device(txt)
            send_telegram(token, chat_id, get_device_clients(dev))
            return

        if st_act == "wait_reboot":
            USER_STATES.pop(chat_id, None)
            dev = find_device(txt)
            if not dev:
                send_telegram(token, chat_id, f"❌ Modem `{txt}` tidak ditemukan.")
                return
            ok, msg = reboot_device_task(dev)
            send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}")
            return

        if st_act == "wait_ssid" and target:
            USER_STATES.pop(chat_id, None)
            dev = find_device(target)
            new_ssid = txt.replace(f"/ssid {target}", "").strip()
            ok, msg = set_wifi_credentials(dev, new_ssid=new_ssid)
            if ok:
                send_telegram(token, chat_id, (
                    f"✅ *Nama WiFi Berhasil Diubah!*\n"
                    f"• *Pelanggan*: `{target}`\n"
                    f"• *SSID Baru*: `{new_ssid}`\n"
                    f"• *Status*: Terkirim ke modem via TR-069."
                ))
            else:
                send_telegram(token, chat_id, f"❌ Gagal: {msg}")
            return

        if st_act == "wait_pass" and target:
            USER_STATES.pop(chat_id, None)
            dev = find_device(target)
            new_pass = txt.replace(f"/pass {target}", "").strip()
            ok, msg = set_wifi_credentials(dev, new_password=new_pass)
            if ok:
                send_telegram(token, chat_id, (
                    f"✅ *Sandi WiFi Berhasil Diubah!*\n"
                    f"• *Pelanggan*: `{target}`\n"
                    f"• *Sandi Baru*: `{new_pass}`\n"
                    f"• *Status*: Terkirim ke modem via TR-069."
                ))
            else:
                send_telegram(token, chat_id, f"❌ Gagal: {msg}")
            return

        if st_act == "wait_wan" and target:
            USER_STATES.pop(chat_id, None)
            parts = txt.split()
            if len(parts) >= 2:
                u = parts[0]
                p = parts[1]
                vlan = parts[2] if len(parts) >= 3 else None
                dev = find_device(target)
                ok, msg = add_or_set_wan_pppoe(dev, u, p, vlan)
                send_telegram(token, chat_id, msg)
            else:
                send_telegram(token, chat_id, "⚠️ Format salah. Minimal masukkan: `<username> <password>`")
            return

    # 3. Direct Command Fast-Path
    if txt.startswith("/addwan "):
        parts = txt[8:].strip().split()
        if len(parts) >= 3:
            target = parts[0]
            pppoe_user = parts[1]
            pppoe_pass = parts[2]
            vlan_id = parts[3] if len(parts) >= 4 else None
            
            dev = find_device(target)
            if not dev:
                send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan. Pastikan SN atau Username benar.")
                return
            ok, msg = add_or_set_wan_pppoe(dev, pppoe_user, pppoe_pass, vlan_id)
            send_telegram(token, chat_id, msg)
            return
        else:
            send_telegram(token, chat_id, (
                "⚠️ Format salah. Gunakan:\n"
                "`/addwan <SN_atau_User> <User_PPPoE> <Pass_PPPoE> [VLAN_ID]`\n\n"
                "_Contoh:_\n`/addwan CIOT157197A8 budi01 12345678 100`"
            ))
            return

    if txt.startswith("/cek "):
        target = txt[5:].strip()
        dev = find_device(target)
        pppoe, summary, wifi_on = get_device_summary(dev)
        kb = get_device_inline_keyboard(pppoe, dev.get("_id") if dev else None, wifi_on) if dev else None
        send_telegram(token, chat_id, summary, reply_markup=kb)
        return

    if txt.startswith("/klien ") or txt.startswith("/hosts "):
        target = txt.split(maxsplit=1)[1].strip()
        dev = find_device(target)
        send_telegram(token, chat_id, get_device_clients(dev))
        return

    if txt.startswith("/wifioff "):
        target = txt[9:].strip()
        dev = find_device(target)
        if not dev:
            send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan.")
            return
        ok, msg = set_wifi_power(dev, enable=False)
        send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}")
        return

    if txt.startswith("/wifion "):
        target = txt[8:].strip()
        dev = find_device(target)
        if not dev:
            send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan.")
            return
        ok, msg = set_wifi_power(dev, enable=True)
        send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}")
        return

    if txt.startswith("/ping "):
        parts = txt[6:].strip().split()
        if parts:
            target = parts[0].strip()
            host = parts[1].strip() if len(parts) > 1 else "8.8.8.8"
            dev = find_device(target)
            if not dev:
                send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan.")
                return
            ok, msg = ping_diagnostics_task(dev, host)
            send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}")
            return
        else:
            send_telegram(token, chat_id, "⚠️ Format salah. Gunakan: `/ping <username/sn> [host]`\n_Contoh:_ `/ping cucimotor 8.8.8.8`")
            return

    if txt.startswith("/superadmin "):
        parts = txt[12:].strip().split(maxsplit=1)
        if len(parts) >= 2:
            target, new_pass = parts[0].strip(), parts[1].strip()
            dev = find_device(target)
            if not dev:
                send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan.")
                return
            ok, msg = set_superadmin_password(dev, new_pass)
            send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}")
            return
        else:
            send_telegram(token, chat_id, "⚠️ Format salah. Gunakan:\n`/superadmin <username/sn> <password_baru>`")
            return

    if txt.startswith("/factoryreset "):
        target = txt[14:].strip()
        dev = find_device(target)
        if not dev:
            send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan.")
            return
        confirm_kb = {
            "inline_keyboard": [
                [
                    {"text": "⚠️ Ya, Reset Pabrik", "callback_data": f"do_fr:{target}"},
                    {"text": "❌ Batal", "callback_data": "cancel_fr"}
                ]
            ]
        }
        send_telegram(token, chat_id, (
            f"⚠️ *KONFIRMASI FACTORY RESET*\n"
            f"Apakah Anda yakin ingin mereset modem pelanggan `{target}` ke setelan pabrik?\n"
            f"_Seluruh konfigurasi WAN, WiFi, dan sandi akan kembali ke standar bawaan pabrik._"
        ), reply_markup=confirm_kb)
        return

    if txt.startswith("/ssid "):
        parts = txt[6:].strip().split(maxsplit=1)
        if len(parts) >= 2:
            target, new_ssid = parts[0].strip(), parts[1].strip()
            dev = find_device(target)
            if not dev:
                send_telegram(token, chat_id, f"❌ Modem pelanggan `{target}` tidak ditemukan.")
                return
            ok, msg = set_wifi_credentials(dev, new_ssid=new_ssid)
            if ok:
                send_telegram(token, chat_id, (
                    f"✅ *Berhasil Mengubah Nama WiFi (SSID)!*\n"
                    f"• *Pelanggan*: `{target}`\n"
                    f"• *Nama WiFi Baru*: `{new_ssid}`\n"
                    f"• *Status*: Terkirim ke modem via TR-069."
                ))
            else:
                send_telegram(token, chat_id, f"❌ Gagal: {msg}")
            return
        else:
            send_telegram(token, chat_id, "⚠️ Format salah. Gunakan:\n`/ssid <username_pppoe> <nama_wifi_baru>`\n_Contoh:_ `/ssid cucimotor Cuci Motor Baru`")
            return

    if txt.startswith("/pass "):
        parts = txt[6:].strip().split(maxsplit=1)
        if len(parts) >= 2:
            target, new_pass = parts[0].strip(), parts[1].strip()
            dev = find_device(target)
            if not dev:
                send_telegram(token, chat_id, f"❌ Modem pelanggan `{target}` tidak ditemukan.")
                return
            ok, msg = set_wifi_credentials(dev, new_password=new_pass)
            if ok:
                send_telegram(token, chat_id, (
                    f"✅ *Berhasil Mengubah Sandi WiFi!*\n"
                    f"• *Pelanggan*: `{target}`\n"
                    f"• *Sandi Baru*: `{new_pass}`\n"
                    f"• *Status*: Terkirim ke modem via TR-069."
                ))
            else:
                send_telegram(token, chat_id, f"❌ Gagal: {msg}")
            return
        else:
            send_telegram(token, chat_id, "⚠️ Format salah. Gunakan:\n`/pass <username_pppoe> <sandi_baru>`\n_Contoh:_ `/pass cucimotor 12345678`")
            return

    if txt.startswith("/reboot "):
        target = txt[8:].strip()
        dev = find_device(target)
        if not dev:
            send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan.")
            return
        ok, msg = reboot_device_task(dev)
        send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}")
        return

    if txt.startswith("/wifi "):
        parts = txt[6:].strip().split()
        if len(parts) >= 3:
            target, new_ssid, new_pass = parts[0], parts[1], parts[2]
            dev = find_device(target)
            if not dev:
                send_telegram(token, chat_id, f"❌ Modem `{target}` tidak ditemukan.")
                return
            ok, msg = set_wifi_credentials(dev, new_ssid=new_ssid, new_password=new_pass)
            if ok:
                send_telegram(token, chat_id, (
                    f"✅ *Berhasil Mengubah WiFi & Sandi!*\n"
                    f"• *Pelanggan*: `{target}`\n"
                    f"• *SSID Baru*: `{new_ssid}`\n"
                    f"• *Sandi Baru*: `{new_pass}`\n"
                    f"• *Status*: Terkirim ke modem via TR-069."
                ))
            else:
                send_telegram(token, chat_id, f"❌ Gagal: {msg}")
            return
        else:
            send_telegram(token, chat_id, "⚠️ Format salah. Gunakan:\n`/wifi <username> <ssid> <password>`")
            return

    # Direct search fallback (bila pengguna langsung ketik nama pppoe atau SN)
    dev = find_device(txt)
    if dev:
        pppoe, summary, wifi_on = get_device_summary(dev)
        kb = get_device_inline_keyboard(pppoe, dev.get("_id") if dev else None, wifi_on) if dev else None
        send_telegram(token, chat_id, summary, reply_markup=kb)
        return

    # Gemini AI Fallback jika pengguna bertanya bahasa santai
    ai_reply = ask_gemini_ai(gemini_key, model_name, txt, chat_id)
    if ai_reply:
        send_telegram(token, chat_id, f"🤖 *{BRAND_NAME} AI:*\n\n{ai_reply}")
        return

    send_telegram(token, chat_id, "🤖 Perintah tidak dikenal. Klik tombol menu di bawah atau ketik `/menu`.", reply_markup=get_main_menu_keyboard())

# ==============================================================================
# BACKGROUND WATCHDOG (AUTO-ALERTS)
# ==============================================================================

def check_proactive_alerts(token, admin_ids):
    global SEEN_DEVICES, NOTIFIED_DROPS
    db = get_db()
    if db is None or not admin_ids:
        return
        
    now = time.time()
    try:
        # 1. Deteksi ONT Baru Belum Setting
        all_devs = list(db.devices.find({}, {"_id": 1, "_deviceId": 1, "VirtualParameters.pppoeUsername": 1, "_lastInform": 1}))
        current_ids = {d["_id"] for d in all_devs}
        
        # Inisialisasi awal agar tidak spam saat pertama kali bot start
        if not SEEN_DEVICES:
            SEEN_DEVICES = current_ids
            return
            
        new_ids = current_ids - SEEN_DEVICES
        for nid in new_ids:
            if "DISCOVERYSERVICE" in nid.upper():
                continue
            dev = db.devices.find_one({"_id": nid})
            if not dev: continue
            
            vp = dev.get("VirtualParameters", {})
            pppoe = vp.get("pppoeUsername", {}).get("_value")
            
            # Jika belum ada PPPoE, kirim notifikasi ONT baru
            if not pppoe or pppoe in ["0", "undefined", ""]:
                did = dev.get("_deviceId", {})
                sn = did.get("_SerialNumber") or nid
                mfr = did.get("_Manufacturer", "-")
                model = did.get("_ProductClass", "-")
                
                alert_msg = (
                    f"⚠️ *[NOTIFIKASI OTOMATIS] ONT BARU TERHUBUNG!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• *Serial Number*: `{sn}`\n"
                    f"• *Tipe Hardware*: {mfr} {model}\n"
                    f"• *Status*: Belum ada akun PPPoE terpasang.\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👉 *Format Pasang*: `/addwan {sn} <user_pppoe> <pass_pppoe>`"
                )
                for aid in admin_ids:
                    send_telegram(token, aid, alert_msg)
                    
        SEEN_DEVICES = current_ids
        
        # 2. Deteksi Redaman Anjlok Kritis (< -28.0 dBm)
        for d in db.devices.find({"VirtualParameters.RXPower": {"$exists": True}}):
            dev_id = d.get("_id")
            vp = d.get("VirtualParameters", {})
            rx_raw = vp.get("RXPower", {}).get("_value")
            try:
                rx_val = float(str(rx_raw).replace("dBm", "").strip())
                if rx_val < -28.0:
                    last_notif = NOTIFIED_DROPS.get(dev_id, 0)
                    if (now - last_notif) > 10800: # 3 jam cooldown per device
                        pppoe = vp.get("pppoeUsername", {}).get("_value") or dev_id
                        NOTIFIED_DROPS[dev_id] = now
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
            except Exception:
                pass
                
    except Exception as e:
        logger.error(f"Error in watchdog: {e}")

# ==============================================================================
# MAIN AGENT SERVICE LOOP
# ==============================================================================

def main():
    logger.info("Starting ALIJAYA NET GenieACS AI Agent Service...")
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
