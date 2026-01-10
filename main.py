import asyncio
import os
import re
import json
import time
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from typing import Dict, Any, List
import requests

# ==================== KONFIGURASI DENGAN NILAI TETAP ====================
# *** PASTIKAN SEMUA NILAI DI SINI SESUAI DENGAN KEBUTUHAN ANDA ***

# Konfigurasi Telegram
BOT_TOKEN = "7777855547:AAGTwJ01fjxjbd2TLJd8wmSEnUabD_yu2G4"
CHAT_ID = "-1003358198353"
ADMIN_ID = -1003358198353 # Gunakan CHAT_ID sebagai target default admin jika tidak ada

# Konfigurasi Chrome/Playwright
# Pastikan Chrome/Edge berjalan dengan --remote-debugging-port=9222
CHROME_DEBUG_URL = "http://127.0.0.1:9222" # URL CDP standar
DASHBOARD_URL = "https://x.mnitnetwork.com/mdashboard/getnum" 
LOGIN_URL = "https://x.mnitnetwork.com/mauth/login" 

# ==================== GLOBAL STATE & UTILS (Diambil dari skrip pertama) ====================

LAST_ID = 0
GLOBAL_ASYNC_LOOP = None 

# --- OTP Cache/Filter (Untuk mencegah duplikasi) ---
class OTPFilter:
    CLEANUP_KEY = '__LAST_CLEANUP_GMT__' 
    def __init__(self, file='otp_cache_mnit.json'): 
        self.file = file
        self.cache = self._load()
        self.last_cleanup_date_gmt = self.cache.pop(self.CLEANUP_KEY, '19700101') 
        self._cleanup() 
        
    def _load(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.file) and os.stat(self.file).st_size > 0:
            try:
                with open(self.file, 'r') as f: return json.load(f)
            except json.JSONDecodeError: return {}
        return {}
        
    def _save(self): 
        temp_cache = self.cache.copy()
        temp_cache[self.CLEANUP_KEY] = self.last_cleanup_date_gmt
        try:
             json.dump(temp_cache, open(self.file,'w'), indent=2)
        except Exception as e:
             print(f"❌ Gagal menyimpan cache: {e}")
    
    def _cleanup(self):
        now_gmt = datetime.now(timezone.utc).strftime('%Y%m%d')
        if now_gmt > self.last_cleanup_date_gmt:
            print("🚨 Cache OTP Harian direset.")
            self.cache = {} 
            self.last_cleanup_date_gmt = now_gmt
            self._save()
        else:
            self._save()
        
    def key(self, d: Dict[str, Any]) -> str: 
        return f"{d.get('otp')}_{d.get('phone')}"
    
    def is_dup(self, d: Dict[str, Any]) -> bool:
        self._cleanup() 
        key = self.key(d)
        if not key or key.split('_')[0] == 'None': return False 
        return key in self.cache
        
    def add(self, d: Dict[str, Any]):
        key = self.key(d)
        if not key or key.split('_')[0] == 'None': return
        self.cache[key] = {'timestamp':datetime.now().isoformat()} 
        self._save()
        
    def filter(self, lst: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for d in lst:
            if d.get('otp') and d.get('phone') != 'N/A':
                if not self.is_dup(d):
                    out.append(d)
                    self.add(d) 
        return out
otp_filter = OTPFilter()

# --- Utility Functions (Disesuaikan dari skrip pertama) ---

COUNTRY_EMOJI = {
    "NEPAL": "🇳🇵", "IVORY COAST": "🇨🇮", "GUINEA": "🇬🇳", "CENTRAL AFRIKA": "🇨🇫", 
    "TOGO": "🇹🇬", "TAJIKISTAN": "🇹🇯", "BENIN": "🇧🇯", "SIERRA LEONE": "🇸🇱", 
    "MADAGASCAR": "🇲🇬", "AFGANISTAN": "🇦🇫", "INDONESIA": "🇮🇩"
}
def get_country_emoji(country_name: str) -> str:
    return COUNTRY_EMOJI.get(country_name.strip().upper(), "❓")

def clean_phone_number(phone):
    if not phone: return "N/A"
    cleaned = re.sub(r'[^\d+]', '', phone)
    if cleaned and not cleaned.startswith('+') and cleaned != 'N/A':
        cleaned = '+' + cleaned
    return cleaned or phone

def mask_phone_number(phone, visible_start=4, visible_end=4):
    if not phone or phone == "N/A": return phone
    prefix = ""
    if phone.startswith('+'):
        prefix = '+'
        digits = phone[1:]
    else:
        digits = phone
        
    if len(digits) <= visible_start + visible_end:
        return phone
        
    digits = re.sub(r'[^\d]', '', digits)

    start_part = digits[:visible_start]
    end_part = digits[-visible_end:]
    mask_length = len(digits) - visible_start - visible_end
    masked_part = '*' * mask_length
    return prefix + start_part + masked_part + end_part

def extract_otp_from_text(text):
    """Fungsi ekstraksi OTP yang fleksibel (pola 668-098)"""
    if not text: return None
    patterns = [ 
        r'<#>\s*([\d\s-]+)\s*—',  
        r'code[:\s]*([\d\s-]+)',  
        r'verification[:\s]*([\d\s-]+)', 
        r'otp[:\s]*([\d\s-]+)',   
        r'pin[:\s]*([\d\s-]+)',   
        r'\b(\d{3}[- ]?\d{3})\b', 
        r'\b(\d{6})\b', 
        r'\b(\d{5})\b', 
        r'\b(\d{4})\b', 
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            matched_otp_raw = m.group(1) if len(m.groups()) >= 1 else m.group(0)
            matched_otp = re.sub(r'[^\d]', '', matched_otp_raw)
            if len(matched_otp) == 4 and 2000 <= int(matched_otp) <= 2099: continue 
            if matched_otp: return matched_otp
            
    return None

def clean_service_name(service):
    """Fungsi untuk membersihkan dan menstandarisasi nama layanan."""
    if not service: return "Unknown"
    
    maps = {
        'facebook': 'Facebook', 'whatsapp': 'WhatsApp', 'instagram': 'Instagram', 
        'telegram': 'Telegram', 'google': 'Google', 'twitter': 'Twitter', 
        'tiktok': 'TikTok', 'laz+nxcar': 'Facebook', 'mnitnetwork': 'M-NIT Network',
    }
    s_lower = service.strip().lower()

    for k, v in maps.items():
        if k in s_lower: return v
            
    if s_lower in ['ваш', 'your', 'service', 'code', 'pin']: return "Unknown Service"
            
    return service.strip().title()

def create_inline_keyboard():
    """Membuat payload keyboard inline untuk Telegram API."""
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "➡️ GetNumber", "url": "https://t.me/myzuraisgoodbot"},
                {"text": "👤 Admin", "url": "https://t.me/Imr1d"}
            ]
        ]
    }
    return json.dumps(keyboard)

