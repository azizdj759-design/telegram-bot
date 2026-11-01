import asyncio
import logging
import os
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from flask import Flask
from threading import Thread
import holehe

# --- الإعدادات ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")  # مفتاح LeakInsight من RapidAPI
RAPIDAPI_HOST = "leakinsight.p.rapidapi.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- خادم ويب بسيط ---
app = Flask('')
@app.route('/')
def home(): return "Leak Search Engine is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- دالة البحث في LeakInsight ---
async def search_leakinsight(query: str):
    url = f"https://{RAPIDAPI_HOST}/search"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    params = {"query": query, "limit": 5}  # البحث بـ 5 نتائج كحد أقصى
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and data.get("results"):
                        return data["results"]
                    return "❌ لم يتم العثور على نتائج في قاعدة بيانات LeakInsight."
                elif response.status == 403:
                    return "⚠️ مفتاح RapidAPI غير صالح أو انتهت صلاحيته."
                else:
                    return f"⚠️ فشل الاتصال بـ LeakInsight (كود: {response.status})."
        except Exception as e:
            logging.error(f"LeakInsight Error: {e}")
            return "⚠️ فشل الاتصال بمحرك LeakInsight."

# --- دالة التحقق من البريد الإلكتروني باستخدام Holehe ---
async def check_email_holehe(email: str):
    try:
        # تشغيل Holehe للتحقق من البريد الإلكتروني
        results = await asyncio.to_thread(holehe.main, email)
        # Holehe يرجع قائمة من النتائج، نبحث عن تيك توك
        for site, exists in results.items():
            if site.lower() == "tiktok" and exists:
                return "✅ البريد الإلكتروني مسجل في تيك توك."
        return "❌ البريد الإلكتروني غير مسجل في تيك توك (أو لم يتم التحقق منه)."
    except Exception as e:
        logging.error(f"Holehe Error: {e}")
        return "⚠️ فشل التحقق من البريد الإلكتروني."

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "مرحباً بك في محرك البحث في التسريبات! 🕵️‍♂️\n\n"
        "أرسل لي **اسم مستخدم** أو **بريد إلكتروني** أو **رقم هاتف** للبحث عنه في قواعد بيانات التسريبات الحقيقية."
    )

@dp.message(F.text)
async def handle_query(message: types.Message):
    query = message.text.strip()
    status_msg = await message.answer(f"⏳ جاري البحث عن `{query}` في مليارات السجلات المسربة...")
    
    response_text = f"🔎 **تقرير التسريبات لـ:** `{query}`\n\n"
    
    # 1. البحث في LeakInsight
    leak_results = await search_leakinsight(query)
    
    if isinstance(leak_results, list) and leak_results:
        response_text += f"🚨 **LeakInsight (عينة):**\n"
        for i, res in enumerate(leak_results[:3], 1):
            # عرض بيانات مختصرة (بدون كلمات مرور)
            email = res.get("email", "N/A")
            phone = res.get("phone", "N/A")
            source = res.get("source", "N/A")
            response_text += f"{i}. 📧: `{email}` | 📱: `{phone}` | 📂: {source}\n"
    elif isinstance(leak_results, str):
        response_text += f"{leak_results}\n\n"
    
    # 2. إذا كان المدخل بريدًا إلكترونيًا، نتحقق منه باستخدام Holehe
    if "@" in query and "." in query:
        holehe_result = await check_email_holehe(query)
        response_text += f"📧 **Holehe (التحقق):**\n{holehe_result}\n\n"
    
    if len(response_text) < 60:  # إذا لم يتم العثور على أي شيء
        response_text += "❌ لم يتم العثور على نتائج في المصادر المتاحة."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
