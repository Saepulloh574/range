import asyncio
import os
import re
import json
import time
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
# Menghapus: from bs4 import BeautifulSoup
from typing import Dict, Any, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder 
import requests # Masih diperlukan untuk send_tg jika admin message diperlukan

# ==================== KONFIGURASI DENGAN NILAI TETAP ====================

# Konfigurasi Telegram
BOT_TOKEN = "8558006836:AAGR3N4DwXYSlpOxjRvjZcPAmC1CUWRJexY"
CHAT_ID = "-1003358198353"
ADMIN_ID = 7184123643 

# Konfigurasi Chrome/Playwright
CHROME_DEBUG_URL = "http://127.0.0.1:9222" # URL CDP standar
# *** TELAH DIKOREKSI KE CONSOLE ***
DASHBOARD_URL = "https://x.mnitnetwork.com/mdashboard/console" 
LOGIN_URL = "https://x.mnitnetwork.com/mauth/login" 

# ==================== GLOBAL STATE & UTILS (SAMA) ====================

SENT_MESSAGES = {} 
GLOBAL_ASYNC_LOOP = None 

# --- Filter Pesan Unik (MessageFilter) ---
class MessageFilter:
    CLEANUP_KEY = '__LAST_CLEANUP_GMT__' 
    def __init__(self, file='range_cache_mnit.json'): 
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
            print("🚨 Cache Harian Range direset.")
            self.cache = {} 
            self.last_cleanup_date_gmt = now_gmt
            self._save()
        else:
            self._save()
        
    def key(self, d: Dict[str, Any]) -> str: 
        phone = d.get('range_key')
        raw_message = d.get('raw_message')
        return f"{phone}_{hash(raw_message)}"
    
    def is_dup(self, d: Dict[str, Any]) -> bool:
        self._cleanup() 
        key = self.key(d)
        if not key or key.startswith('N/A'): return False 
        return key in self.cache
        
    def add(self, d: Dict[str, Any]):
        key = self.key(d)
        if not key or key.startswith('N/A'): return
        self.cache[key] = {'timestamp':datetime.now().isoformat()} 
        self._save()
        
    def filter(self, lst: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for d in lst:
            if d.get('range_key') != 'N/A' and d.get('raw_message'):
                if not self.is_dup(d):
                    out.append(d)
                    self.add(d) 
        return out
message_filter = MessageFilter()

# --- Utility Functions (SAMA) ---

COUNTRY_EMOJI = {
    "NEPAL": "🇳🇵", "IVORY COAST": "🇨🇮", "GUINEA": "🇬🇳", "CENTRAL AFRIKA": "🇨🇫", 
    "TOGO": "🇹🇬", "TAJIKISTAN": "🇹🇯", "BENIN": "🇧🇯", "SIERRA LEONE": "🇸🇱", 
    "MADAGASCAR": "🇲🇬", "AFGANISTAN": "🇦🇫", "INDONESIA": "🇮🇩", "UNITED STATES": "🇺🇸" 
}
def get_country_emoji(country_name: str) -> str:
    return COUNTRY_EMOJI.get(country_name.strip().upper(), "❓")

def clean_phone_number(phone):
    if not phone: return "N/A"
    cleaned = re.sub(r'[^\d+]', '', phone)
    return cleaned or phone

def mask_phone_number(phone, visible_start=4, visible_end=4):
    if not phone or phone == "N/A": return phone
    prefix = ""
    digits = phone
    if phone.startswith('+'):
        prefix = '+'
        digits = phone[1:]
        
    if len(digits) <= visible_start + visible_end:
        return phone
        
    digits = re.sub(r'[^\d]', '', digits)

    start_part = digits[:visible_start]
    end_part = digits[-visible_end:]
    mask_length = len(digits) - visible_start - visible_end
    masked_part = '*' * mask_length
    return prefix + start_part + masked_part + end_part

def clean_service_name(service):
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

def create_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📞GetNumber", url="https://t.me/myzuraisgoodbot?start=ZuraBot"),
            InlineKeyboardButton("👤Admin", url="https://t.me/Imr1d")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_live_message(range_val, count, country_name, service, full_message):
    country_emoji = get_country_emoji(country_name)
    masked_range = mask_phone_number(range_val, visible_start=4, visible_end=4)
    range_with_count = f"<code>{masked_range}</code> ({count}x)" if count > 1 else f"<code>{masked_range}</code>"
    full_message_escaped = full_message.replace('<', '&lt;').replace('>', '&gt;')
    
    message = (
        "🔥Live message new range\n"
        f"📱Range: {range_with_count}\n"
        f"{country_emoji}Country: {country_name}\n"
        f"⚙️ Service: {service}\n"
        "🗯️Message Available :\n"
        f"<blockquote>{full_message_escaped}</blockquote>"
    )
    return message


async def cleanup_old_messages(app):
    global SENT_MESSAGES
    ten_minutes_ago = datetime.now() - timedelta(minutes=10)
    
    ranges_to_remove = []
    for range_val, data in SENT_MESSAGES.items():
        if data['timestamp'] < ten_minutes_ago:
            ranges_to_remove.append(range_val)
            print(f"🧹 Range {range_val} (Count: {data['count']}) sudah lebih dari 10 menit, menghapus dari pelacakan.")
            
    for range_val in ranges_to_remove:
        del SENT_MESSAGES[range_val]

async def send_or_edit_telegram_message(app, range_val, country, service, message_text):
    global SENT_MESSAGES
    reply_markup = create_keyboard()
    try:
        if range_val in SENT_MESSAGES:
            message_id = SENT_MESSAGES[range_val]['message_id']
            await app.bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=message_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            sent_message = await app.bot.send_message(
                chat_id=CHAT_ID,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            SENT_MESSAGES[range_val] = {
                'message_id': sent_message.message_id,
                'count': 1,
                'timestamp': datetime.now()
            }
    except Exception as e:
        if 'Message is not modified' not in str(e):
             print(f"❌ Gagal mengirim/mengedit pesan Telegram: {e}")

async def send_startup_message(app):
    if not BOT_TOKEN or not CHAT_ID: return
    try:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="✅Ready to check the latest range (Playwright CONSOLE Monitor)",
            parse_mode='HTML'
        )
        print("✅ Pesan startup terkirim.")
    except Exception as e:
        print(f"❌ Gagal mengirim pesan startup: {e}")

# ==================== PLAYWRIGHT/SCRAPER CLASS (REVISI KONSEL) ====================

class SMSMonitor:
    
    def __init__(self, url=DASHBOARD_URL): 
        self.url = url
        self.browser = None
        self.page = None
        self.is_logged_in = False 
        # Selector khusus untuk blok konsol live
        self.CONSOLE_SELECTOR = ".group.flex.flex-col.sm\\:flex-row.sm\\:items-start.gap-3.p-3.rounded-lg"


    async def initialize(self, p_instance):
        try:
            self.browser = await p_instance.chromium.connect_over_cdp(CHROME_DEBUG_URL)
            context = self.browser.contexts[0]
            self.page = await context.new_page()
            print(f"✅ Playwright page connected successfully to CDP: {CHROME_DEBUG_URL}")
        except Exception as e:
            print(f"❌ FATAL ERROR: Gagal terhubung ke Chrome CDP. Pastikan Chrome berjalan. Error: {e}")
            raise

    async def check_url_login_status(self) -> bool:
        if not self.page: return False
        try:
            current_url = self.page.url
            self.is_logged_in = current_url.startswith("https://x.mnitnetwork.com/mdashboard")
            return self.is_logged_in
        except Exception:
            self.is_logged_in = False 
            return False

    async def fetch_sms(self) -> List[Dict[str, Any]]:
        """Mengambil dan memparsing data SMS dari konsol live (/console)."""
        if not self.page or not self.is_logged_in: return []
            
        if self.page.url != self.url:
            try:
                # Navigasi ke URL konsol
                await self.page.goto(self.url, wait_until='networkidle', timeout=15000)
            except Exception as e:
                print(f"❌ Error navigating to console dashboard: {e}")
                return []
                
        try:
            # Tunggu selector blok konsol
            await self.page.wait_for_selector(self.CONSOLE_SELECTOR, timeout=10000)
        except PlaywrightTimeoutError: 
             print("❌ Timeout saat menunggu blok data konsol.")
             return []

        messages = []
        
        # Menggunakan Playwright API untuk mendapatkan semua blok data
        elements = await self.page.locator(self.CONSOLE_SELECTOR).all()

        SERVICE_KEYWORDS = r'(facebook|whatsapp|instagram|telegram|google|twitter|linkedin|tiktok)'

        for element in elements:
            try:
                # 1. Service
                service_element = element.locator(".flex-grow.min-w-0 .text-xs.font-bold.text-blue-400")
                service_text = await service_element.inner_text() if await service_element.count() > 0 else "N/A"
                service = clean_service_name(service_text)
                
                # Hanya fokus pada WhatsApp dan Facebook (sesuai Pyppeteer sebelumnya, bisa dihapus)
                if service.strip().upper() not in ["WHATSAPP", "FACEBOOK"]:
                    # Lanjutkan ke log berikutnya jika bukan layanan yang diinginkan
                    # HAPUS baris IF ini jika Anda ingin semua layanan
                    pass 

                # 2. Range/Phone
                phone_element = element.locator(".flex-grow.min-w-0 .text-\\[10px\\].text-slate-500.font-mono")
                phone_raw = await phone_element.inner_text() if await phone_element.count() > 0 else "N/A"
                phone = clean_phone_number(phone_raw) # Ini adalah range_key
                
                # 3. Country
                country_element = element.locator(".flex-shrink-0 .text-\\[10px\\].text-slate-600.mt-1.font-mono")
                country_full = await country_element.inner_text() if await country_element.count() > 0 else ""
                # Ekstraksi nama negara dari teks (e.g., "ID • INDONESIA")
                country_match = re.search(r'•\s*(.*)$', country_full.strip())
                country_name = country_match.group(1).strip() if country_match else "Unknown"
                
                # 4. Message (FULL)
                message_element = element.locator(".flex-grow.min-w-0 p")
                message_text = await message_element.inner_text() if await message_element.count() > 0 else ""
                full_message = message_text.replace('➜', '').strip()

                # --- Simpan Hasil ---
                if phone != 'N/A' and full_message:
                    messages.append({
                        "range_key": phone, 
                        "country": country_name,
                        "service": service,
                        "raw_message": full_message 
                    })
            except Exception as e:
                # Error saat memproses satu blok log, lewati
                print(f"⚠️ Error memproses satu blok konsol: {e}")
                continue
                
        return messages

monitor = SMSMonitor()

# ==================== MAIN LOOP DENGAN LOGIKA LIVE CONSOLE (SAMA) ====================

async def monitor_sms_loop(app):
    global SENT_MESSAGES
    
    # 1. Inisialisasi Koneksi Playwright
    async with async_playwright() as p:
        try:
            await monitor.initialize(p)
        except Exception:
            await app.bot.send_message(chat_id=ADMIN_ID, text="🚨 <b>FATAL ERROR</b>: Gagal terhubung ke Chrome/Playwright. Cek log.", parse_mode='HTML')
            return 
        
        # 2. Loop Utama
        while True:
            try:
                await monitor.check_url_login_status() 

                if monitor.is_logged_in:
                    
                    # A. Ambil data SMS (Sekarang dari /console)
                    msgs = await monitor.fetch_sms()
                    
                    # B. Filter pesan baru
                    new_unique_logs = message_filter.filter(msgs) 

                    if new_unique_logs:
                        print(f"✅ Ditemukan {len(new_unique_logs)} log unik baru. Memproses Live Counter...")
                        
                        # C. Proses Live Counter dan Kirim/Edit Pesan
                        for log in new_unique_logs:
                            range_val = log['range_key']
                            
                            if range_val in SENT_MESSAGES:
                                old_data = SENT_MESSAGES[range_val]
                                new_count = old_data['count'] + 1
                                SENT_MESSAGES[range_val]['count'] = new_count
                                SENT_MESSAGES[range_val]['timestamp'] = datetime.now()
                                
                                message_text = format_live_message(
                                    range_val, new_count, log['country'], log['service'], log['raw_message']
                                )
                                await send_or_edit_telegram_message(app, range_val, log['country'], log['service'], message_text)

                            else:
                                message_text = format_live_message(
                                    range_val, 1, log['country'], log['service'], log['raw_message']
                                )
                                await send_or_edit_telegram_message(app, range_val, log['country'], log['service'], message_text)
                            
                            await asyncio.sleep(0.5) 

                    # D. Bersihkan pesan lama
                    await cleanup_old_messages(app)
                    
                    # E. Refresh halaman
                    if monitor.page:
                         # Pada halaman konsol, reload mungkin kurang efektif
                         # Disarankan menggunakan page.goto ulang ke URL yang sama
                         await monitor.page.goto(DASHBOARD_URL, wait_until='networkidle', timeout=10000)
                         print("🔄 Halaman Konsol di-reload (refresh).")

                else:
                    print("⚠️ TIDAK LOGIN. Pastikan Anda sudah login manual di browser Chrome yang terhubung ke CDP.")
                    try:
                        await monitor.page.goto(DASHBOARD_URL, wait_until='domcontentloaded', timeout=5000)
                    except Exception:
                         pass

            except Exception as e:
                print(f"❌ Error saat fetch/send di loop utama: {e.__class__.__name__}: {e}")

            # Waktu tunggu antara cek
            await asyncio.sleep(10)

# ==================== START EXECUTION (SAMA) ====================

async def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT_TOKEN atau CHAT_ID tidak ditemukan di bagian KONFIGURASI. Pastikan sudah benar.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    print("🤖 Telegram Bot terhubung.")
    
    await send_startup_message(app)
    
    await monitor_sms_loop(app)

if __name__ == "__main__":
    
    print("Starting SMS Monitor Bot (Playwright CONSOLE Scraper - OTP Free)...")
    
    print("\n=======================================================")
    print("     ⚠️  PENTING: JALANKAN CHROME/EDGE TERPISAH   ⚠️")
    print("     Gunakan perintah ini di terminal terpisah:")
    print('     chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\temp\\playwright_profile"')
    print("=======================================================\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot shutting down...")
    except Exception as e:
        print(f"Error fatal: {e}")
