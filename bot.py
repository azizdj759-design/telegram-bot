import asyncio
import logging
import sqlite3
import os
import json
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from curl_cffi import requests as curl_requests
from flask import Flask
from threading import Thread

# --- إعدادات البوت ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is missing!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- خادم ويب بسيط لإبقاء Render نشطاً ---
app = Flask('')

@app.route('/')
def home():
    return "OSINT Bot is Alive!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('leaks.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS leaks (username TEXT, email TEXT, phone TEXT)''')
    dummy_data = [('nox.qxx', 'issa.contact@gmail.com', '+212 612-345678')]
    cursor.executemany('INSERT OR IGNORE INTO leaks VALUES (?, ?, ?)', dummy_data)
    conn.commit()
    conn.close()
init_db()

def lookup_leaks(username: str):
    try:
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email, phone FROM leaks WHERE LOWER(username) = ?", (username.lower(),))
        result = cursor.fetchone()
        conn.close()
        return {"email": result[0], "phone": result[1]} if result else None
    except Exception:
        return None

# --- محرك جلب البيانات الحية ---
def fetch_live_data_sync(username: str):
    try:
        url = f"https://www.tiktok.com/@{username}"
        response = curl_requests.get(url, impersonate="chrome110", timeout=10)
        if response.status_code == 200:
            match = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', response.text)
            if match:
                data = json.loads(match.group(1))
                scope = data.get("__DEFAULT_SCOPE__", {})
                user_info = scope.get("webapp.user-detail", {}).get("userInfo", {})
                if user_info:
                    return user_info.get("user", {})
    except Exception as e:
        print(f"Scraping Error: {e}")
    return None

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("مرحباً بك في محرك OSINT! 🕵️‍♂️\nأرسل اسم مستخدم تيك توك للبحث عنه.")

@dp.message(F.text)
async def handle_query(message: types.Message):
    query = message.text.strip()
    status_msg = await message.answer("⏳ جاري البحث...")
    
    response_text = f"🔎 **النتائج لـ:** `{query}`\n\n"
    
    # 1. البحث في التسريبات
    leaked = lookup_leaks(query)
    if leaked:
        response_text += f"⚠️ **بيانات مسربة:**\n"
        response_text += f"📧 الإيميل: `{leaked['email']}`\n"
        response_text += f"📱 الهاتف: `{leaked['phone']}`\n\n"
    
    # 2. جلب البيانات الحية
    live = await asyncio.to_thread(fetch_live_data_sync, query)
    if live:
        response_text += f"🌐 **بيانات حية:**\n"
        response_text += f"👤 الاسم: {live.get('nickname', 'N/A')}\n"
        response_text += f"📊 المتابعون: {live.get('followerCount', 0):,}\n"
        response_text += f"❤️ الإعجابات: {live.get('heartCount', 0):,}\n"
    else:
        response_text += "❌ لم يتم العثور على بيانات حية (قد يكون الحساب غير موجود أو الحظر من Render)."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    # تشغيل Flask في الخلفية
    Thread(target=run_flask, daemon=True).start()
    # تشغيل البوت
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
