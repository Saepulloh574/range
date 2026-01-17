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

# ==================== KONFIGURASI ====================

BOT_TOKEN = "8264103317:AAG_-LZQIxrMDIlLlttWQqIvA9xu_GNMwnc"
CHAT_ID = "-1003358198353"
ADMIN_ID = 7184123643 

CHROME_DEBUG_URL = "http://127.0.0.1:9222"
DASHBOARD_URL = "https://x.mnitnetwork.com/mdashboard/console" 

# ==================== GLOBAL STATE & UTILS ====================

SENT_MESSAGES = {} 

class MessageFilter:
    def __init__(self, file='range_cache_mnit.json'): 
        self.file = file
        if os.path.exists(self.file):
            try: os.remove(self.file)
            except: pass
        self.cache = {}

    def key(self, d: Dict[str, Any]) -> str: 
        return f"{d.get('range_key')}_{hash(d.get('raw_message'))}" 
        
    def is_dup(self, d: Dict[str, Any]) -> bool:
        return self.key(d) in self.cache
        
    def add(self, d: Dict[str, Any]):
        self.cache[self.key(d)] = {'timestamp': datetime.now().isoformat()}
        
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

# --- JSON STORAGE LOGIC (Dinamis Path) ---

def save_to_inline_json(range_val, country_name, service):
    """Menyimpan data Facebook ke ../get/inline.json (Max 10 FIFO)"""
    if service.lower() != "facebook":
        return

    # Logika Path: Naik satu tingkat dari folder 'range' ke 'Administrator', lalu masuk ke 'get'
    current_dir = os.path.dirname(os.path.abspath(__file__)) # folder range
    parent_dir = os.path.dirname(current_dir) # folder Administrator
    target_folder = os.path.join(parent_dir, 'get')
    file_path = os.path.join(target_folder, 'inline.json')

    # Pastikan folder 'get' ada
    if not os.path.exists(target_folder):
        os.makedirs(target_folder, exist_ok=True)

    data_list = []
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
        except:
            data_list = []

    # Hindari duplikat range di dalam file
    if any(item['range'] == range_val for item in data_list):
        return

    new_entry = {
        "range": range_val,
        "country": country_name.upper(),
        "emoji": get_country_emoji(country_name)
    }

    data_list.append(new_entry)

    # Batasi 10 data (Hapus yang paling lama/paling atas)
    if len(data_list) > 10:
        data_list = data_list[-10:]

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, indent=2, ensure_ascii=False)
        print(f"📂 [JSON] Update: {file_path}")
    except Exception as e:
        print(f"❌ JSON Error: {e}")

# --- Message Formatter ---

def format_live_message(range_val, count, country_name, service, full_message):
    emoji = get_country_emoji(country_name)
    r_count = f"<code>{range_val}</code> ({count}x)" if count > 1 else f"<code>{range_val}</code>"
    msg_esc = full_message.replace('<', '&lt;').replace('>', '&gt;')
    return (
        "🔥Live message new range\n\n"
        f"📱Range    : {r_count}\n"
        f"{emoji}Country : {country_name}\n"
        f"⚙️ Service : {service}\n\n"
        "🗯️Message Available :\n"
        f"<blockquote>{msg_esc}</blockquote>"
    )

# ==================== ACTIONS ====================

async def delete_and_send_telegram_message(app, range_val, country, service, message_text):
    global SENT_MESSAGES
    
    # Simpan ke file JSON (Hanya Facebook)
    save_to_inline_json(range_val, country, service)
    
    kb = create_keyboard() 
    try:
        if range_val in SENT_MESSAGES:
            old_mid = SENT_MESSAGES[range_val]['message_id']
            try: await app.bot.delete_message(chat_id=CHAT_ID, message_id=old_mid)
            except: pass
                
        sent = await app.bot.send_message(chat_id=CHAT_ID, text=message_text, reply_markup=kb, parse_mode='HTML')
        
        if range_val in SENT_MESSAGES:
            SENT_MESSAGES[range_val]['message_id'] = sent.message_id
        else:
            SENT_MESSAGES[range_val] = {'message_id': sent.message_id, 'count': 1, 'timestamp': datetime.now()}
            
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def cleanup_old_messages():
    global SENT_MESSAGES
    limit = datetime.now() - timedelta(minutes=10)
    to_rem = [r for r, d in SENT_MESSAGES.items() if d['timestamp'] < limit]
    for r in to_rem: del SENT_MESSAGES[r]

