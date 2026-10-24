#!/usr/bin/env python3
# ==============================================================================
# ALIJAYA NET - GenieACS AI Telegram Agent (Powered by Gemini)
# Pengembang: ALIJAYA NET (WhatsApp: 081947215703)
# ==============================================================================

import time
import json
import logging
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
        # Strip outer single or double quotes if entered in GenieACS UI
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
# GENIEACS CORE OPERATIONS
# ==============================================================================

def find_device(query_str):
    db = get_db()
    if db is None:
        return None
    q = query_str.strip()
    reg = {"$regex": q, "$options": "i"}

    # Search by PPPoE Username, SSID, Serial Number, or IP
    dev = db.devices.find_one({
        "$or": [
            {"VirtualParameters.pppoeUsername._value": reg},
            {"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.Username._value": reg},
            {"VirtualParameters.WlanSSID._value": reg},
            {"InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID._value": reg},
            {"_id": reg},
            {"DeviceID.SerialNumber._value": reg},
            {"VirtualParameters.pppoeIP._value": q},
            {"InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.ExternalIPAddress._value": q}
        ]
    })
    return dev

def get_device_summary(dev):
    if not dev:
        return "Perangkat modem tidak ditemukan. Pastikan Username PPPoE benar."
    
    dev_id = dev.get("_id", "Unknown")
    vp = dev.get("VirtualParameters", {})
    igd = dev.get("InternetGatewayDevice", {})
    device_id = dev.get("DeviceID", {})
    
    # PPPoE User
    pppoe = (
        vp.get("pppoeUsername", {}).get("_value") or
        igd.get("WANDevice", {}).get("1", {}).get("WANConnectionDevice", {}).get("1", {}).get("WANPPPConnection", {}).get("1", {}).get("Username", {}).get("_value") or
        "-"
    )
    
    # Redaman RX
    rx = vp.get("RXPower", {}).get("_value") or "-"
    if rx != "-" and not str(rx).endswith("dBm"):
        rx = f"{rx} dBm"
        
    # Suhu
    temp = vp.get("gettemp", {}).get("_value") or vp.get("temp", {}).get("_value") or "-"
    if temp != "-" and not str(temp).endswith("°C"):
        temp = f"{temp} °C"
        
    # Uptime
    uptime = vp.get("getdeviceuptime", {}).get("_value") or vp.get("uptimeDevice", {}).get("_value") or "-"
    
    # IP WAN
    ip = (
        vp.get("pppoeIP", {}).get("_value") or
        igd.get("WANDevice", {}).get("1", {}).get("WANConnectionDevice", {}).get("1", {}).get("WANPPPConnection", {}).get("1", {}).get("ExternalIPAddress", {}).get("_value") or
        "-"
    )
    
    # WiFi SSID & Password
    wlan1 = igd.get("LANDevice", {}).get("1", {}).get("WLANConfiguration", {}).get("1", {})
    ssid = wlan1.get("SSID", {}).get("_value") or vp.get("WlanSSID", {}).get("_value") or "-"
    wifi_pass = (
        wlan1.get("KeyPassphrase", {}).get("_value") or
        wlan1.get("PreSharedKey", {}).get("1", {}).get("KeyPassphrase", {}).get("_value") or
        vp.get("WlanPassword", {}).get("_value") or
        "(Tersimpan Aman di Modem)"
    )
    
    # Klien Aktif
    clients = (
        wlan1.get("TotalAssociations", {}).get("_value") or
        vp.get("activedevices", {}).get("_value") or
        "0"
    )
    
    # Online Status
    last_inform = dev.get("_lastInform")
    online_str = "Offline"
    if last_inform:
        diff_sec = (time.time() - last_inform.timestamp())
        if diff_sec < 600:
            online_str = "Online (Aktif) 🟢"
        else:
            online_str = f"Offline ({int(diff_sec//60)} mnt lalu) 🔴"
            
    # Hardware info
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
    return res

def set_wifi_credentials(dev, new_ssid=None, new_password=None):
    if not dev:
        return False, "Modem pelanggan tidak ditemukan."
    dev_id = dev.get("_id")
    
    param_values = []
    if new_ssid:
        param_values.append(["InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID", new_ssid, "xsd:string"])
    if new_password:
        # Send to both KeyPassphrase and PreSharedKey to cover ZTE & Huawei/GM220
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

# ==============================================================================
# GEMINI AI INTELLIGENCE & INTENT ROUTER
# ==============================================================================

