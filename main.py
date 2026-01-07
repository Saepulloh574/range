import asyncio
import os
import re
from datetime import datetime, timedelta
# Menghapus: from dotenv import load_dotenv

# Pyppeteer
from pyppeteer import launch
from pyppeteer.errors import TimeoutError

# Telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder

# ==================== KONFIGURASI DENGAN NILAI TETAP ====================

# Konfigurasi Telegram
BOT_TOKEN = "7777855547:AAGTwJ01fjxjbd2TLJd8wmSEmUabD_yu2G4"
CHAT_ID = "-1003358198353"

# Konfigurasi Chrome/Pyppeteer
# INI HARUS DIGANTI DENGAN NILAI WEBSOCKET DARI CHROME DEBUG ANDA
CHROME_DEBUG_URL = "ws://127.0.0.1:9222/devtools/browser/ab1c30b4-37a6-44fe-b8b4-9f5e9e56c103"

# URL Target untuk Scraping
TARGET_URL = "https://x.mnitnetwork.com/mdashboard/console" 

# Jalur Chrome Executable (Penting untuk menghindari error unduhan Chromium)
CHROME_EXECUTABLE_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
# Pastikan jalur ini benar di sistem Windows Anda!
# ========================================================================


# Dictionary negara ke emoji (Dibiarkan sama)
COUNTRY_EMOJI = {
    "AFGHANISTAN": "🇦🇫", "ALBANIA": "🇦🇱", "ALGERIA": "🇩🇿", "ANDORRA": "🇦🇩", "ANGOLA": "🇦🇴",
    "ANTIGUA AND BARBUDA": "🇦🇬", "ARGENTINA": "🇦🇷", "ARMENIA": "🇦🇲", "AUSTRALIA": "🇦🇺", "AUSTRIA": "🇦🇹",
    "AZERBAIJAN": "🇦🇿", "BAHAMAS": "🇧🇸", "BAHRAIN": "🇧🇭", "BANGLADESH": "🇧🇩", "BARBADOS": "🇧🇧",
    "BELARUS": "🇧🇾", "BELGIUM": "🇧🇪", "BELIZE": "🇧🇿", "BENIN": "🇧🇯", "BHUTAN": "🇧🇹",
    "BOLIVIA": "🇧🇴", "BOSNIA AND HERZEGOVINA": "🇧🇦", "BOTSWANA": "🇧🇼", "BRAZIL": "🇧🇷", "BRUNEI": "🇧🇳",
    "BULGARIA": "🇧🇬", "BURKINA FASO": "🇧🇫", "BURUNDI": "🇧🇮", "CAMBODIA": "🇰🇭", "CAMEROON": "🇨🇲",
    "CANADA": "🇨🇦", "CAPE VERDE": "🇨🇻", "CENTRAL AFRICAN REPUBLIC": "🇨🇫", "CHAD": "🇹🇩", "CHILE": "🇨🇱",
    "CHINA": "🇨🇳", "COLOMBIA": "🇨🇴", "COMOROS": "🇰🇲", "CONGO": "🇨🇬", "COSTA RICA": "🇨🇷",
    "CROATIA": "🇭🇷", "CUBA": "🇨🇺", "CYPRUS": "🇨🇾", "CZECH REPUBLIC": "🇨🇿", "IVORY COAST": "🇨🇮",
    "DENMARK": "🇩🇰", "DJIBOUTI": "🇩🇯", "DOMINICA": "🇩🇲", "DOMINICAN REPUBLIC": "🇩🇴", "ECUADOR": "🇪🇨",
    "EGYPT": "🇪🇬", "EL SALVADOR": "🇸🇻", "EQUATORIAL GUINEA": "🇬🇶", "ERITREA": "🇪🇷", "ESTONIA": "🇪🇪",
    "ESWATINI": "🇸🇿", "ETHIOPIA": "🇪🇹", "FIJI": "🇫🇯", "FINLAND": "🇫🇮", "FRANCE": "🇫🇷",
    "GERMANY": "🇩🇪", "GHANA": "🇬🇭", "GREECE": "🇬🇷", "GUATEMALA": "🇬🇹", "GUINEA": "🇬🇳",
    "GUINEA-BISSAU": "🇬🇼", "GUYANA": "🇬🇾", "HAITI": "🇭🇹", "HONDURAS": "🇭🇳", "HUNGARY": "🇭🇺",
    "ICELAND": "🇮🇸", "INDIA": "🇮🇳", "INDONESIA": "🇮🇩", "IRAN": "🇮🇶", "IRAQ": "🇮🇶",
    "IRELAND": "🇮🇪", "ISRAEL": "🇮🇱", "ITALY": "🇮🇹", "JAPAN": "🇯🇵", "JORDAN": "🇯🇴",
    "KAZAKHSTAN": "🇰🇿", "KENYA": "🇰🇪", "KUWAIT": "🇰🇼", "LAOS": "🇱🇦", "LATVIA": "🇱🇻",
    "LEBANON": "🇱🇧", "LIBYA": "🇱🇾", "LITHUANIA": "🇱🇹", "LUXEMBOURG": "🇱🇺",
    "MALAYSIA": "🇲🇾", "MEXICO": "🇲🇽", "MONGOLIA": "🇲🇳", "MOROCCO": "🇲🇦",
    "MYANMAR": "🇲🇲", "NEPAL": "🇳🇵", "NETHERLANDS": "🇳🇱", "NEW ZEALAND": "🇳🇿",
    "NIGERIA": "🇳🇬", "NORTH KOREA": "🇰🇵", "NORWAY": "🇳🇴",
    "PAKISTAN": "🇵🇰", "PHILIPPINES": "🇵🇭", "POLAND": "🇵🇱", "PORTUGAL": "🇵🇹",
    "QATAR": "🇶🇦", "ROMANIA": "🇷🇴", "RUSSIA": "🇷🇺", "SAUDI ARABIA": "🇸🇦",
    "SINGAPORE": "🇸🇬", "SOUTH AFRICA": "🇿🇦", "SOUTH KOREA": "🇰🇷",
    "SPAIN": "🇪🇸", "SRI LANKA": "🇱🇰", "SWEDEN": "🇸🇪", "SWITZERLAND": "🇨🇭",
    "THAILAND": "🇹🇭", "TURKEY": "🇹🇷", "UKRAINE": "🇺🇦",
    "UNITED KINGDOM": "🇬🇧", "UNITED STATES": "🇺🇸",
    "VIETNAM": "🇻🇳", "YEMEN": "🇾🇪", "ZIMBABWE": "🇿🇼"
}

