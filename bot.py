import asyncio
import logging
import sqlite3
import os
import json
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from curl_cffi import requests as curl_requests
from tiktokflow import TikTokAPI
import httpx

# --- الإعدادات الأساسية ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ضع_التوكن_هنا")
TIKTOK_API_KEY = os.getenv("TIKTOK_API_KEY", "ضع_مفتاح_الـ_API_هنا")
PROXY_URL = os.getenv("PROXY_URL", None)

# تهيئة البوت
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- 1. إعداد قاعدة بيانات التسريبات (Leaks DB) ---
def init_db():
    conn = sqlite3.connect('leaks.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS leaks (username TEXT, email TEXT, phone TEXT)''')
    # بيانات تجريبية للاختبار
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

# --- 2. محرك جلب البيانات الحية (Private API + Scraping) ---
async def fetch_live_data(username: str):
    # المحاولة الأولى: Private API
    if TIKTOK_API_KEY and TIKTOK_API_KEY != "ضع_مفتاح_الـ_API_هنا":
        try:
            api = TikTokAPI(
                api_key=TIKTOK_API_KEY,
                proxies=[PROXY_URL] if PROXY_URL else None
            )
            user_info = api.user.info(username=username)
            if user_info and "user" in user_info:
                return user_info["user"]
        except Exception as e:
            print(f"Private API Error: {e}")

    # المحاولة الثانية: الكشط المباشر (Fallback)
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

# --- 3. محرك التحقق عبر البريد الإلكتروني (Holehe Logic) ---
async def check_email_recovery(email: str):
    # محاكاة إرسال طلب استعادة كلمة المرور إلى تيك توك
    # في الإنتاج، يجب استخدام بروكسي وتوقيعات (Signatures)
    async with httpx.AsyncClient() as client:
        try:
            # ملاحظة: هذا الرابط تجريبي، قد تحتاج لتحديثه
            response = await client.post(
                "https://api2.tiktok.com/passport/find-password-via-email/",
                json={"email": email},
                timeout=10
            )
            if response.status_code == 200:
                return "✅ البريد الإلكتروني مرتبط بحساب تيك توك."
        except Exception:
            pass
    return "❌ لم يتم تأكيد الارتباط أو فشل الطلب."

# --- 4. أوامر البوت والتفاعل ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 بحث عن مستخدم", callback_data="search_user")
    builder.button(text="📧 التحقق من إيميل", callback_data="check_email")
    await message.answer(
        "مرحباً بك في محرك OSINT المتقدم! 🕵️‍♂️\nاختر نوع البحث:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "search_user")
async def ask_username(callback: types.CallbackQuery):
    await callback.message.answer("أرسل اسم المستخدم (بدون @):")
    await callback.answer()

@dp.callback_query(F.data == "check_email")
async def ask_email(callback: types.CallbackQuery):
    await callback.message.answer("أرسل البريد الإلكتروني للتحقق:")
    await callback.answer()

@dp.message(F.text)
async def handle_input(message: types.Message):
    query = message.text.strip()
    status_msg = await message.answer("⏳ جاري تحليل البيانات...")
    
    response_text = f"🔎 **نتائج البحث لـ:** `{query}`\n\n"
    
    # التحقق من نوع المدخل
    if "@" in query and "." in query:
        # معالجة كبريد إلكتروني
        email_status = await check_email_recovery(query)
        response_text += f"📧 **التحقق من البريد:**\n{email_status}\n"
    else:
        # معالجة كاسم مستخدم
        username = query.lstrip('@')
        
        # 1. البحث في التسريبات
        leaked = lookup_leaks(username)
        if leaked:
            response_text += f"⚠️ **من التسريبات (Leaked DB):**\n"
            response_text += f"📧 الإيميل: `{leaked['email']}`\n"
            response_text += f"📱 الهاتف: `{leaked['phone']}`\n\n"
        
        # 2. جلب البيانات الحية
        live = await fetch_live_data(username)
        if live:
            response_text += f"🌐 **بيانات حية (Live):**\n"
            response_text += f"👤 الاسم: {live.get('nickname', 'N/A')}\n"
            response_text += f"📊 المتابعون: {live.get('follower_count', 0):,}\n"
            response_text += f"❤️ الإعجابات: {live.get('heart_count', 0):,}\n"
            if live.get('signature'):
                response_text += f"📝 البايو: {live.get('signature')}\n"
        else:
            response_text += "❌ لم يتم العثور على بيانات حية.\n"

    await status_msg.edit_text(response_text, parse_mode="Markdown")

# --- 5. تشغيل البوت ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
