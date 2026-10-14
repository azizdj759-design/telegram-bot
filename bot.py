import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# إعداد التسجيلات للرصد والمتابعة
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
PORT = int(os.environ.get("PORT", 10000))

app = Flask(__name__)
telegram_app = None

async def setup_bot():
    """بناء وتكوين نظام البوت الاستخباراتي"""
    app_bot = Application.builder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_target))
    await app_bot.initialize()
    return app_bot

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب الخيالية"""
    welcome_text = (
        "⚡ **النظام الاستخباراتي السيبراني - TikTok OSINT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ **الحالة:** متصل وجاهز للعمل بكفاءة عالية.\n"
        "🎯 **المهمة:** تحليل الحسابات واستخراج الروابط الاستخباراتية.\n\n"
        "أرسل الآن اسم المستخدم (`Username`) أو رابط الحساب لبدء الفحص الفوري."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأهداف وإرسال التقارير المرئية بدقة دون تكرار"""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    
    # تنظيف المدخلات واستخراج اسم المستخدم بدقة
    username = text.replace("@", "").replace("https://www.tiktok.com/@", "").split("/")[0].split("?")[0]
    
    profile_url = f"https://www.tiktok.com/@{username}"
    archive_url = f"https://web.archive.org/web/*/{profile_url}"
    google_dork = f"https://www.google.com/search?q=site:tiktok.com+{username}"

    # لوحة أزرار استخباراتية تفاعلية
    buttons = [
        [InlineKeyboardButton("🔗 فتح الملف الشخصي المباشر", url=profile_url)],
        [InlineKeyboardButton("🏛️ فحص الأرشيف التاريخي والسجلات", url=archive_url)],
        [InlineKeyboardButton("🔍 البحث العميق في محركات الويب", url=google_dork)]
    ]
    markup = InlineKeyboardMarkup(buttons)

    report = (
        f"📊 **التقرير الاستخباراتي المتقدم**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **الهدف المستهدف:** `@{username}`\n"
        f"🌐 **الرابط الرسمي:** {profile_url}\n"
        f"🛡️ **مستوى الأمان:** مشفر ومؤمن بالكامل.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"اختر أحد الأزرار أدناه للوصول السريع للبيانات:"
    )

    await update.message.reply_text(report, parse_mode="Markdown", reply_markup=markup)

@app.route('/')
def home():
    return "Cyber OSINT TikTok Bot is Online and Secured!"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """محطة الويب هوك الآمنة لمنع التكرار وضمان استقرار السيرفر"""
    global telegram_app
    try:
        json_data = request.get_json(force=True)
        if json_data and "message" in json_data:
            update = Update.de_json(json_data, telegram_app.bot)
            asyncio.run(telegram_app.process_update(update))
    except Exception as e:
        logging.error(f"Webhook processing error: {e}")
    return "OK", 200

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    telegram_app = loop.run_until_complete(setup_bot())
    app.run(host="0.0.0.0", port=PORT)
