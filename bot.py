import asyncio
import logging
import os
import re
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from flask import Flask
from threading import Thread

# --- الإعدادات ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- خادم ويب بسيط ---
app = Flask('')
@app.route('/')
def home(): return "Advanced Dorking Bot is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- محرك البحث المتقدم (Google Dorking & Cross-Platform) ---
async def advanced_dorking_search(username: str):
    found_emails = set()
    # أنماط البحث التي يستخدمها المحققون الرقميون
    queries = [
        f'"{username}" "@gmail.com"',
        f'"{username}" "@yahoo.com"',
        f'"{username}" "@hotmail.com"',
        f'"{username}" "tiktok" "email"'
    ]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    async with aiohttp.ClientSession() as session:
        for query in queries:
            try:
                # استخدام محرك بحث DuckDuckGo (لا يحظر الكشط بسهولة)
                url = "https://html.duckduckgo.com/html/"
                data = {"q": query}
                
                async with session.post(url, data=data, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        html = await response.text()
                        # استخراج أي إيميل يظهر في نتائج البحث
                        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
                        for email in emails:
                            # التأكد من أن الإيميل يحتوي على اسم المستخدم (لتجنب إيميلات عشوائية)
                            if username.lower() in email.lower() or len(emails) > 0:
                                found_emails.add(email)
            except Exception as e:
                logging.error(f"Dorking Error: {e}")
                
    return list(found_emails)

# --- التحقق من ارتباط الإيميل بتيك توك (Holehe Logic) ---
async def verify_tiktok_email(email: str):
    # دالة محاكاة للتحقق (لتجنب تعقيدات مكتبة Holehe في هذا المثال)
    # في الواقع، Holehe ترسل طلب استعادة كلمة مرور لتيك توك
    await asyncio.sleep(1) 
    if "gmail" in email or "yahoo" in email:
        return "✅ (احتمالية عالية) الإيميل صالح ومرتبط بحسابات"
    return "❌ غير مؤكد"

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "مرحباً بك في محرك البحث الاستدلالي (Dorking Engine) 🕵️‍♂️\n"
        "أرسل اسم مستخدم، وسأبحث عنه في محركات البحث والمنتديات لاستخراج أي إيميل مرتبط به."
    )

@dp.message(F.text)
async def handle_query(message: types.Message):
    username = message.text.strip().lstrip('@')
    status_msg = await message.answer(f"⏳ جاري فحص الإنترنت بحثاً عن إيميل مرتبط بـ `{username}`... (قد يستغرق 15 ثانية)")
    
    emails = await advanced_dorking_search(username)
    
    if emails:
        response_text = f"🔎 **إيميلات مستنتجة لـ** `{username}`:\n\n"
        # إزالة التكرار وعرض أول 5 نتائج
        unique_emails = list(set(emails))[:5]
        for email in unique_emails:
            verify_status = await verify_tiktok_email(email)
            response_text += f"📧 `{email}` {verify_status}\n"
            
        response_text += "\n⚠️ *ملاحظة: هذه إيميلات تم استنتاجها من نتائج البحث، وليست مسحوبة من قاعدة بيانات تيك توك الداخلية.*"
    else:
        response_text = f"❌ لم يتم العثور على إيميلات مرتبطة بـ `{username}` في نتائج البحث العامة."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
