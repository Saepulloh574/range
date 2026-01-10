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
BOT_TOKEN = "8558006836:AAGR3N4DwXYSlpOxjRvjZcPAmC1CUWRJexY"
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
        
        # +++++ KOREKSI DI SINI: HAPUS CACHE SAAT STARTUP +++++
        if os.path.exists(self.file):
            try:
                os.remove(self.file)
                print(f"🗑️ Cache lama '{self.file}' berhasil dihapus saat startup.")
            except Exception as e:
                print(f"❌ Gagal menghapus cache saat startup: {e}")
        # +++++++++++++++++++++++++++++++++++++++++++++++++++++
        
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
            # Karena cache sudah dihapus di awal, ini hanya memastikan file kosong ditulis
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
    # === BAWAAN (WAJIB, JANGAN DIUBAH) ===
    "NEPAL": "🇳🇵",
    "IVORY COAST": "🇨🇮",
    "GUINEA": "🇬🇳",
    "CENTRAL AFRIKA": "🇨🇫",
    "TOGO": "🇹🇬",
    "TAJIKISTAN": "🇹🇯",
    "BENIN": "🇧🇯",
    "SIERRA LEONE": "🇸🇱",
    "MADAGASCAR": "🇲🇬",
    "AFGANISTAN": "🇦🇫",
    "INDONESIA": "🇮🇩",
    "UNITED STATES": "🇺🇸",
    "ANGOLA": "🇦🇴",
    "CAMEROON": "🇨🇲",
    "MOZAMBIQUE": "🇲🇿",
    "PERU": "🇵🇪",
    "VIETNAM": "🇻🇳",

    # === TAMBAHAN NEGARA LAIN ===
    "AFGHANISTAN": "🇦🇫",
    "ALBANIA": "🇦🇱",
    "ALGERIA": "🇩🇿",
    "ANDORRA": "🇦🇩",
    "ANTIGUA AND BARBUDA": "🇦🇬",
    "ARGENTINA": "🇦🇷",
    "ARMENIA": "🇦🇲",
    "AUSTRALIA": "🇦🇺",
    "AUSTRIA": "🇦🇹",
    "AZERBAIJAN": "🇦🇿",

    "BAHAMAS": "🇧🇸",
    "BAHRAIN": "🇧🇭",
    "BANGLADESH": "🇧🇩",
    "BARBADOS": "🇧🇧",
    "BELARUS": "🇧🇾",
    "BELGIUM": "🇧🇪",
    "BELIZE": "🇧🇿",
    "BHUTAN": "🇧🇹",
    "BOLIVIA": "🇧🇴",
    "BOSNIA AND HERZEGOVINA": "🇧🇦",
    "BOTSWANA": "🇧🇼",
    "BRAZIL": "🇧🇷",
    "BRUNEI": "🇧🇳",
    "BULGARIA": "🇧🇬",
    "BURKINA FASO": "🇧🇫",
    "BURUNDI": "🇧🇮",

    "CAMBODIA": "🇰🇭",
    "CANADA": "🇨🇦",
    "CAPE VERDE": "🇨🇻",
    "CENTRAL AFRICAN REPUBLIC": "🇨🇫",
    "CHAD": "🇹🇩",
    "CHILE": "🇨🇱",
    "CHINA": "🇨🇳",
    "COLOMBIA": "🇨🇴",
    "COMOROS": "🇰🇲",
    "CONGO": "🇨🇬",
    "COSTA RICA": "🇨🇷",
    "CROATIA": "🇭🇷",
    "CUBA": "🇨🇺",
    "CYPRUS": "🇨🇾",
    "CZECH REPUBLIC": "🇨🇿",

    "DENMARK": "🇩🇰",
    "DJIBOUTI": "🇩🇯",
    "DOMINICA": "🇩🇲",
    "DOMINICAN REPUBLIC": "🇩🇴",

    "ECUADOR": "🇪🇨",
    "EGYPT": "🇪🇬",
    "EL SALVADOR": "🇸🇻",
    "EQUATORIAL GUINEA": "🇬🇶",
    "ERITREA": "🇪🇷",
    "ESTONIA": "🇪🇪",
    "ESWATINI": "🇸🇿",
    "ETHIOPIA": "🇪🇹",

    "FIJI": "🇫🇯",
    "FINLAND": "🇫🇮",
    "FRANCE": "🇫🇷",

    "GABON": "🇬🇦",
    "GAMBIA": "🇬🇲",
    "GEORGIA": "🇬🇪",
    "GERMANY": "🇩🇪",
    "GHANA": "🇬🇭",
    "GREECE": "🇬🇷",
    "GRENADA": "🇬🇩",
    "GUATEMALA": "🇬🇹",
    "GUINEA-BISSAU": "🇬🇼",
    "GUYANA": "🇬🇾",

    "HAITI": "🇭🇹",
    "HONDURAS": "🇭🇳",
    "HUNGARY": "🇭🇺",

    "ICELAND": "🇮🇸",
    "INDIA": "🇮🇳",
    "IRAN": "🇮🇷",
    "IRAQ": "🇮🇶",
    "IRELAND": "🇮🇪",
    "ISRAEL": "🇮🇱",
    "ITALY": "🇮🇹",

    "JAMAICA": "🇯🇲",
    "JAPAN": "🇯🇵",
    "JORDAN": "🇯🇴",

    "KAZAKHSTAN": "🇰🇿",
    "KENYA": "🇰🇪",
    "KIRIBATI": "🇰🇮",
    "KUWAIT": "🇰🇼",
    "KYRGYZSTAN": "🇰🇬",

    "LAOS": "🇱🇦",
    "LATVIA": "🇱🇻",
    "LEBANON": "🇱🇧",
    "LESOTHO": "🇱🇸",
    "LIBERIA": "🇱🇷",
    "LIBYA": "🇱🇾",
    "LIECHTENSTEIN": "🇱🇮",
    "LITHUANIA": "🇱🇹",
    "LUXEMBOURG": "🇱🇺",

    "MALAWI": "🇲🇼",
    "MALAYSIA": "🇲🇾",
    "MALDIVES": "🇲🇻",
    "MALI": "🇲🇱",
    "MALTA": "🇲🇹",
    "MARSHALL ISLANDS": "🇲🇭",
    "MAURITANIA": "🇲🇷",
    "MAURITIUS": "🇲🇺",
    "MEXICO": "🇲🇽",
    "MICRONESIA": "🇫🇲",
    "MOLDOVA": "🇲🇩",
    "MONACO": "🇲🇨",
    "MONGOLIA": "🇲🇳",
    "MONTENEGRO": "🇲🇪",
    "MOROCCO": "🇲🇦",
    "MYANMAR": "🇲🇲",

    "NAMIBIA": "🇳🇦",
    "NAURU": "🇳🇷",
    "NETHERLANDS": "🇳🇱",
    "NEW ZEALAND": "🇳🇿",
    "NICARAGUA": "🇳🇮",
    "NIGER": "🇳🇪",
    "NIGERIA": "🇳🇬",
    "NORTH KOREA": "🇰🇵",
    "NORTH MACEDONIA": "🇲🇰",
    "NORWAY": "🇳🇴",

    "OMAN": "🇴🇲",

    "PAKISTAN": "🇵🇰",
    "PALAU": "🇵🇼",
    "PANAMA": "🇵🇦",
    "PAPUA NEW GUINEA": "🇵🇬",
    "PARAGUAY": "🇵🇾",
    "PHILIPPINES": "🇵🇭",
    "POLAND": "🇵🇱",
    "PORTUGAL": "🇵🇹",
    "QATAR": "🇶🇦",

    "ROMANIA": "🇷🇴",
    "RUSSIA": "🇷🇺",
    "RWANDA": "🇷🇼",

    "SAUDI ARABIA": "🇸🇦",
    "SENEGAL": "🇸🇳",
    "SERBIA": "🇷🇸",
    "SEYCHELLES": "🇸🇨",
    "SINGAPORE": "🇸🇬",
    "SLOVAKIA": "🇸🇰",
    "SLOVENIA": "🇸🇮",
    "SOLOMON ISLANDS": "🇸🇧",
    "SOMALIA": "🇸🇴",
    "SOUTH AFRICA": "🇿🇦",
    "SOUTH KOREA": "🇰🇷",
    "SOUTH SUDAN": "🇸🇸",
    "SPAIN": "🇪🇸",
    "SRI LANKA": "🇱🇰",
    "SUDAN": "🇸🇩",
    "SURINAME": "🇸🇷",
    "SWEDEN": "🇸🇪",
    "SWITZERLAND": "🇨🇭",
    "SYRIA": "🇸🇾",

    "TAIWAN": "🇹🇼",
    "TANZANIA": "🇹🇿",
    "THAILAND": "🇹🇭",
    "TONGA": "🇹🇴",
    "TRINIDAD AND TOBAGO": "🇹🇹",
    "TUNISIA": "🇹🇳",
    "TURKEY": "🇹🇷",
    "TURKMENISTAN": "🇹🇲",
    "TUVALU": "🇹🇻",

    "UGANDA": "🇺🇬",
    "UKRAINE": "🇺🇦",
    "UNITED ARAB EMIRATES": "🇦🇪",
    "UNITED KINGDOM": "🇬🇧",
    "URUGUAY": "🇺🇾",
    "UZBEKISTAN": "🇺🇿",

    "VANUATU": "🇻🇺",
    "VATICAN CITY": "🇻🇦",
    "VENEZUELA": "🇻🇪",

    "YEMEN": "🇾🇪",
    "ZAMBIA": "🇿🇲",
    "ZIMBABWE": "🇿🇼",
}

