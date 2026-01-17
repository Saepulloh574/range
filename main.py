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

# ==================== KONFIGURASI ====================

BOT_TOKEN = "8264103317:AAG_-LZQIxrMDIlLlttWQqIvA9xu_GNMwnc"
CHAT_ID = "-1003358198353"
ADMIN_ID = 7184123643 

CHROME_DEBUG_URL = "http://127.0.0.1:9222"
DASHBOARD_URL = "https://x.mnitnetwork.com/mdashboard/console" 
LOGIN_URL = "https://x.mnitnetwork.com/mauth/login" 

# ==================== GLOBAL STATE & UTILS ====================

SENT_MESSAGES = {} 
GLOBAL_ASYNC_LOOP = None 

class MessageFilter:
    CLEANUP_KEY = '__LAST_CLEANUP_GMT__' 
    def __init__(self, file='range_cache_mnit.json'): 
        self.file = file
        if os.path.exists(self.file):
            try:
                os.remove(self.file)
                print(f"🗑️ Cache lama '{self.file}' dihapus.")
            except: pass
        
        self.cache = self._load() 
        self.last_cleanup_date_gmt = self.cache.pop(self.CLEANUP_KEY, '19700101') 
        self._cleanup() 
        
    def _load(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.file) and os.stat(self.file).st_size > 0:
            try:
                with open(self.file, 'r') as f: return json.load(f)
            except: return {}
        return {}
        
    def _save(self): 
        temp_cache = self.cache.copy()
        temp_cache[self.CLEANUP_KEY] = self.last_cleanup_date_gmt
        try:
             json.dump(temp_cache, open(self.file,'w'), indent=2)
        except: pass
    
    def _cleanup(self):
        now_gmt = datetime.now(timezone.utc).strftime('%Y%m%d')
        if now_gmt > self.last_cleanup_date_gmt:
            self.cache = {} 
            self.last_cleanup_date_gmt = now_gmt
        self._save()
        
    def key(self, d: Dict[str, Any]) -> str: 
        return f"{d.get('range_key')}_{hash(d.get('raw_message'))}" 
        
    def is_dup(self, d: Dict[str, Any]) -> bool:
        self._cleanup() 
        key = self.key(d)
        return key in self.cache
        
    def add(self, d: Dict[str, Any]):
        key = self.key(d)
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
    "GEORGIA": "🇬🇪"
}

def get_country_emoji(country_name: str) -> str:
    return COUNTRY_EMOJI.get(country_name.strip().upper(), "🇹🇾")

def clean_phone_number(phone):
    if not phone: return "N/A"
    return re.sub(r'[^\d+X]', '', phone) or phone

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
    return service.strip().title()

def create_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("📞GetNumber", url="https://t.me/myzuraisgoodbot?start=ZuraBot")]])

# --- JSON STORAGE LOGIC (Facebook Only - Max 10) ---

def save_to_inline_json(range_val, country_name, service):
    """Menyimpan data Facebook ke get/inline.json dengan sistem FIFO limit 10."""
    if service.lower() != "facebook":
        return

    file_path = 'get/inline.json'
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    data_list = []
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
        except:
            data_list = []

    # Cek duplikat di file
    if any(item['range'] == range_val for item in data_list):
        return

    # Entry Baru
    new_entry = {
        "range": range_val,
        "country": country_name.upper(),
        "emoji": get_country_emoji(country_name)
    }

    data_list.append(new_entry)

    # FIFO: Jika > 10, ambil 10 terbaru (buang yang paling atas)
    if len(data_list) > 10:
        data_list = data_list[-10:]

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, indent=2, ensure_ascii=False)
        print(f"📂 [JSON] Saved Facebook Range: {range_val}")
    except Exception as e:
        print(f"❌ Error Saving JSON: {e}")

# --- Message Formatter ---

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

# ==================== CORE ACTIONS ====================

