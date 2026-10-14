import os
import logging
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
PORT = int(os.environ.get("PORT", 10000))

app = Flask(__name__)
application = None

async def setup_bot():
    app_bot = Application.builder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_query))
    await app_bot.initialize()
    return app_bot

async def start(update: Update, context):
    await update.message.reply_text(
        "⚡ **مرحباً بك في بوت تيك توك الاستخباراتي السحابي**\n\n"
        "أرسل اسم المستخدم (`Username`) للحصول على الروابط والتحليل الفوري.",
        parse_mode="Markdown"
    )

async def handle_query(update: Update, context):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    profile_url = f"https://www.tiktok.com/@{username}"
    archive_url = f"https://web.archive.org/web/*/{profile_url}"
    
    buttons = [
        [InlineKeyboardButton("🔗 فتح الحساب الرسمي في تيك توك", url=profile_url)],
        [InlineKeyboardButton("🏛️ فحص الأرشيف التاريخي والسجلات", url=archive_url)]
    ]
    markup = InlineKeyboardMarkup(buttons)
    
    report = (
        f"📊 **تقرير الفحص الاستخباراتي السحابي**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **الحساب المستهدف:** `@{username}`\n"
        f"🌐 **الرابط المباشر:** {profile_url}\n"
        f"🛡️ **الحالة:** السيرفر يعمل بنجاح تام.\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"اختر أحد الأزرار أدناه للوصول الفوري:"
    )
    
    await update.message.reply_text(report, parse_mode="Markdown", reply_markup=markup)

@app.route('/')
def home():
    return "TikTok Cloud OSINT Bot is Live!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    import asyncio
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, telegram_app.bot)
    asyncio.run(telegram_app.process_update(update))
    return "OK", 200

telegram_app = None

if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    telegram_app = loop.run_until_complete(setup_bot())
    
    # تعيين الويب هوك تلقائياً مع نطاق Railway الخاص بك أو التشغيل المحلي
    # (ملاحظة: تأكد من ضبط الويب هوك أو الاعتماد على تشغيل الـ Flask)
    app.run(host="0.0.0.0", port=PORT)
