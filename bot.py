import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread

# --- إعدادات بوت تيليجرام الخاص بك ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- إعدادات حساب المستخدم (Userbot) ---
API_ID = 1234567 # ضع الـ API ID الخاص بك
API_HASH = "ضع_الـ_API_HASH_هنا"
TARGET_BOT = "tiktokinfobot" 

client = TelegramClient('anon', API_ID, API_HASH)

# --- خادم ويب بسيط ---
app = Flask('')
@app.route('/')
def home(): return "Proxy Scraper is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- دالة اختراق نظام الدفع / سحب البيانات ---
async def scrape_and_bypass(username: str):
    try:
        if not client.is_connected():
            await client.connect()
            
        # إرسال الطلب للبوت
        await client.send_message(TARGET_BOT, f"/search {username}") 
        await asyncio.sleep(4) # الانتظار ليرد البوت
        
        messages = await client.get_messages(TARGET_BOT, limit=1)
        if messages:
            msg = messages[0]
            response_text = msg.text or ""
            
            # 1. هل البوت يطلب دفع؟
            if "pay" in response_text.lower() or "balance" in response_text.lower() or "رصيد" in response_text:
                
                # محاولة إرسال أوامر الرصيد المجاني تلقائياً
                free_commands = ["/daily", "/bonus", "/free", "/checkin"]
                for cmd in free_commands:
                    await client.send_message(TARGET_BOT, cmd)
                    await asyncio.sleep(2)
                
                # قراءة الردود بعد محاولة الحصول على رصيد
                messages = await client.get_messages(TARGET_BOT, limit=3)
                for m in messages:
                    if m.text and ("success" in m.text.lower() or "added" in m.text.lower() or "تم" in m.text):
                        # إذا حصلنا على رصيد، نعيد المحاولة
                        await client.send_message(TARGET_BOT, f"/search {username}")
                        await asyncio.sleep(4)
                        final_msg = (await client.get_messages(TARGET_BOT, limit=1))[0]
                        return process_message(final_msg)

                # إذا فشلنا في الحصول على رصيد، نرجع الرسالة التي تطلب الدفع
                return {"error": "البوت يطلب دفع. حاول استخدام حسابات أخرى أو تجاوز الحظر يدوياً.", "raw": response_text, "buttons": msg.buttons}
            
            # 2. إذا لم يطلب دفع، نقوم بمعالجة الرسالة الطبيعية
            return process_message(msg)
            
    except Exception as e:
        print(f"Scraping Error: {e}")
    return None

def process_message(msg):
    """دالة مساعدة لاستخراج البيانات من الرسالة"""
    response_text = msg.text or ""
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', response_text)
    phone_match = re.search(r'\+?\d[\d -]{8,12}\d', response_text)
    
    return {
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0) if phone_match else None,
        "raw": response_text
    }

# --- أوامر البوت الخاص بك ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("مرحباً! 🕵️‍♂️\nأرسل اسم مستخدم للبحث عبر الوسيط الذكي.")

@dp.message(F.text)
async def handle_query(message: types.Message):
    username = message.text.strip().lstrip('@')
    status_msg = await message.answer(f"⏳ جاري استغلال البوت لسحب `{username}`...")
    
    data = await scrape_and_bypass(username)
    
    if data and "error" not in data:
        response_text = f"🔎 **النتائج لـ:** `{username}`\n\n"
        if data.get('email'): response_text += f"📧 **الإيميل:** `{data['email']}`\n"
        if data.get('phone'): response_text += f"📱 **الهاتف:** `{data['phone']}`\n"
        if not data.get('email') and not data.get('phone'): response_text += "⚠️ لم يتم العثور على إيميل أو هاتف."
    elif data and "error" in data:
        response_text = f"⛔ **تنبيه:** {data['error']}\n\n"
        response_text += f"📄 **الرد من البوت:**\n`{data['raw'][:200]}`"
    else:
        response_text = f"❌ فشل السحب."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    await client.start()
    print("Telethon Client Started!")
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