def query_gemini(api_key, model_name, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    system_inst = (
        "Anda adalah ALIJAYA NET Network AI Assistant di server GenieACS TR-069. "
        "Tugas Anda membantu admin/teknisi mengelola modem pelanggan via PPPoE username. "
        "Analisa teks pengguna dan jawab dalam format JSON sederhana jika mendeteksi perintah:\n"
        "Format JSON:\n"
        "{\n"
        '  "action": "cek_status" | "ganti_wifi" | "reboot" | "chat",\n'
        '  "pppoe_username": "username yang dimaksud",\n'
        '  "new_ssid": "nama wifi baru jika ada",\n'
        '  "new_password": "sandi wifi baru jika ada",\n'
        '  "reply": "jawaban ramah dalam Bahasa Indonesia jika hanya chat biasa"\n'
        "}\n"
        "Keluarkan HANYA JSON murni tanpa markdown formatting backticks."
    )
    
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{system_inst}\n\nPesan Pengguna: {prompt}"}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 500
        }
    }
    
    try:
        r = requests.post(url, json=payload, timeout=12)
        if r.status_code == 200:
            data = r.json()
            cand = data.get("candidates", [])[0]
            raw_text = cand.get("content", {}).get("parts", [])[0].get("text", "").strip()
            # Clean possible markdown
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                raw_text = "\n".join(lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:])
            return json.loads(raw_text)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
    return None

# ==============================================================================
# TELEGRAM BOT CLIENT
# ==============================================================================

def send_telegram(token, chat_id, text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

def handle_incoming_message(token, chat_id, user_text, gemini_key, model_name):
    txt = user_text.strip()
    
    # 1. Direct Command Fast-Path (Dapat berjalan 100% tanpa Gemini API Key)
    if txt.startswith("/start") or txt.startswith("/help"):
        help_msg = (
            "🤖 *ALIJAYA NET - GenieACS Telegram Bot*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Perintah langsung (Bisa digunakan tanpa API Key):\n\n"
            "🔍 *Cek Status & Redaman:*\n"
            "• `/cek <pppoe_username>`\n"
            "  _Contoh:_ `/cek cucimotor`\n\n"
            "📶 *Ubah Nama WiFi (SSID):*\n"
            "• `/ssid <pppoe_user> <nama_wifi_baru>`\n"
            "  _Contoh:_ `/ssid cucimotor Cuci Motor Baru`\n\n"
            "🔑 *Ubah Sandi WiFi (Password):*\n"
            "• `/pass <pppoe_user> <sandi_baru>`\n"
            "  _Contoh:_ `/pass cucimotor 12345678`\n\n"
            "⚡ *Ubah SSID & Sandi Sekaligus:*\n"
            "• `/wifi <pppoe_user> <ssid_baru> <sandi_baru>`\n"
            "  _Contoh:_ `/wifi cucimotor CuciMotor 12345678`\n\n"
            "🔄 *Restart / Reboot Modem:*\n"
            "• `/reboot <pppoe_user>`\n"
            "  _Contoh:_ `/reboot cucimotor`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👑 *Pengembang: ALIJAYA NET (081947215703)*"
        )
        send_telegram(token, chat_id, help_msg)
        return

    if txt.startswith("/cek "):
        target = txt[5:].strip()
        dev = find_device(target)
        send_telegram(token, chat_id, get_device_summary(dev))
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

    # 2. Natural Language via Gemini AI
    if is_valid_token(gemini_key):
        intent = query_gemini(gemini_key, model_name, txt)
        if intent:
            action = intent.get("action")
            user_target = intent.get("pppoe_username", "").strip()
            
            if action in ["cek_status", "cek_redaman", "info_lengkap"] and user_target:
                dev = find_device(user_target)
                send_telegram(token, chat_id, get_device_summary(dev))
                return
            elif action == "ganti_wifi" and user_target:
                dev = find_device(user_target)
                new_ssid = intent.get("new_ssid")
                new_pass = intent.get("new_password")
                ok, msg = set_wifi_credentials(dev, new_ssid, new_pass)
                send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}\n• *SSID*: `{new_ssid}`\n• *Sandi*: `{new_pass}`")
                return
            elif action == "reboot" and user_target:
                dev = find_device(user_target)
                ok, msg = reboot_device_task(dev)
                send_telegram(token, chat_id, f"{'✅' if ok else '❌'} {msg}")
                return
            elif intent.get("reply"):
                send_telegram(token, chat_id, intent["reply"])
                return

    # Fallback jika nama pelanggan langsung diketik
    dev = find_device(txt)
    if dev:
        send_telegram(token, chat_id, get_device_summary(dev))
    else:
        send_telegram(token, chat_id, "🤖 Maaf, saya belum memahami pesan Anda. Ketik `/help` untuk panduan.")

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
                
            # If valid, greet once
            if not notified_online and is_valid_token(admin_chat_id):
                greeting = (
                    "🚀 *ALIJAYA NET GenieACS AI Agent Aktif!*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Server siap menerima perintah pemantauan modem.\n"
                    "Ketik `/help` untuk panduan atau sebutkan username PPPoE."
                )
                send_telegram(token, admin_chat_id, greeting)
                notified_online = True
                logger.info("Bot Telegram berhasil terhubung dan menyapa Admin!")

            # Long polling Telegram
            poll_url = f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id + 1}&timeout=15"
            r = requests.get(poll_url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                for upd in data.get("result", []):
                    last_update_id = upd.get("update_id", last_update_id)
                    msg = upd.get("message", {})
                    chat = msg.get("chat", {})
                    sender_id = str(chat.get("id", ""))
                    text = msg.get("text", "")
                    
                    # Security filter: if adminChatId configured, only accept from admin
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
