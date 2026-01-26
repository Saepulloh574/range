import asyncio
import os
import re
import json
import time
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, Any, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder 
import requests 

# ==================== KONFIGURASI DENGAN NILAI TETAP ====================

# Konfigurasi Telegram
BOT_TOKEN = "8264103317:AAG_-LZQIxrMDIlLlttWQqIvA9xu_GNMwnc"
CHAT_ID = "-1003358198353"
ADMIN_ID = 7184123643 

# Konfigurasi Chrome/Playwright
CHROME_DEBUG_URL = "http://127.0.0.1:9222" # URL CDP standar
DASHBOARD_URL = "https://x.mnitnetwork.com/mdashboard/console" 
LOGIN_URL = "https://x.mnitnetwork.com/mauth/login" 

# ==================== GLOBAL STATE & UTILS ====================

SENT_MESSAGES = {} 
GLOBAL_ASYNC_LOOP = None 

# --- Filter Pesan Unik (MessageFilter) ---
class MessageFilter:
    CLEANUP_KEY = '__LAST_CLEANUP_GMT__' 
    def __init__(self, file='range_cache_mnit.json'): 
        self.file = file
        
        # HAPUS CACHE SAAT STARTUP
        if os.path.exists(self.file):
            try:
                os.remove(self.file)
                print(f"🗑️ Cache lama '{self.file}' berhasil dihapus saat startup.")
            except Exception as e:
                print(f"❌ Gagal menghapus cache saat startup: {e}")
        
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

# --- Utility Functions ---

COUNTRY_EMOJI = {
    "NEPAL": "🇳🇵", "IVORY COAST": "🇨🇮", "GUINEA": "🇬🇳", "CENTRAL AFRIKA": "🇨🇫", 
    "TOGO": "🇹🇬", "TAJIKISTAN": "🇹🇯", "BENIN": "🇧🇯", "SIERRA LEONE": "🇸🇱", 
    "MADAGASCAR": "🇲🇬", "AFGHANISTAN": "🇦🇫", "NETHERLANDS": "🇳🇱",  
    "INDONESIA": "🇮🇩", "UNITED STATES": "🇺🇸", "ANGOLA": "🇦🇴", 
    "CAMEROON": "🇨🇲", "MOZAMBIQUE": "🇲🇿", "PERU": "🇵🇪", "VIETNAM": "🇻🇳",
    "MYANMAR": "🇲🇲", "GEORGIA": "🇬🇪"
}

def get_country_emoji(country_name: str) -> str:
    return COUNTRY_EMOJI.get(country_name.strip().upper(), "🇹🇾")

def clean_phone_number(phone):
    if not phone: return "N/A"
    cleaned = re.sub(r'[^0-9X]', '', phone) 
    return cleaned or phone

def format_phone_number(phone):
    if not phone or phone == "N/A": return phone
    return phone

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
    keyboard = [[InlineKeyboardButton("📞GetNumber", url="https://t.me/myzuraisgoodbot?start=ZuraBot")]]
    return InlineKeyboardMarkup(keyboard)

# --- FUNGSI SIMPAN JSON DENGAN STRUKTUR BARU (WA/FB) ---
def save_to_inline_json(range_val, country_name, service):
    # Mapping nama service menjadi singkatan
    service_map = {
        'whatsapp': 'WA',
        'facebook': 'FB'
    }
    
    # Cek apakah service yang masuk ada di mapping kita (case insensitive)
    service_key = service.lower()
    if service_key not in service_map:
        return # Jika bukan WhatsApp atau Facebook, tidak disimpan (skip)

    short_service = service_map[service_key]

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        target_folder = os.path.join(parent_dir, 'get')
        file_path = os.path.join(target_folder, 'inline.json')

        if not os.path.exists(target_folder):
            os.makedirs(target_folder, exist_ok=True)

        data_list = []
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data_list = json.load(f)
                except json.JSONDecodeError:
                    data_list = []

        # Cek duplikasi range agar tidak dobel di file
        if any(item['range'] == range_val for item in data_list):
            return

        # Ambil emoji
        emoji_char = get_country_emoji(country_name)

        # Struktur baru sesuai request
        new_entry = {
            "range": range_val, 
            "country": country_name.upper(), 
            "emoji": emoji_char,
            "service": short_service
        }
        
        data_list.append(new_entry)
        
        # Simpan max 10 entry terakhir
        if len(data_list) > 10:
            data_list = data_list[-10:]

        # Simpan ke file
        with open(file_path, 'w', encoding='utf-8') as f:
            # ensure_ascii=False agar emoji terlihat di text editor
            json.dump(data_list, f, indent=2, ensure_ascii=False)
            
        print(f"📂 [JSON] {short_service} Saved: {range_val}")
    except Exception as e:
        print(f"❌ JSON Error: {e}")

def format_live_message(range_val, count, country_name, service, full_message):
    country_emoji = get_country_emoji(country_name)
    range_with_count = f"<code>{range_val}</code> ({count}x)" if count > 1 else f"<code>{range_val}</code>"
    full_message_escaped = full_message.replace('<', '&lt;').replace('>', '&gt;')
    return (
        "🔥Live message new range\n\n" 
        f"📱Range    : {range_with_count}\n"
        f"{country_emoji}Country : {country_name}\n"
        f"⚙️ Service : {service}\n\n" 
        "🗯️Message Available :\n"
        f"<blockquote>{full_message_escaped}</blockquote>"
    )

async def cleanup_old_messages(app):
    global SENT_MESSAGES
    ten_minutes_ago = datetime.now() - timedelta(minutes=10)
    ranges_to_remove = [r for r, d in SENT_MESSAGES.items() if d['timestamp'] < ten_minutes_ago]
    for r in ranges_to_remove:
        del SENT_MESSAGES[r]