async def delete_and_send_telegram_message(app, range_val, country, service, message_text):
    global SENT_MESSAGES
    
    # Simpan ke JSON jika Facebook
    save_to_inline_json(range_val, country, service)
    
    reply_markup = create_keyboard() 
    try:
        if range_val in SENT_MESSAGES:
            message_id = SENT_MESSAGES[range_val]['message_id']
            try:
                await app.bot.delete_message(chat_id=CHAT_ID, message_id=message_id)
            except: pass
                
            sent_message = await app.bot.send_message(
                chat_id=CHAT_ID, text=message_text, reply_markup=reply_markup, parse_mode='HTML'
            )
            SENT_MESSAGES[range_val]['message_id'] = sent_message.message_id
        else:
            sent_message = await app.bot.send_message(
                chat_id=CHAT_ID, text=message_text, reply_markup=reply_markup, parse_mode='HTML'
            )
            SENT_MESSAGES[range_val] = {
                'message_id': sent_message.message_id,
                'count': 1, 
                'timestamp': datetime.now()
            }
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def cleanup_old_messages(app):
    global SENT_MESSAGES
    limit = datetime.now() - timedelta(minutes=10)
    to_remove = [r for r, d in SENT_MESSAGES.items() if d['timestamp'] < limit]
    for r in to_remove: del SENT_MESSAGES[r]

# ==================== SCRAPER CLASS ====================

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
        self.browser = await p_instance.chromium.connect_over_cdp(CHROME_DEBUG_URL)
        context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        self.page = context.pages[0] if context.pages else await context.new_page()

    async def check_url_login_status(self) -> bool:
        try:
            self.is_logged_in = self.page.url.startswith("https://x.mnitnetwork.com/mdashboard")
            return self.is_logged_in
        except: return False

    async def fetch_sms(self) -> List[Dict[str, Any]]:
        if not self.page or not self.is_logged_in: return []
        if self.page.url != self.url:
            try: await self.page.goto(self.url, wait_until='networkidle', timeout=15000)
            except: return []
                
        try: await self.page.wait_for_selector(self.CONSOLE_SELECTOR, timeout=10000)
        except: return []

        messages = []
        elements = await self.page.locator(self.CONSOLE_SELECTOR).all()

        for element in elements:
            try:
                # Country Filter
                country_element = element.locator(".flex-shrink-0 .text-\\[10px\\].text-slate-600.mt-1.font-mono")
                country_full = await country_element.inner_text() if await country_element.count() > 0 else ""
                country_match = re.search(r'•\s*(.*)$', country_full.strip())
                country_name = country_match.group(1).strip() if country_match else "Unknown"
                
                if country_name.lower() in self.BANNED_COUNTRIES: continue 
                
                # Service Filter
                service_element = element.locator(".flex-grow.min-w-0 .text-xs.font-bold.text-blue-400")
                service_raw = await service_element.inner_text() if await service_element.count() > 0 else "N/A"
                if not any(a in service_raw.lower() for a in self.ALLOWED_SERVICES): continue
                
                service = clean_service_name(service_raw)
                
                # Phone & Msg
                phone_element = element.locator(".flex-grow.min-w-0 .text-\\[10px\\].text-slate-500.font-mono")
                phone = clean_phone_number(await phone_element.inner_text() if await phone_element.count() > 0 else "N/A")
                
                message_element = element.locator(".flex-grow.min-w-0 p")
                full_message = (await message_element.inner_text()).replace('➜', '').strip()

                if 'XXX' in phone and full_message: 
                    messages.append({
                        "range_key": phone, "country": country_name,
                        "service": service, "raw_message": full_message 
                    })
            except: continue
        return messages

monitor = SMSMonitor()

# ==================== MAIN LOOP ====================

async def monitor_sms_loop(app):
    async with async_playwright() as p:
        try: await monitor.initialize(p)
        except: return 
        
        while True:
            try:
                await monitor.check_url_login_status() 
                if monitor.is_logged_in:
                    msgs = await monitor.fetch_sms()
                    new_logs = message_filter.filter(msgs) 

                    if new_logs:
                        # Group by range to handle multiple unique messages at once
                        grouped = {}
                        for log in new_logs: grouped[log['range_key']] = log 

                        for range_val, log in grouped.items():
                            if range_val in SENT_MESSAGES:
                                SENT_MESSAGES[range_val]['count'] += 1
                                SENT_MESSAGES[range_val]['timestamp'] = datetime.now()
                            else:
                                pass # initialized in send function
                            
                            count = SENT_MESSAGES.get(range_val, {}).get('count', 1)
                            text = format_live_message(range_val, count, log['country'], log['service'], log['raw_message'])
                            await delete_and_send_telegram_message(app, range_val, log['country'], log['service'], text)
                            await asyncio.sleep(0.5) 

                    await cleanup_old_messages(app)
                else:
                    try: await monitor.page.goto(DASHBOARD_URL, timeout=5000)
                    except: pass
            except Exception as e:
                print(f"Loop Error: {e}")
            await asyncio.sleep(10)

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    print("🤖 Bot Started.")
    await monitor_sms_loop(app)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: print("Offline.")