def clean_phone_number(phone):
    if not phone: return "N/A"
    cleaned = re.sub(r'[^\d+X]', '', phone) 
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
    keyboard = [
        [
            InlineKeyboardButton("📞GetNumber", url="https://t.me/myzuraisgoodbot?start=ZuraBot"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_live_message(range_val, count, country_name, service, full_message):
    """Format pesan Telegram dengan perataan kolon dan counter."""
    country_emoji = get_country_emoji(country_name)
    
    formatted_range = format_phone_number(range_val)
    
    range_with_count = f"<code>{formatted_range}</code> ({count}x)" if count > 1 else f"<code>{formatted_range}</code>"
    full_message_escaped = full_message.replace('<', '&lt;').replace('>', '&gt;')
    
    # Menggunakan spasi untuk perataan (jika di-render di Telegram dengan font monospaced)
    message = (
        "🔥Live message new range\n"
        "\n" 
        f"📱Range    : {range_with_count}\n"
        f"{country_emoji}Country : {country_name}\n"
        f"⚙️ Service : {service}\n"
        "\n" 
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


# FUNGSI BARU: DELETE PESAN LAMA DAN KIRIM ULANG PESAN BARU
async def delete_and_send_telegram_message(app, range_val, country, service, message_text):
    global SENT_MESSAGES
    reply_markup = create_keyboard() 
    
    try:
        if range_val in SENT_MESSAGES:
            # Langkah 1: Hapus pesan lama
            message_id = SENT_MESSAGES[range_val]['message_id']
            try:
                await app.bot.delete_message(
                    chat_id=CHAT_ID,
                    message_id=message_id
                )
                print(f"✅ Berhasil menghapus pesan lama ({message_id}) untuk Range: {range_val}")
            except Exception as delete_e:
                if 'Message to delete not found' not in str(delete_e):
                    print(f"❌ Gagal menghapus pesan Telegram lama: {delete_e}")
                
            # Langkah 2: Kirim pesan baru
            sent_message = await app.bot.send_message(
                chat_id=CHAT_ID,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            # Langkah 3: Update message_id di SENT_MESSAGES
            SENT_MESSAGES[range_val]['message_id'] = sent_message.message_id
            
        else:
            # Kirim pesan baru (untuk range yang baru pertama kali muncul)
            sent_message = await app.bot.send_message(
                chat_id=CHAT_ID,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            # Tambahkan ke tracking
            SENT_MESSAGES[range_val] = {
                'message_id': sent_message.message_id,
                'count': 1, 
                'timestamp': datetime.now()
            }
            
    except Exception as e:
        print(f"❌ Gagal mengirim pesan Telegram baru setelah penghapusan: {e}")

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

# ==================== PLAYWRIGHT/SCRAPER CLASS ====================

class SMSMonitor:
    
    def __init__(self, url=DASHBOARD_URL): 
        self.url = url
        self.browser = None
        self.page = None
        self.is_logged_in = False 
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
                await self.page.goto(self.url, wait_until='networkidle', timeout=15000)
            except Exception as e:
                print(f"❌ Error navigating to console dashboard: {e}")
                return []
                
        try:
            await self.page.wait_for_selector(self.CONSOLE_SELECTOR, timeout=10000)
        except PlaywrightTimeoutError: 
             print("❌ Timeout saat menunggu blok data konsol.")
             return []

        messages = []
        elements = await self.page.locator(self.CONSOLE_SELECTOR).all()

        for element in elements:
            try:
                # 1. Service
                service_element = element.locator(".flex-grow.min-w-0 .text-xs.font-bold.text-blue-400")
                service_text = await service_element.inner_text() if await service_element.count() > 0 else "N/A"
                service = clean_service_name(service_text)
                
                # 2. Range/Phone (Nomor Penuh XXX)
                phone_element = element.locator(".flex-grow.min-w-0 .text-\\[10px\\].text-slate-500.font-mono")
                phone_raw = await phone_element.inner_text() if await phone_element.count() > 0 else "N/A"
                phone = clean_phone_number(phone_raw) 

                # 3. Country
                country_element = element.locator(".flex-shrink-0 .text-\\[10px\\].text-slate-600.mt-1.font-mono")
                country_full = await country_element.inner_text() if await country_element.count() > 0 else ""
                country_match = re.search(r'•\s*(.*)$', country_full.strip())
                country_name = country_match.group(1).strip() if country_match else "Unknown"
                
                # 4. Message (FULL)
                message_element = element.locator(".flex-grow.min-w-0 p")
                message_text = await message_element.inner_text() if await message_element.count() > 0 else ""
                full_message = message_text.replace('➜', '').strip()

                if 'XXX' in phone and full_message: 
                    messages.append({
                        "range_key": phone, 
                        "country": country_name,
                        "service": service,
                        "raw_message": full_message 
                    })
            except Exception as e:
                print(f"⚠️ Error memproses satu blok konsol: {e}")
                continue
                
        return messages

monitor = SMSMonitor()

# ==================== MAIN LOOP DENGAN LOGIKA DELETE & SEND ====================

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
                    
                    # A. Ambil data SMS
                    msgs = await monitor.fetch_sms()
                    
                    # B. Filter pesan baru (Nomor Penuh XXX + Isi Pesan)
                    new_unique_logs = message_filter.filter(msgs) 

                    if new_unique_logs:
                        print(f"✅ Ditemukan {len(new_unique_logs)} log unik baru. Memproses Live Counter (Delete & Send)...")
                        
                        # C. Proses Live Counter: Kelompokkan berdasarkan Range Key (Nomor Penuh XXX)
                        grouped_logs = {}
                        for log in new_unique_logs:
                            grouped_logs[log['range_key']] = log 
                        
                        print(f"📦 Mengelompokkan ke {len(grouped_logs)} Range unik untuk diproses.")

                        for range_val, log in grouped_logs.items():
                            
                            last_message = log['raw_message'] 
                            
                            # Logika Peningkatan Counter (berjalan jika range_val ada di SENT_MESSAGES)
                            if range_val in SENT_MESSAGES:
                                old_data = SENT_MESSAGES[range_val]
                                new_count = old_data['count'] + 1
                                SENT_MESSAGES[range_val]['count'] = new_count
                                SENT_MESSAGES[range_val]['timestamp'] = datetime.now()
                            else:
                                new_count = 1

                            # Siapkan pesan
                            message_text = format_live_message(
                                range_val, new_count, log['country'], log['service'], last_message
                            )
                            
                            # Panggil fungsi DELETE & SEND
                            await delete_and_send_telegram_message(app, range_val, log['country'], log['service'], message_text)
                            
                            await asyncio.sleep(0.5) 

                    # D. Bersihkan pesan lama (hapus dari tracking SENT_MESSAGES setelah 10 menit)
                    await cleanup_old_messages(app)
                    
                    # E. Refresh halaman
                    if monitor.page:
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

            # Waktu tunggu antara cek (10 detik)
            await asyncio.sleep(10)

# ==================== START EXECUTION ====================

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