def format_otp_message(otp_data: Dict[str, Any]) -> str:
    """Memformat data OTP menjadi pesan Telegram (seperti skrip pertama)."""
    otp = otp_data.get('otp', 'N/A')
    phone = otp_data.get('phone', 'N/A')
    masked_phone = mask_phone_number(phone, visible_start=4, visible_end=4)
    service = otp_data.get('service', 'Unknown')
    range_text = otp_data.get('range', 'N/A')
    full_message = otp_data.get('raw_message', 'N/A')
    
    emoji = get_country_emoji(range_text)
    full_message_escaped = full_message.replace('<', '&lt;').replace('>', '&gt;') 
    
    # Menggunakan tag <b> dan <code> sesuai skrip pertama
    return f"""🔐 <b>New OTP Received</b>

🌍 Country: <b>{range_text} {emoji}</b>

📱 Number: <code>{masked_phone}</code>
🌐 Service: <b>{service}</b>
🔢 OTP: <code>{otp}</code>

FULL MESSAGES:
<blockquote>{full_message_escaped}</blockquote>"""

def send_tg(text, with_inline_keyboard=False, target_chat_id=None):
    """Fungsi sederhana untuk mengirim pesan Telegram."""
    chat_id_to_use = target_chat_id if target_chat_id is not None else CHAT_ID
    if not BOT_TOKEN or not chat_id_to_use:
        print("❌ Telegram config missing. Cannot send message.")
        return
    payload = {'chat_id': chat_id_to_use, 'text': text, 'parse_mode': 'HTML'}
    if with_inline_keyboard:
        payload['reply_markup'] = create_inline_keyboard()
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=payload,
            timeout=15  
        )
    except requests.exceptions.RequestException as e:
        print(f"❌ Telegram Connection Error: {e}")