async def delete_and_send_telegram_message(app, range_val, country, service, message_text):
    global SENT_MESSAGES
    
    # Panggil fungsi save json yang sudah diupgrade
    save_to_inline_json(range_val, country, service)
    
    reply_markup = create_keyboard() 
    
    try:
        if range_val in SENT_MESSAGES and 'message_id' in SENT_MESSAGES[range_val]:
            old_mid = SENT_MESSAGES[range_val]['message_id']
            try:
                await app.bot.delete_message(chat_id=CHAT_ID, message_id=old_mid)
            except: pass
        
        sent_message = await app.bot.send_message(
            chat_id=CHAT_ID, text=message_text, reply_markup=reply_markup, parse_mode='HTML'
        )
        
        if range_val not in SENT_MESSAGES:
            SENT_MESSAGES[range_val] = {'count': 1}
            
        SENT_MESSAGES[range_val]['message_id'] = sent_message.message_id
        SENT_MESSAGES[range_val]['timestamp'] = datetime.now()
        
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def send_startup_message(app):
    try:
        await app.bot.send_message(chat_id=CHAT_ID, text="✅Ready to check the latest range (Playwright CONSOLE Monitor)", parse_mode='HTML')
    except: pass

# ==================== PLAYWRIGHT/SCRAPER CLASS ====================

class SMSMonitor:
    def __init__(self, url=DASHBOARD_URL): 
        self.url = url
        self.browser = None
        self.page = None
        self.is_logged_in = False 
        self.CONSOLE_SELECTOR = ".group.flex.flex-col.sm\\:flex-row.sm\\:items-start.gap-3.p-3.rounded-lg"
        self.ALLOWED_SERVICES = ['whatsapp', 'facebook']
        self.BANNED_COUNTRIES = ['angola'] 

    async def initialize(self, p_instance):
        try:
            self.browser = await p_instance.chromium.connect_over_cdp(CHROME_DEBUG_URL)
            context = self.browser.contexts[0]
            print(f"🚀 Membuka TAB BARU ke: {self.url}")
            self.page = await context.new_page()
            await self.page.goto(self.url, wait_until='networkidle', timeout=30000)
            print(f"✅ Halaman Dashboard Terbuka.")
        except Exception as e:
            print(f"❌ CDP Error: {e}")
            raise

    async def check_url_login_status(self) -> bool:
        if not self.page: return False
        try:
            self.is_logged_in = self.page.url.startswith("https://x.mnitnetwork.com/mdashboard")
            return self.is_logged_in
        except: return False

    async def fetch_sms(self) -> List[Dict[str, Any]]:
        if not self.page: return []
        if self.page.url != self.url:
            try: await self.page.goto(self.url, wait_until='domcontentloaded', timeout=15000)
            except: return []
                
        try: await self.page.wait_for_selector(self.CONSOLE_SELECTOR, timeout=5000)
        except: return []

        messages = []
        elements = await self.page.locator(self.CONSOLE_SELECTOR).all()

        for element in elements:
            try:
                c_el = element.locator(".flex-shrink-0 .text-\\[10px\\].text-slate-600.mt-1.font-mono")
                c_raw = await c_el.inner_text() if await c_el.count() > 0 else ""
                c_name = re.search(r'•\s*(.*)$', c_raw.strip()).group(1).strip() if "•" in c_raw else "Unknown"
                if c_name.lower() in self.BANNED_COUNTRIES: continue 
                
                s_el = element.locator(".flex-grow.min-w-0 .text-xs.font-bold.text-blue-400")
                s_raw = await s_el.inner_text() if await s_el.count() > 0 else ""
                if not any(a in s_raw.lower() for a in self.ALLOWED_SERVICES): continue
                service = clean_service_name(s_raw)
                
                p_el = element.locator(".flex-grow.min-w-0 .text-\\[10px\\].font-mono")
                p_raw = await p_el.last.inner_text() if await p_el.count() > 0 else "N/A"
                phone = clean_phone_number(p_raw) 
                
                m_el = element.locator(".flex-grow.min-w-0 p")
                m_raw = await m_el.inner_text() if await m_el.count() > 0 else ""
                full_message = m_raw.replace('➜', '').strip()

                if 'XXX' in phone and full_message: 
                    messages.append({"range_key": phone, "country": c_name, "service": service, "raw_message": full_message})
            except: continue
        return messages

monitor = SMSMonitor()

async def monitor_sms_loop(app):
    async with async_playwright() as p:
        await monitor.initialize(p)
        while True:
            try:
                await monitor.check_url_login_status() 
                if monitor.is_logged_in:
                    msgs = await monitor.fetch_sms()
                    new_unique_logs = message_filter.filter(msgs) 

                    if new_unique_logs:
                        for log in new_unique_logs:
                            range_val = log['range_key']
                            if range_val in SENT_MESSAGES:
                                SENT_MESSAGES[range_val]['count'] += 1
                            else:
                                SENT_MESSAGES[range_val] = {'count': 1, 'timestamp': datetime.now()}
                            
                            text = format_live_message(range_val, SENT_MESSAGES[range_val]['count'], log['country'], log['service'], log['raw_message'])
                            await delete_and_send_telegram_message(app, range_val, log['country'], log['service'], text)
                            await asyncio.sleep(0.5) 

                    await cleanup_old_messages(app)
                else:
                    await monitor.page.goto(DASHBOARD_URL)
            except Exception as e:
                print(f"❌ Loop Error: {e}")
            await asyncio.sleep(10)

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    await send_startup_message(app)
    await monitor_sms_loop(app)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
