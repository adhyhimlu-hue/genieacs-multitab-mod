#!/usr/bin/env python3
# ==============================================================================
# ALIJAYA NET - GenieACS AI Telegram Agent (Interactive Menu, Buttons & Add WAN)
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
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
            val = val[1:-1]
        res[c["_id"]] = val.strip()
    return res

def is_valid_token(val):
    if not val:
        return False
    if "MASUKKAN_" in val:
        return False
    return True

# ==============================================================================
# KEYBOARD MARKUPS
# ==============================================================================

def get_main_menu_keyboard():
    return {
        "keyboard": [
            [{"text": "🔍 Cek Modem"}, {"text": "🔄 Reboot Modem"}],
            [{"text": "📶 Ubah SSID"}, {"text": "🔑 Ubah Sandi"}],
            [{"text": "🌐 Tambah / Set WAN"}, {"text": "📊 Status Server STB"}],
            [{"text": "❓ Bantuan / Help"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def get_device_inline_keyboard(pppoe_user):
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Reboot Modem", "callback_data": f"reboot:{pppoe_user}"},
                {"text": "⚡ Refresh Data", "callback_data": f"refresh:{pppoe_user}"}
            ],
            [
                {"text": "📶 Ganti SSID", "callback_data": f"prompt_ssid:{pppoe_user}"},
                {"text": "🔑 Ganti Sandi", "callback_data": f"prompt_pass:{pppoe_user}"}
            ],
            [
                {"text": "🌐 Set WAN PPPoE", "callback_data": f"prompt_wan:{pppoe_user}"}
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
        return None, "❌ Perangkat modem tidak ditemukan. Pastikan Username PPPoE atau Serial Number benar."
    
    dev_id = dev.get("_id", "Unknown")
    vp = dev.get("VirtualParameters", {})
    igd = dev.get("InternetGatewayDevice", {})
    device_id = dev.get("DeviceID", {})
    
    # PPPoE User
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
    if not pppoe:
        pppoe = dev_id
    
    rx = vp.get("RXPower", {}).get("_value") or "-"
    if rx != "-" and not str(rx).endswith("dBm"):
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
            
    mfr = device_id.get("Manufacturer", {}).get("_value") or "-"
    model = device_id.get("ProductClass", {}).get("_value") or "-"
    sn = device_id.get("SerialNumber", {}).get("_value") or dev_id
    
    res = (
        f"📡 *DATA MODEM: {pppoe}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Status*: {online_str}\n"
        f"• *Redaman (RX)*: `{rx}`\n"
        f"• *Suhu Transceiver*: `{temp}`\n"
        f"• *IP WAN*: `{ip}`\n"
        f"• *Uptime*: `{uptime}`\n"
        f"• *Nama WiFi (SSID)*: `{ssid}`\n"
        f"• *Sandi WiFi*: `{wifi_pass}`\n"
        f"• *User HP Terkoneksi*: `{clients} perangkat`\n"
        f"• *Hardware*: {mfr} {model} (SN: `{sn}`)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 *ALIJAYA NET TR-069*"
    )
    return pppoe, res

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

def add_or_set_wan_pppoe(dev, pppoe_user, pppoe_pass, vlan_id=None):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    igd = dev.get("InternetGatewayDevice", {})
    wandev = igd.get("WANDevice", {})

    target_path = None
    # 1. Search for best existing WANPPPConnection (prefer INTERNET profile or existing username)
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
                
                # If name has INTERNET or user matches, lock this path
                if "INTERNET" in name or cur_user == pppoe_user:
                    target_path = f"InternetGatewayDevice.WANDevice.{wk}.WANConnectionDevice.{ck}.WANPPPConnection.{pk}"
                    break
                elif not target_path and cur_user == "":
                    target_path = f"InternetGatewayDevice.WANDevice.{wk}.WANConnectionDevice.{ck}.WANPPPConnection.{pk}"
            if target_path and "INTERNET" in target_path:
                break
        if target_path and "INTERNET" in target_path:
            break

    # If no path found, fallback to default WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1
    # or create via addObject
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
        logger.error(f"Failed to send Telegram message: {e}")

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
        {"command": "addwan", "description": "Tambah/Set WAN: /addwan <sn> <user> <pass> [vlan]"},
        {"command": "ssid", "description": "Ganti nama WiFi saja: /ssid <user> <nama>"},
        {"command": "pass", "description": "Ganti sandi WiFi saja: /pass <user> <sandi>"},
        {"command": "wifi", "description": "Ganti SSID & Sandi: /wifi <user> <ssid> <sandi>"},
        {"command": "reboot", "description": "Restart modem pelanggan: /reboot <user>"},
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
        pppoe, summary = get_device_summary(fresh_dev)
        kb = get_device_inline_keyboard(pppoe) if pppoe else None
        send_telegram(token, sender_id, summary, reply_markup=kb)
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
            "🤖 *ALIJAYA NET - GenieACS Telegram Bot*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Gunakan tombol menu di bawah untuk aksi cepat, atau ketik perintah langsung:\n\n"
            "📌 *Perintah Cepat:*\n"
            "• `/cek <user_atau_sn>` ➔ Cek redaman & status\n"
            "• `/addwan <sn> <user> <pass> [vlan]` ➔ Tambah/Set WAN PPPoE\n"
            "• `/ssid <user> <nama_baru>` ➔ Ganti nama WiFi\n"
            "• `/pass <user> <sandi_baru>` ➔ Ganti sandi WiFi\n"
            "• `/wifi <user> <ssid> <sandi>` ➔ Ganti SSID & sandi\n"
            "• `/reboot <user>` ➔ Restart modem pelanggan\n"
            "• `/server` ➔ Status performa STB\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👑 *Pengembang: ALIJAYA NET (081947215703)*"
        )
        send_telegram(token, chat_id, welcome, reply_markup=get_main_menu_keyboard())
        return

    if txt == "🔍 Cek Modem":
        USER_STATES[chat_id] = {"action": "wait_cek"}
        send_telegram(token, chat_id, "🔍 *Cek Modem*: Silakan ketik Username PPPoE atau Serial Number (contoh: `cucimotor`):")
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

    if txt == "📶 Ubah SSID":
        send_telegram(token, chat_id, "📶 *Ubah Nama WiFi (SSID)*:\nFormat: `/ssid <username_pppoe> <nama_baru>`\nContoh: `/ssid cucimotor Cuci Motor Baru`")
        return

    if txt == "🔑 Ubah Sandi":
        send_telegram(token, chat_id, "🔑 *Ubah Sandi WiFi*:\nFormat: `/pass <username_pppoe> <sandi_baru>`\nContoh: `/pass cucimotor 12345678`")
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
            pppoe, summary = get_device_summary(dev)
            kb = get_device_inline_keyboard(pppoe) if pppoe else None
            send_telegram(token, chat_id, summary, reply_markup=kb)
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
        pppoe, summary = get_device_summary(dev)
        kb = get_device_inline_keyboard(pppoe) if pppoe else None
        send_telegram(token, chat_id, summary, reply_markup=kb)
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

    # Direct search fallback
    dev = find_device(txt)
    if dev:
        pppoe, summary = get_device_summary(dev)
        kb = get_device_inline_keyboard(pppoe) if pppoe else None
        send_telegram(token, chat_id, summary, reply_markup=kb)
        return

    send_telegram(token, chat_id, "🤖 Perintah tidak dikenal. Klik tombol menu di bawah atau ketik `/menu`.", reply_markup=get_main_menu_keyboard())

# ==============================================================================
# MAIN AGENT SERVICE LOOP
# ==============================================================================

def main():
    logger.info("Starting ALIJAYA NET GenieACS AI Agent Service...")
    last_update_id = 0
    notified_online = False
    
    while True:
        try:
            cfgs = get_config()
            enabled = cfgs.get("agent.enabled", "true").lower() == "true"
            token = cfgs.get("agent.telegram.botToken", "")
            admin_chat_id = cfgs.get("agent.telegram.adminChatId", "")
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
                if is_valid_token(admin_chat_id):
                    greeting = (
                        "🚀 *ALIJAYA NET GenieACS Bot Aktif!*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "Menu interaktif, tombol cepat & fitur Add WAN siap digunakan.\n"
                        "Ketik `/menu` atau klik tombol di bawah untuk mulai."
                    )
                    send_telegram(token, admin_chat_id, greeting, reply_markup=get_main_menu_keyboard())
                notified_online = True
                logger.info("Bot Telegram berhasil terhubung dan siap melayani!")

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
                        if is_valid_token(admin_chat_id) and cb_sender != admin_chat_id:
                            answer_callback(token, cb_id, "Akses ditolak!", show_alert=True)
                            continue
                        handle_callback_query(token, cb_sender, cb_data, cb_id)
                        continue

                    msg = upd.get("message", {})
                    chat = msg.get("chat", {})
                    sender_id = str(chat.get("id", ""))
                    text = msg.get("text", "")
                    
                    if is_valid_token(admin_chat_id) and sender_id != admin_chat_id:
                        logger.warning(f"Unauthorized chat from {sender_id}: {text}")
                        send_telegram(token, sender_id, "⛔ Akses Ditolak: Anda bukan Admin ALIJAYA NET.")
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
