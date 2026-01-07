import asyncio
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Pyppeteer
from pyppeteer import launch
from pyppeteer.errors import TimeoutError

# Telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder

# Muat variabel dari .env
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CHROME_DEBUG_URL = os.getenv("CHROME_DEBUG_URL")
TARGET_URL = os.getenv("TARGET_URL")

# Logika untuk konversi kode negara ke emoji
def get_country_emoji(country_name):
    """Mengembalikan emoji untuk Myanmar, default ke ❓ untuk negara lain."""
    if "Myanmar" in country_name:
        return "🇲🇲"
    # Tambahkan negara lain jika diperlukan
    return "❓"

# Logika untuk format pesan Telegram
def format_telegram_message(range_val, count, country_name, service, full_message):
    """Membuat teks pesan Telegram dengan format yang diminta."""
    country_emoji = get_country_emoji(country_name)
    
    # Range dengan jumlah kemunculan
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

# Logika untuk membuat keyboard inline Telegram
def create_keyboard():
    """Membuat keyboard inline untuk pesan Telegram."""
    keyboard = [
        [
            InlineKeyboardButton("📞GetNumber", url="https://t.me/myzuraisgoodbot?start=ZuraBot"),
            InlineKeyboardButton("👤Admin", url="https://t.me/Imr1d")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Dictionary global untuk melacak pesan yang sudah dikirim
# Key: range_val (e.g., "959755133XXX")
# Value: { 'message_id': int, 'count': int, 'timestamp': datetime }
SENT_MESSAGES = {}

async def send_or_edit_telegram_message(app, range_val, country, service, message_text, is_new_entry):
    """
    Mengirim pesan baru atau mengedit pesan yang sudah ada di Telegram.
    
    Menggunakan HTML untuk <code> dan <blockquote>.
    """
    global SENT_MESSAGES
    
    reply_markup = create_keyboard()
    
    try:
        if range_val in SENT_MESSAGES:
            # Edit pesan yang sudah ada
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
            # Kirim pesan baru
            sent_message = await app.bot.send_message(
                chat_id=CHAT_ID,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            # Simpan ID pesan baru
            SENT_MESSAGES[range_val] = {
                'message_id': sent_message.message_id,
                'count': 1,
                'timestamp': datetime.now()
            }
            print(f"✅ Pesan baru terkirim untuk range: {range_val}")
            
    except Exception as e:
        print(f"❌ Gagal mengirim/mengedit pesan Telegram: {e}")

async def delete_telegram_message(app, message_id, range_val):
    """Menghapus pesan dari Telegram."""
    try:
        await app.bot.delete_message(chat_id=CHAT_ID, message_id=message_id)
        print(f"🗑️ Pesan lama berhasil dihapus untuk range: {range_val}")
    except Exception as e:
        # Pesan mungkin sudah terhapus, abaikan error
        print(f"⚠️ Gagal menghapus pesan {message_id} untuk {range_val} (Mungkin sudah terhapus): {e}")

async def cleanup_old_messages(app):
    """Menghapus pesan dari SENT_MESSAGES jika sudah lebih dari 10 menit tanpa update."""
    global SENT_MESSAGES
    ten_minutes_ago = datetime.now() - timedelta(minutes=10)
    
    ranges_to_remove = []
    for range_val, data in SENT_MESSAGES.items():
        if data['timestamp'] < ten_minutes_ago:
            # PENTING: Jangan hapus dari Telegram, hanya dari dictionary pelacak.
            # Logika user: "jika dalam 10 menit ga muncul range sama lagi lupain" -> Artinya, lupakan status pelacakan, tapi pesannya tetap ada.
            ranges_to_remove.append(range_val)
            print(f"🧹 Range {range_val} (Count: {data['count']}) sudah lebih dari 10 menit, menghapus dari pelacakan.")
            
    for range_val in ranges_to_remove:
        # Hapus hanya dari dictionary pelacak, pesan di Telegram tetap ada.
        del SENT_MESSAGES[range_val]

async def scrape_and_send(app):
    """Fungsi utama untuk scraping dan pengiriman pesan."""
    global SENT_MESSAGES
    
    if not CHROME_DEBUG_URL or not TARGET_URL:
        print("❌ Pastikan CHROME_DEBUG_URL dan TARGET_URL sudah diset di .env")
        return

    try:
        # Koneksi ke Chrome Debugger yang sudah berjalan
        browser = await launch(
            # headless=True, # Set ke False jika ingin melihat browser (Tidak disarankan untuk koneksi ke debugger yang sudah ada)
            # Karena Anda meminta menggunakan debugger yang sudah terbuka, kita harus menggunakan koneksi websocket
            # browserWSEndpoint harus diset dengan URL dari .env
            browserWSEndpoint=CHROME_DEBUG_URL,
            args=['--no-sandbox'] # Penting untuk lingkungan Linux
        )
        print(f"🔗 Terhubung ke Chrome Debugger: {CHROME_DEBUG_URL}")

        # Buka tab baru
        page = await browser.newPage()
        await page.goto(TARGET_URL, {'waitUntil': 'networkidle2'})
        print(f"🌐 Berhasil membuka URL target: {TARGET_URL}")

    except TimeoutError:
        print("❌ Timeout saat membuka halaman atau koneksi Pyppeteer.")
        return
    except Exception as e:
        print(f"❌ Gagal terhubung ke Chrome Debugger atau membuka halaman: {e}")
        return

    # Loop scraping
    while True:
        try:
            # 1. Scraping Data
            # Selector untuk setiap entri log
            SELECTOR = ".group.flex.flex-col.sm\\:flex-row.sm\\:items-start.gap-3.p-3.rounded-lg"
            
            # Ambil semua elemen log
            elements = await page.querySelectorAll(SELECTOR)
            
            # Simpan data yang sudah diproses dalam loop saat ini
            current_log_data = []

            for element in elements:
                try:
                    # Ambil Service (WhatsApp/Facebook)
                    service_element = await element.querySelector(".flex-grow.min-w-0 .text-xs.font-bold.text-blue-400")
                    service = await page.evaluate('(element) => element.textContent', service_element)
                    
                    # Cek Service
                    if service.strip().upper() not in ["WHATSAPP", "FACEBOOK"]:
                        continue # Lewati jika bukan WhatsApp atau Facebook

                    # Ambil Range (Nomor) - format 959755133XXX
                    range_full_element = await element.querySelector(".flex-grow.min-w-0 .text-\\[10px\\].text-slate-500.font-mono")
                    range_full = await page.evaluate('(element) => element.textContent', range_full_element)
                    range_val = range_full.strip() if range_full else None
                    
                    # Ambil Negara - format "959755133 • Myanmar"
                    country_full_element = await element.querySelector(".flex-shrink-0 .text-\\[10px\\].text-slate-600.mt-1.font-mono")
                    country_full = await page.evaluate('(element) => element.textContent', country_full_element)
                    # Ekstrak nama negara dari string (e.g., "959755133 • Myanmar" -> "Myanmar")
                    country_match = re.search(r'•\s*(.*)$', country_full.strip())
                    country_name = country_match.group(1).strip() if country_match else "Unknown"

                    # Ambil Pesan (full message)
                    message_element = await element.querySelector(".flex-grow.min-w-0 p")
                    message = await page.evaluate('(element) => element.textContent', message_element)
                    
                    # Bersihkan pesan dari prefix "➜"
                    full_message = message.replace('➜', '').strip() if message else ""

                    if range_val and full_message:
                        current_log_data.append({
                            'range': range_val,
                            'country': country_name,
                            'service': service.strip(),
                            'message': full_message,
                            'timestamp': datetime.now() # Waktu saat ini (scraper run)
                        })

                except Exception as e:
                    # print(f"⚠️ Error memproses satu entri log: {e}")
                    continue

            # 2. Proses dan Kirim ke Telegram
            
            # Cek status log (menghapus yang sudah lebih dari 10 menit)
            await cleanup_old_messages(app)
            
            # Balik urutan untuk memproses dari yang PALING BARU (Elemen pertama di HTML adalah yang terbaru)
            # Atau proses sesuai urutan untuk memastikan yang paling baru dihitung/dikirim.
            
            for log in current_log_data:
                range_val = log['range']
                
                # Cek apakah range sudah pernah dikirim
                if range_val in SENT_MESSAGES:
                    # Update count dan timestamp
                    old_data = SENT_MESSAGES[range_val]
                    old_count = old_data['count']
                    new_count = old_count + 1
                    
                    # Update Dictionary Global
                    SENT_MESSAGES[range_val]['count'] = new_count
                    SENT_MESSAGES[range_val]['timestamp'] = datetime.now()
                    
                    # Buat pesan baru dengan count yang diperbarui
                    message_text = format_telegram_message(
                        range_val, 
                        new_count, 
                        log['country'], 
                        log['service'], 
                        log['message']
                    )

                    # Edit pesan lama di Telegram (yang sebelumnya 1x menjadi 2x, dst.)
                    await send_or_edit_telegram_message(
                        app, 
                        range_val, 
                        log['country'], 
                        log['service'], 
                        message_text,
                        is_new_entry=False
                    )

                else:
                    # Range baru, kirim pesan baru
                    message_text = format_telegram_message(
                        range_val, 
                        1, # Default count 1
                        log['country'], 
                        log['service'], 
                        log['message']
                    )
                    
                    # Kirim pesan baru ke Telegram dan simpan message_id
                    await send_or_edit_telegram_message(
                        app, 
                        range_val, 
                        log['country'], 
                        log['service'], 
                        message_text,
                        is_new_entry=True
                    )
            
            # 3. Tunggu sebelum scraping berikutnya (misalnya 5 detik)
            await asyncio.sleep(5) 

        except Exception as e:
            print(f"❌ Error saat loop utama scraping: {e}")
            await asyncio.sleep(10) # Tunggu lebih lama jika ada error
            # Coba refresh halaman jika sering error (opsional)
            # await page.reload()


async def main():
    """Fungsi inisialisasi aplikasi Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ BOT_TOKEN atau CHAT_ID tidak ditemukan di .env. Pastikan .env sudah benar.")
        return

    # Inisialisasi Telegram Application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    print("🤖 Telegram Bot terhubung.")
    
    # Jalankan scraper
    await scrape_and_send(app)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScraper dihentikan oleh pengguna.")
    except Exception as e:
        print(f"Error fatal: {e}")