# ==================== PLAYWRIGHT/SCRAPER CLASS (Mirip skrip pertama) ====================

class SMSMonitor:
    
    def __init__(self, url=DASHBOARD_URL): 
        self.url = url
        self.browser = None
        self.page = None
        self.is_logged_in = False 
        self._temp_username = None 
        self._temp_password = None 

    async def initialize(self, p_instance):
        """Menghubungkan ke browser melalui CDP."""
        try:
            self.browser = await p_instance.chromium.connect_over_cdp(CHROME_DEBUG_URL)
            context = self.browser.contexts[0]
            self.page = await context.new_page()
            print(f"✅ Playwright page connected successfully to CDP: {CHROME_DEBUG_URL}")
        except Exception as e:
            print(f"❌ FATAL ERROR: Gagal terhubung ke Chrome CDP. Pastikan Chrome berjalan. Error: {e}")
            raise

    async def check_url_login_status(self) -> bool:
        """Memeriksa status login berdasarkan URL."""
        if not self.page: return False
        try:
            current_url = self.page.url
            self.is_logged_in = current_url.startswith("https://x.mnitnetwork.com/mdashboard")
            return self.is_logged_in
        except Exception:
            self.is_logged_in = False 
            return False

    async def fetch_sms(self) -> List[Dict[str, Any]]:
        """Mengambil dan memparsing data SMS dari dashboard."""
        if not self.page or not self.is_logged_in: 
            print("⚠️ ERROR: Page not initialized or not logged in during fetch_sms.")
            return []
            
        if self.page.url != self.url:
            try:
                await self.page.goto(self.url, wait_until='domcontentloaded', timeout=15000)
            except Exception as e:
                print(f"❌ Error navigating to dashboard: {e}")
                return []
                
        try:
            # Tunggu selector utama tabel data OTP
            await self.page.wait_for_selector('tbody.text-sm.divide-y.divide-white\\/5', timeout=10000)
        except PlaywrightTimeoutError:
             print("❌ Error: Timeout saat menunggu tabel data SMS. Mungkin halaman belum selesai dimuat atau perlu login ulang.")
             return []
        except Exception as e:
             print(f"❌ Error: Gagal menemukan tabel data SMS: {e}")
             return []


        html = await self.page.content()
        soup = BeautifulSoup(html, "html.parser")
        messages = []

        tbody = soup.find("tbody", class_="text-sm divide-y divide-white/5")
        if not tbody: return []
            
        rows = tbody.find_all("tr")

        SERVICE_KEYWORDS = r'(facebook|whatsapp|instagram|telegram|google|twitter|linkedin|tiktok)'

        for r in rows:
            tds = r.find_all("td")
            if len(tds) < 3: continue
            
            # Kolom 1 (Status, Phone, Message)
            col1 = tds[0]
            status_span = col1.find("span", class_=lambda x: x and "text-[10px] uppercase" in x)
            status = status_span.get_text(strip=True) if status_span else "N/A"
            
            if status.lower() != 'success': continue # Hanya ambil yang sukses
            
            # A. Phone Number
            phone_span = col1.find("span", class_=lambda x: x and "font-mono text-white font-bold text-lg" in x)
            phone_number_raw = phone_span.get_text(strip=True) if phone_span else "N/A"
            phone = clean_phone_number(phone_number_raw)
            
            # B. Raw Message (FULL)
            message_div = col1.find("div", class_=lambda x: x and "bg-slate-800 border" in x)
            raw_message_full = message_div.get_text(strip=True, separator=' ') if message_div else ""
            
            # C. OTP
            otp = extract_otp_from_text(raw_message_full)
                    
            # D. Range/Country (Kolom kedua)
            range_span = tds[1].find("span", class_="text-slate-200 font-medium")
            range_text = range_span.get_text(strip=True) if range_span else "N/A"
            
            # E. Service
            service_match = re.search(SERVICE_KEYWORDS, raw_message_full, re.IGNORECASE)
            
            if service_match:
                service = clean_service_name(service_match.group(1))
            else:
                # Logika fallback layanan
                service_hint = raw_message_full.split('—', 1)[1].strip() if '—' in raw_message_full else raw_message_full
                words = service_hint.split()
                service_raw = words[0] if words else service_hint
                service = clean_service_name(service_raw)
            
            # --- Simpan Hasil ---
            if otp and phone != 'N/A':
                messages.append({
                    "otp": otp,
                    "phone": phone,
                    "service": service,
                    "range": range_text,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "raw_message": raw_message_full 
                })
        return messages