# ==================== SCRAPER ====================

class SMSMonitor:
    def __init__(self): 
        self.url = DASHBOARD_URL
        self.page = None
        self.is_logged_in = False 
        self.SELECTOR = ".group.flex.flex-col.sm\\:flex-row.sm\\:items-start.gap-3.p-3.rounded-lg"
        self.ALLOWED = ['whatsapp', 'facebook']
        self.BANNED = ['angola'] 

    async def initialize(self, p_instance):
        browser = await p_instance.chromium.connect_over_cdp(CHROME_DEBUG_URL)
        context = browser.contexts[0]
        self.page = context.pages[0] if context.pages else await context.new_page()

    async def fetch_sms(self) -> List[Dict[str, Any]]:
        if not self.page: return []
        if self.page.url != self.url:
            try: await self.page.goto(self.url, wait_until='networkidle', timeout=15000)
            except: return []
                
        try: await self.page.wait_for_selector(self.SELECTOR, timeout=10000)
        except: return []

        results = []
        elements = await self.page.locator(self.SELECTOR).all()

        for el in elements:
            try:
                # Country
                c_el = el.locator(".flex-shrink-0 .text-\\[10px\\].text-slate-600.mt-1.font-mono")
                c_raw = await c_el.inner_text() if await c_el.count() > 0 else ""
                c_name = re.search(r'•\s*(.*)$', c_raw.strip()).group(1).strip() if "•" in c_raw else "Unknown"
                if c_name.lower() in self.BANNED: continue 
                
                # Service
                s_el = el.locator(".flex-grow.min-w-0 .text-xs.font-bold.text-blue-400")
                s_raw = await s_el.inner_text() if await s_el.count() > 0 else ""
                if not any(a in s_raw.lower() for a in self.ALLOWED): continue
                service = clean_service_name(s_raw)
                
                # Phone
                p_el = el.locator(".flex-grow.min-w-0 .text-\\[10px\\].text-slate-500.font-mono")
                phone = clean_phone_number(await p_el.inner_text() if await p_el.count() > 0 else "")
                
                # Message
                m_el = el.locator(".flex-grow.min-w-0 p")
                msg = (await m_el.inner_text()).replace('➜', '').strip()

                if 'XXX' in phone and msg: 
                    results.append({"range_key": phone, "country": c_name, "service": service, "raw_message": msg})
            except: continue
        return results

monitor = SMSMonitor()

# ==================== MAIN ====================

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    print("🤖 Monitoring Started...")
    
    async with async_playwright() as p:
        await monitor.initialize(p)
        while True:
            try:
                msgs = await monitor.fetch_sms()
                new_logs = message_filter.filter(msgs) 

                if new_logs:
                    # Ambil data unik per range terbaru saja
                    grouped = {log['range_key']: log for log in new_logs}
                    for r_val, log in grouped.items():
                        if r_val in SENT_MESSAGES:
                            SENT_MESSAGES[r_val]['count'] += 1
                            SENT_MESSAGES[r_val]['timestamp'] = datetime.now()
                        
                        current_count = SENT_MESSAGES.get(r_val, {}).get('count', 1)
                        text = format_live_message(r_val, current_count, log['country'], log['service'], log['raw_message'])
                        await delete_and_send_telegram_message(app, r_val, log['country'], log['service'], text)
                        await asyncio.sleep(0.5) 

                await cleanup_old_messages()
            except Exception as e: print(f"Loop Error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
