import asyncio
import logging
import os
import sqlite3
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

apify_client = ApifyClientAsync(APIFY_TOKEN)

# --- 1. إعداد قاعدة بيانات التسريبات ---
# ملاحظة: يجب أن ترفع ملف leaks.db مع الكود في GitHub
def init_db():
    # إنشاء قاعدة بيانات وهمية للتجربة (إذا لم تكن موجودة)
    if not os.path.exists('leaks.db'):
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS leaks (username TEXT, email TEXT, phone TEXT)''')
        # بيانات وهمية لتجربة نجاح البوت
        dummy_data = [('test_account', 'test@example.com', '+123456789')]
        cursor.executemany('INSERT OR IGNORE INTO leaks VALUES (?, ?, ?)', dummy_data)
        conn.commit()
        conn.close()

init_db()

def search_leaks_db(username: str):
    """البحث في قاعدة البيانات المسربة"""
    try:
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        # البحث بدون حساسية لحالة الأحرف
        cursor.execute("SELECT email, phone FROM leaks WHERE LOWER(username) = ?", (username.lower(),))
        result = cursor.fetchone()
        conn.close()
        if result:
            return {"email": result[0], "phone": result[1]}
        return None
    except Exception as e:
        print(f"DB Error: {e}")
        return None

# --- 2. الكشط العام (Apify) ---
async def search_apify(username: str):
    try:
        run_input = {"profiles": [f"https://www.tiktok.com/@{username}"], "maxResults": 1}
        run = await apify_client.actor("logiover/tiktok-profile-email-scraper").call(run_input=run_input)
        if run:
            dataset_id = run["defaultDatasetId"]
            items = await apify_client.dataset(dataset_id).list_items(limit=1)
            if items.items:
                return items.items[0]
    except Exception as e:
        print(f"Apify Error: {e}")
    return None

# --- خادم ويب بسيط لإبقاء Render نشطاً ---
app = Flask('')
@app.route('/')
def home(): return "OSINT Bot is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("مرحباً! 🕵️‍♂️\nأرسل اسم مستخدم تيك توك للبحث في التسريبات والبيانات العامة.")

@dp.message(F.text)
async def handle_query(message: types.Message):
    username = message.text.strip().lstrip('@')
    status_msg = await message.answer(f"⏳ جاري تحليل `{username}` في قواعد البيانات والمصادر المفتوحة...")
    
    # 1. البحث في التسريبات أولاً (السلاح السري)
    leaked_data = search_leaks_db(username)
    
    # 2. جلب البيانات العامة (Apify)
    live_data = await search_apify(username)
    
    response_text = f"🔎 **تقرير OSINT لـ:** `{username}`\n\n"
    
    # عرض نتائج التسريبات (إذا وجدت)
    if leaked_data:
        response_text += f"🚨 **بيانات مسربة (Leaked):**\n"
        response_text += f"📧 الإيميل: `{leaked_data['email']}`\n"
        response_text += f"📱 الهاتف: `{leaked_data['phone']}`\n\n"
    else:
        response_text += f"🔒 **التسريبات:** لم يتم العثور على سجل لهذا الاسم في قاعدة البيانات المحلية.\n\n"

    # عرض البيانات الحية (إذا وجدت)
    if live_data:
        response_text += f"🌐 **بيانات عامة (Live):**\n"
        response_text += f"👤 الاسم: {live_data.get('nickname', 'N/A')}\n"
        response_text += f"📊 المتابعون: {live_data.get('followerCount', 0):,}\n"
        response_text += f"❤️ الإعجابات: {live_data.get('heartCount', 0):,}\n"
        
        # إيميل وهاتف البايو (إن وجد)
        if live_data.get('email') or live_data.get('phone'):
            response_text += f"📧 إيميل البايو: {live_data.get('email', 'None')}\n"
            response_text += f"📱 هاتف البايو: {live_data.get('phone', 'None')}\n"
    else:
        response_text += f"❌ لم يتم العثور على بيانات عامة (الحساب غير موجود أو محظور)."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