monitor = SMSMonitor()

# ==================== MAIN LOOP ====================

async def monitor_sms_loop():
    global GLOBAL_ASYNC_LOOP
    global LAST_ID
    
    # Inisialisasi Telegram API (tanpa ApplicationBuilder karena hanya untuk send_tg sederhana)
    send_tg("🚀 Bot Playwright/BeautifulSoup aktif. Mencoba koneksi ke Chrome CDP...", target_chat_id=ADMIN_ID)

    async with async_playwright() as p:
        try:
            # 1. Inisialisasi Koneksi
            await monitor.initialize(p)
        except Exception:
            send_tg("🚨 <b>FATAL ERROR</b>: Gagal terhubung ke Chrome/Playwright. Cek log.", target_chat_id=ADMIN_ID)
            return 
    
        # 2. Loop Utama
        while True:
            try:
                # Periksa status login
                await monitor.check_url_login_status() 

                if monitor.is_logged_in:
                    
                    # A. Ambil data SMS
                    msgs = await monitor.fetch_sms()
                    
                    # B. Filter pesan baru (cegah duplikasi)
                    new_otps = otp_filter.filter(msgs)

                    if new_otps:
                        print(f"✅ Ditemukan {len(new_otps)} OTP baru. Mengirim ke Telegram...")
                        
                        for i, otp_data in enumerate(new_otps):
                            # Kirim ke Telegram (menggunakan format skrip pertama)
                            message_text = format_otp_message(otp_data)
                            send_tg(message_text, with_inline_keyboard=True, target_chat_id=CHAT_ID)
                            print(f"   -> Terkirim OTP {i+1}/{len(new_otps)}: {otp_data['otp']} for {otp_data['phone']}")
                            
                            await asyncio.sleep(2) # Jeda pengiriman
                    
                    # C. Refresh halaman (soft refresh/reload)
                    if monitor.page:
                         await monitor.page.reload(wait_until='networkidle')
                         print("🔄 Halaman Dashboard di-refresh.")

                else:
                    # Jika belum login, coba navigasi ke URL dashboard, tetapi bot ini tidak ada
                    # fungsi login otomatis, asumsikan user sudah login di CDP yang berjalan.
                    # Jika tidak, pesan peringatan akan muncul di console.
                    print("⚠️ TIDAK LOGIN. Pastikan Anda sudah login manual di browser Chrome yang terhubung ke CDP.")
                    try:
                        # Coba navigasi ulang, mungkin sesi sudah ada
                        await monitor.page.goto(DASHBOARD_URL, wait_until='domcontentloaded', timeout=5000)
                    except Exception:
                         pass

            except Exception as e:
                print(f"❌ Error saat fetch/send: {e.__class__.__name__}: {e}")

            # Waktu tunggu antara cek
            await asyncio.sleep(10) # 10 detik

# ==================== START EXECUTION ====================

if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_ID:
        print("FATAL ERROR: Pastikan BOT_TOKEN dan CHAT_ID ada di bagian KONFIGURASI.")
    else:
        print("Starting SMS Monitor Bot (Playwright/BeautifulSoup) with revised logic...")
        
        print("\n=======================================================")
        print("     ⚠️  PENTING: JALANKAN CHROME/EDGE TERPISAH   ⚠️")
        print("     Gunakan perintah ini di terminal terpisah:")
        print('     chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\temp\\playwright_profile"')
        print("=======================================================\n")

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        GLOBAL_ASYNC_LOOP = loop 
        
        try:
            loop.run_until_complete(monitor_sms_loop())
        except KeyboardInterrupt:
            print("\nBot shutting down...")
        finally:
            print("Bot core shutdown complete.")
