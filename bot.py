import asyncio
import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from apify_client import ApifyClientAsync
from flask import Flask
from threading import Thread
from xposedornot import XposedOrNot

# --- الإعدادات ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
apify_client = ApifyClientAsync(APIFY_TOKEN)

# --- خادم ويب بسيط لإبقاء Render نشطاً ---
app = Flask('')
@app.route('/')
def home(): return "OSINT Hybrid Engine is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# ==========================================
# 1. المحركات الاستخباراتية (OSINT Engines)
# ==========================================

async def check_xposedornot(email: str):
    """البحث في تسريبات البيانات عبر XposedOrNot"""
    try:
        xon = XposedOrNot()
        # ملاحظة: هذه الدالة متزامنة، نستخدم to_thread لتجنب تجميد البوت
        result = await asyncio.to_thread(xon.check_email, email)
        if result and hasattr(result, 'breaches') and result.breaches:
            return f"✅ وجد في {len(result.breaches)} تسريب (مثال: {', '.join(result.breaches[:2])}...)"
        return "❌ لم يتم العثور على تسريبات."
    except Exception as e:
        logging.error(f"XposedOrNot Error: {e}")
        return "⚠️ فشل الاتصال بمحرك XposedOrNot."

async def check_hudsonrock(query: str, is_email: bool = True):
    """البحث في سجلات البرمجيات الخبيثة عبر HudsonRock"""
    base_url = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools"
    endpoint = "search-by-email" if is_email else "search-by-username"
    param_name = "email" if is_email else "username"
    
    url = f"{base_url}/{endpoint}?{param_name}={query}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    # التحقق من وجود بيانات
                    if data.get("message") == "No results found" or not data.get("data"):
                        return "❌ لا توجد سجلات إصابة."
                    
                    # استخراج معلومات مبسطة
                    message = data.get("message", "")
                    if "stealer" in message.lower() or data.get("data"):
                        return "🚨 تحذير: الحساب مرتبط بإصابة برمجية خبيثة (Infostealer)!"
                return "❌ لا توجد سجلات إصابة."
        except Exception as e:
            logging.error(f"HudsonRock Error: {e}")
            return "⚠️ فشل الاتصال بـ HudsonRock."

async def check_proxynova(query: str):
    """البحث في قاعدة بيانات COMB الضخمة عبر ProxyNova"""
    url = f"https://api.proxynova.com/comb?query={query}&start=0&limit=5"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("found"):
                        lines = data.get("lines", [])
                        return f"✅ وجد {len(lines)} سجل مسرب. (مثال: {lines[0][:30]}...)"
                return "❌ لم يتم العثور على بيانات في COMB."
        except Exception as e:
            logging.error(f"ProxyNova Error: {e}")
            return "⚠️ فشل الاتصال بـ ProxyNova."

async def search_apify_tiktok(username: str):
    """الكشط العام لبيانات تيك توك عبر Apify"""
    try:
        run_input = {"profiles": [f"https://www.tiktok.com/@{username}"], "maxResults": 1}
        run = await apify_client.actor("logiover/tiktok-profile-email-scraper").call(run_input=run_input)
        if run:
            dataset_id = run["defaultDatasetId"]
            items = await apify_client.dataset(dataset_id).list_items(limit=1)
            if items.items:
                return items.items[0]
    except Exception as e:
        logging.error(f"Apify Error: {e}")
    return None

# ==========================================
# 2. أوامر البوت ومعالجة الرسائل
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "مرحباً بك في محرك OSINT المتقدم! 🕵️‍♂️\n\n"
        "أرسل لي **بريداً إلكترونياً** للبحث في التسريبات،\n"
        "أو **اسم مستخدم** للبحث في سجلات الاختراق وتيك توك."
    )

@dp.message(F.text)
async def handle_query(message: types.Message):
    query = message.text.strip()
    status_msg = await message.answer(f"⏳ جاري تحليل `{query}` عبر 4 محركات استخباراتية... يرجى الانتظار.")
    
    response_text = f"🔎 **تقرير OSINT الشامل لـ:** `{query}`\n\n"
    
    # تحديد نوع البحث
    is_email = "@" in query and "." in query

    if is_email:
        # --- البحث عن بريد إلكتروني ---
        # تشغيل المحركات الثلاثة بالتوازي لتوفير الوقت
        task_xon = check_xposedornot(query)
        task_hr = check_hudsonrock(query, is_email=True)
        task_pn = check_proxynova(query)
        
        results = await asyncio.gather(task_xon, task_hr, task_pn)
        
        response_text += f"📧 **XposedOrNot:**\n{results[0]}\n\n"
        response_text += f"🦠 **HudsonRock:**\n{results[1]}\n\n"
        response_text += f"📋 **ProxyNova (COMB):**\n{results[2]}\n\n"
        
    else:
        # --- البحث عن اسم مستخدم (تيك توك أو غيره) ---
        username = query.lstrip('@')
        
        # 1. البحث في HudsonRock (اسم المستخدم)
        hr_result = await check_hudsonrock(username, is_email=False)
        
        # 2. البحث في ProxyNova (اسم المستخدم)
        pn_result = await check_proxynova(username)
        
        # 3. البحث في تيك توك (Apify)
        live_data = await search_apify_tiktok(username)
        
        response_text += f"🦠 **HudsonRock:**\n{hr_result}\n\n"
        response_text += f"📋 **ProxyNova (COMB):**\n{pn_result}\n\n"
        
        if live_data:
            response_text += f"🌐 **بيانات تيك توك العامة:**\n"
            response_text += f"👤 الاسم: {live_data.get('nickname', 'N/A')}\n"
            response_text += f"📊 المتابعون: {live_data.get('followerCount', 0):,}\n"
            if live_data.get('email'):
                response_text += f"📧 إيميل البايو: `{live_data.get('email')}`\n"
        else:
            response_text += "🌐 **تيك توك:** ❌ لم يتم العثور على بيانات عامة.\n"

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
