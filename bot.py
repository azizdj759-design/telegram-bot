import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from apify_client import ApifyClientAsync
from flask import Flask
from threading import Thread

# --- الإعدادات ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- تهيئة عميل Apify غير المتزامن ---
apify_client = ApifyClientAsync(APIFY_TOKEN)

# --- خادم ويب بسيط لإبقاء Render نشطاً ---
app = Flask('')

@app.route('/')
def home():
    return "OSINT Bot is Alive!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- دالة البحث عبر Apify (بشكل غير متزامن) ---
async def search_via_apify(username: str):
    try:
        run_input = {
            "profiles": [f"https://www.tiktok.com/@{username}"],
            "maxResults": 1
        }
        
        # استدعاء الـ Actor بشكل غير متزامن
        run = await apify_client.actor("logiover/tiktok-profile-email-scraper").call(run_input=run_input)
        
        if run is None:
            return None

        dataset_id = run["defaultDatasetId"]
        items = await apify_client.dataset(dataset_id).list_items(limit=1)
        
        if items.items:
            return items.items[0]
        return None
    except Exception as e:
        print(f"Apify Error: {e}")
        return None

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("مرحباً! 🕵️‍♂️\nأرسل اسم مستخدم تيك توك للبحث عن بياناته.")

@dp.message(F.text)
async def handle_query(message: types.Message):
    username = message.text.strip().lstrip('@')
    status_msg = await message.answer(f"⏳ جاري البحث عن `{username}`...")
    
    data = await search_via_apify(username)
    
    if data:
        response_text = f"🔎 **النتائج لـ:** `{username}`\n\n"
        response_text += f"👤 **الاسم:** {data.get('nickname', 'N/A')}\n"
        response_text += f"📊 **المتابعون:** {data.get('followerCount', 0):,}\n"
        response_text += f"❤️ **الإعجابات:** {data.get('heartCount', 0):,}\n"
        
        email = data.get('email')
        phone = data.get('phone')
        
        if email:
            response_text += f"\n📧 **الإيميل:** `{email}`\n"
        if phone:
            response_text += f"📱 **الهاتف:** `{phone}`\n"
            
        if not email and not phone:
            response_text += "\n⚠️ لم يتم العثور على إيميل أو هاتف عام لهذا الحساب.\n"
            
        response_text += f"\n🔗 **الرابط:** {data.get('profileUrl', 'N/A')}"
    else:
        response_text = f"❌ لم يتم العثور على بيانات لـ `{username}`."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
