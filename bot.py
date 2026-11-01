import asyncio
import logging
import os
import sqlite3
import httpx
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

# --- 1. إعداد قاعدة البيانات المحلية (Leaks DB) ---
def init_db():
    if not os.path.exists('leaks.db'):
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS leaks (username TEXT, email TEXT, phone TEXT)''')
        dummy_data = [('test_account', 'test@example.com', '+123456789')]
        cursor.executemany('INSERT OR IGNORE INTO leaks VALUES (?, ?, ?)', dummy_data)
        conn.commit()
        conn.close()
init_db()

def search_local_leaks(username: str):
    try:
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email, phone FROM leaks WHERE LOWER(username) = ?", (username.lower(),))
        result = cursor.fetchone()
        conn.close()
        return {"email": result[0], "phone": result[1]} if result else None
    except Exception:
        return None

# --- 2. محرك Hudson Rock (كشف تسريبات الاعتماد) ---
async def check_hudson_rock(email: str):
    """البحث عن البريد في سجلات البرمجيات الخبيثة (Infostealer Logs)"""
    try:
        async with httpx.AsyncClient() as client:
            # استخدام API المجاني من Hudson Rock
            url = f"https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email?email={email}"
            response = await client.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                # التحقق من وجود بيانات مسربة
                if data.get("message") != "No results found" and data.get("data"):
                    return {"source": "Hudson Rock (Infostealer)", "details": data.get("data")}
    except Exception as e:
        print(f"Hudson Rock Error: {e}")
    return None

# --- 3. محرك PSBDMP (البحث في Pastebin) ---
async def check_psbdmp(email: str):
    """البحث عن البريد في تسريبات Pastebin"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://psbdmp.ws/api/search/{email}"
            response = await client.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return {"source": "Pastebin (PSBDMP)", "count": len(data), "latest": data[0].get("text", "")[:100] + "..."}
    except Exception as e:
        print(f"PSBDMP Error: {e}")
    return None

# --- 4. الكشط العام (Apify) ---
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
def home(): return "OSINT Hybrid Engine is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("مرحباً! 🕵️‍♂️\nأرسل اسم مستخدم تيك توك للبحث في التسريبات والبيانات العامة.")

@dp.message(F.text)
async def handle_query(message: types.Message):
    query = message.text.strip()
    status_msg = await message.answer(f"⏳ جاري تحليل `{query}` عبر محركات OSINT المتعددة...")
    
    response_text = f"🔎 **تقرير OSINT المتقدم لـ:** `{query}`\n\n"
    
    # 1. البحث في قاعدة البيانات المحلية (إذا كان اسم مستخدم)
    if "@" not in query:
        local_data = search_local_leaks(query)
        if local_data:
            response_text += f"🚨 **بيانات مسربة (محلي):**\n"
            response_text += f"📧 الإيميل: `{local_data['email']}`\n"
            response_text += f"📱 الهاتف: `{local_data['phone']}`\n\n"
        
        # 2. الكشط العام عبر Apify
        live_data = await search_apify(query)
        if live_data:
            response_text += f"🌐 **بيانات عامة (Apify):**\n"
            response_text += f"👤 الاسم: {live_data.get('nickname', 'N/A')}\n"
            response_text += f"📊 المتابعون: {live_data.get('followerCount', 0):,}\n"
            if live_data.get('email'):
                response_text += f"📧 إيميل البايو: `{live_data.get('email')}`\n"
            if live_data.get('phone'):
                response_text += f"📱 هاتف البايو: `{live_data.get('phone')}`\n"
            response_text += "\n"
    
    # 3. إذا كان المدخل بريداً إلكترونياً، نبحث في محركات التسريبات
    if "@" in query and "." in query:
        hr_result = await check_hudson_rock(query)
        if hr_result:
            response_text += f"🦠 **تسريب اعتماد (Hudson Rock):**\n"
            response_text += f"تم العثور على البريد في سجلات برمجيات خبيثة.\n\n"
        
        psb_result = await check_psbdmp(query)
        if psb_result:
            response_text += f"📋 **تسريب Pastebin:**\n"
            response_text += f"تم العثور على {psb_result['count']} تسريب.\n"
            response_text += f"أحدث تسريب: `{psb_result['latest']}`\n\n"

    if len(response_text) < 50: # إذا لم يتم العثور على أي شيء
        response_text += "❌ لم يتم العثور على بيانات في المصادر المتاحة."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
