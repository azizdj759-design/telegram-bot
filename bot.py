import asyncio
import logging
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from flask import Flask
from threading import Thread

# --- الإعدادات ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
TG_SESSION = os.getenv("TG_SESSION")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# تهيئة الحساب الوسيط (Userbot)
client = TelegramClient(StringSession(TG_SESSION), API_ID, API_HASH)

# --- قائمة البوتات المستهدفة (يمكنك إضافة المزيد) ---
# التنسيق: {'username': 'اسم البوت بدون @', 'command_prefix': 'الأمر الذي يسبق البحث (أو None)'}
TARGET_BOTS = [
    {"username": "goodsearch_robot", "prefix": "/search "},  # LeakOsint
    {"username": "GtaSearchOsntBot", "prefix": "/search "},  # GTA Search
    {"username": "Dyxless_infoo_bot", "prefix": ""},         # Dyxless (يقبل النص مباشرة غالباً)
    {"username": "Sherlock_Holmes_OSINT_bot", "prefix": ""}  # Sherlock (لأسماء المستخدمين)
]

# --- خادم ويب بسيط ---
app = Flask('')
@app.route('/')
def home(): return "Meta OSINT Bot is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- دالة الاستعلام من بوت واحد ---
async def query_single_bot(bot_info: dict, query: str):
    target = bot_info["username"]
    prefix = bot_info["prefix"]
    message_text = f"{prefix}{query}".strip()
    
    try:
        # إرسال الرسالة
        sent_msg = await client.send_message(target, message_text)
        
        # الانتظار حتى يرد البوت (Timeout 15 ثانية)
        response_text = ""
        for _ in range(15): 
            await asyncio.sleep(1)
            # جلب آخر رسالة من البوت
            messages = await client.get_messages(target, limit=1)
            if messages and messages[0].id != sent_msg.id:
                response_text = messages[0].text or ""
                # التحقق من وجود أزرار وإضافتها
                if messages[0].buttons:
                    response_text += "\n[يحتوي على أزرار تفاعلية]"
                break
        
        if not response_text:
            return {"source": target, "status": "no_response", "data": None}
            
        # استخراج البيانات بـ Regex
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', response_text)
        phones = re.findall(r'\+?\d[\d -]{8,15}\d', response_text)
        
        return {
            "source": target,
            "status": "success",
            "email": list(set(emails))[0] if emails else None,
            "phone": list(set(phones))[0] if phones else None,
            "raw": response_text[:300] # مقتطف من الرد
        }
        
    except Exception as e:
        logging.error(f"Error querying {target}: {e}")
        return {"source": target, "status": "error", "data": str(e)}

# --- دالة تجميع النتائج (Meta Search) ---
async def meta_search(query: str):
    tasks = []
    for bot_info in TARGET_BOTS:
        tasks.append(query_single_bot(bot_info, query))
    
    # تشغيل جميع البوتات في نفس الوقت (Parallel Execution)
    results = await asyncio.gather(*tasks)
    return results

# --- أوامر البوت الخاص بك ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "مرحباً بك في **Meta OSINT Bot**! 🕵️‍♂️\n"
        "أنا لا أمتلك قاعدة بيانات، بل أنا محرك يبحث في عدة بوتات استخباراتية في نفس الوقت.\n"
        "أرسل اسم مستخدم، بريد إلكتروني، أو رقم هاتف، وسأجمع لك النتائج."
    )

@dp.message(F.text)
async def handle_query(message: types.Message):
    query = message.text.strip()
    status_msg = await message.answer(f"⏳ جاري إرسال `{query}` إلى {len(TARGET_BOTS)} بوتات استخباراتية... (قد يستغرق 15 ثانية)")
    
    results = await meta_search(query)
    
    response_text = f"🌐 **تقرير البحث الشامل (Meta-Search) لـ:** `{query}`\n\n"
    found_anything = False
    
    for res in results:
        if res["status"] == "success":
            if res.get("email") or res.get("phone"):
                found_anything = True
                response_text += f"✅ **{res['source']}:**\n"
                if res.get("email"): response_text += f"  📧 إيميل: `{res['email']}`\n"
                if res.get("phone"): response_text += f"  📱 هاتف: `{res['phone']}`\n"
            else:
                response_text += f"⚪ **{res['source']}:** لم يجد بيانات اتصال مباشرة (لكن قد يوجد تقرير).\n"
        elif res["status"] == "no_response":
            response_text += f"⏳ **{res['source']}:** لم يرد في الوقت المحدد.\n"
        else:
            response_text += f"❌ **{res['source']}:** خطأ في الاتصال.\n"

    if not found_anything:
        response_text += "\n⚠️ **الخلاصة:** لم يتم العثور على إيميل أو هاتف مباشر في ردود البوتات. قد تكون البيانات مدفوعة أو غير موجودة في التسريبات."

    await status_msg.edit_text(response_text, parse_mode="Markdown")

async def main():
    try:
        await client.start()
        logging.info("Userbot Connected Successfully!")
    except Exception as e:
        logging.error(f"Failed to start Userbot: {e}")
        return

    Thread(target=run_flask, daemon=True).start()
    logging.info("Starting Meta Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