def get_country_emoji(country_name: str) -> str:
    """Mengembalikan emoji bendera negara."""
    return COUNTRY_EMOJI.get(country_name.upper(), "❓")

def format_telegram_message(range_val, count, country_name, service, full_message):
    """Membuat teks pesan Telegram dengan format yang diminta."""
    country_emoji = get_country_emoji(country_name)
    range_with_count = f"<code>{range_val}</code> ({count}x)" if count > 1 else f"<code>{range_val}</code>"
    message = (
        "🔥Live message new range\n"
        f"📱Range: {range_with_count}\n"
        f"{country_emoji}Country: {country_name}\n"
        f"⚙️ Service: {service}\n"
        "🗯️Message Available :\n"
        f"<blockquote>{full_message}</blockquote>"
    )
    return message

def create_keyboard():
    """Membuat keyboard inline untuk pesan Telegram."""
    keyboard = [
        [
            InlineKeyboardButton("📞GetNumber", url="https://t.me/myzuraisgoodbot?start=ZuraBot"),
            InlineKeyboardButton("👤Admin", url="https://t.me/Imr1d")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

SENT_MESSAGES = {}

async def send_or_edit_telegram_message(app, range_val, country, service, message_text, is_new_entry):
    """Mengirim pesan baru atau mengedit pesan yang sudah ada di Telegram."""
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
            print(f"✅ Pesan di-edit untuk range: {range_val} (Count: {SENT_MESSAGES[range_val]['count']})")
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
            print(f"✅ Pesan baru terkirim untuk range: {range_val}")
    except Exception as e:
        print(f"❌ Gagal mengirim/mengedit pesan Telegram: {e}")

async def cleanup_old_messages(app):
    """Menghapus pesan dari SENT_MESSAGES jika sudah lebih dari 10 menit tanpa update."""
    global SENT_MESSAGES
    ten_minutes_ago = datetime.now() - timedelta(minutes=10)
    
    ranges_to_remove = []
    for range_val, data in SENT_MESSAGES.items():
        if data['timestamp'] < ten_minutes_ago:
            ranges_to_remove.append(range_val)
            print(f"🧹 Range {range_val} (Count: {data['count']}) sudah lebih dari 10 menit, menghapus dari pelacakan.")
            
    for range_val in ranges_to_remove:
        del SENT_MESSAGES[range_val]

async def send_startup_message(app):
    """Mengirim pesan status saat skrip berhasil terhubung ke bot."""
    # Verifikasi apakah CHAT_ID dan BOT_TOKEN ada sebelum mengirim
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Konfigurasi Telegram hilang, tidak bisa mengirim pesan startup.")
        return
        
    try:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="✅Ready to check the latest range",
            parse_mode='HTML'
        )
        print("✅ Pesan startup terkirim.")
    except Exception as e:
        print(f"❌ Gagal mengirim pesan startup: {e}")

async def scrape_and_send(app):
    """Fungsi utama untuk scraping dan pengiriman pesan."""
    global SENT_MESSAGES
    
    if not CHROME_DEBUG_URL or not TARGET_URL:
        print("❌ Pastikan CHROME_DEBUG_URL dan TARGET_URL sudah diset di bagian KONFIGURASI.")
        return

    try:
        # Koneksi ke Chrome Debugger yang sudah berjalan
        browser = await launch(
            executablePath=CHROME_EXECUTABLE_PATH, # Solusi error Chromium
            browserWSEndpoint=CHROME_DEBUG_URL,
            args=['--no-sandbox']
        )
        print(f"🔗 Terhubung ke Chrome Debugger: {CHROME_DEBUG_URL}")

        # Buka tab baru
        page = await browser.newPage()
        # Langkah membuka halaman target
        await page.goto(TARGET_URL, {'waitUntil': 'networkidle2'})
        print(f"🌐 Berhasil membuka URL target: {TARGET_URL}")

    except TimeoutError:
        print("❌ Timeout saat membuka halaman atau koneksi Pyppeteer.")
        return
    except Exception as e:
        print(f"❌ Gagal terhubung ke Chrome Debugger atau membuka halaman: {e}")
        if "No such file or directory" in str(e):
             print(f"⚠️ Cek apakah jalur CHROME_EXECUTABLE_PATH: {CHROME_EXECUTABLE_PATH} sudah benar.")
        return

    # Loop scraping
    while True:
        try:
            # 1. Scraping Data
            SELECTOR = ".group.flex.flex-col.sm\\:flex-row.sm\\:items-start.gap-3.p-3.rounded-lg"
            elements = await page.querySelectorAll(SELECTOR)
            current_log_data = []

            for element in elements:
                try:
                    service_element = await element.querySelector(".flex-grow.min-w-0 .text-xs.font-bold.text-blue-400")
                    service = await page.evaluate('(element) => element.textContent', service_element)
                    
                    if service.strip().upper() not in ["WHATSAPP", "FACEBOOK"]:
                        continue 

                    range_full_element = await element.querySelector(".flex-grow.min-w-0 .text-\\[10px\\].text-slate-500.font-mono")
                    range_full = await page.evaluate('(element) => element.textContent', range_full_element)
                    range_val = range_full.strip() if range_full else None
                    
                    country_full_element = await element.querySelector(".flex-shrink-0 .text-\\[10px\\].text-slate-600.mt-1.font-mono")
                    country_full = await page.evaluate('(element) => element.textContent', country_full_element)
                    country_match = re.search(r'•\s*(.*)$', country_full.strip())
                    country_name = country_match.group(1).strip() if country_match else "Unknown"

                    message_element = await element.querySelector(".flex-grow.min-w-0 p")
                    message = await page.evaluate('(element) => element.textContent', message_element)
                    
                    full_message = message.replace('➜', '').strip() if message else ""

                    if range_val and full_message:
                        current_log_data.append({
                            'range': range_val,
                            'country': country_name,
                            'service': service.strip(),
                            'message': full_message,
                            'timestamp': datetime.now()
                        })

                except Exception as e:
                    continue

            # 2. Proses dan Kirim ke Telegram
            await cleanup_old_messages(app)
            
            for log in current_log_data:
                range_val = log['range']
                
                if range_val in SENT_MESSAGES:
                    old_data = SENT_MESSAGES[range_val]
                    new_count = old_data['count'] + 1
                    SENT_MESSAGES[range_val]['count'] = new_count
                    SENT_MESSAGES[range_val]['timestamp'] = datetime.now()
                    
                    message_text = format_telegram_message(
                        range_val, new_count, log['country'], log['service'], log['message']
                    )
                    await send_or_edit_telegram_message(app, range_val, log['country'], log['service'], message_text, is_new_entry=False)

                else:
                    message_text = format_telegram_message(
                        range_val, 1, log['country'], log['service'], log['message']
                    )
                    await send_or_edit_telegram_message(app, range_val, log['country'], log['service'], message_text, is_new_entry=True)
            
            # 3. Tunggu dan Refresh Halaman (Simulasi "Typing URL")
            await asyncio.sleep(5) 
            await page.reload({'waitUntil': 'networkidle2'})
            print("🔄 Melakukan refresh halaman (simulasi mengetik ulang URL).")

        except Exception as e:
            print(f"❌ Error saat loop utama scraping: {e}")
            await asyncio.sleep(10)


async def main():
    """Fungsi inisialisasi aplikasi Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT_TOKEN atau CHAT_ID tidak ditemukan di bagian KONFIGURASI. Pastikan sudah benar.")
        return

    # Inisialisasi Telegram Application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    print("🤖 Telegram Bot terhubung.")
    
    # KIRIM PESAN STARTUP (dilakukan setelah bot terhubung)
    await send_startup_message(app)
    
    # Jalankan scraper
    await scrape_and_send(app)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScraper dihentikan oleh pengguna.")
    except Exception as e:
        print(f"Error fatal: {e}")
