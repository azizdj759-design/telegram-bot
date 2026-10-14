import os
import logging
import aiohttp
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

@app.route('/')
def home():
    return "TikTok OSINT Pro Bot is Active!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ **مرحباً بك في بوت تيك توك الاستخباراتي المتقدم**\n\n"
        "أرسل اسم المستخدم (`Username`) للحصول على الأداة الاستخباراتية الفورية والرابط المباشر.",
        parse_mode="Markdown"
    )

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status = await update.message.reply_text(f"🔍 جاري معالجة وفحص الحساب `@{username}`...", parse_mode="Markdown")
    
    profile_url = f"https://www.tiktok.com/@{username}"
    archive_url = f"https://web.archive.org/web/*/{profile_url}"
    
    # تجهيز أزرار تفاعلية احترافية تضمن للمستخدم الوصول الفوري بغض النظر عن القيود
    buttons = [
        [InlineKeyboardButton("🔗 فتح الحساب الرسمي في تيك توك", url=profile_url)],
        [InlineKeyboardButton("🏛️ فحص الأرشيف التاريخي والسجلات السابقة", url=archive_url)],
        [InlineKeyboardButton("🔍 البحث الشامل في محركات الويب", url=https://www.google.com/search?q=site:tiktok.com+@{username})]
    ]
    markup = InlineKeyboardMarkup(buttons)
    
    report = (
        f"📊 **تقرير الفحص الاستخباراتي للحساب**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **اسم المستخدم المستهدف:** `@{username}`\n"
        f"🌐 **رابط الملف الشخصي:** {profile_url}\n"
        f"🛡️ **حالة النظام:** جاهز للاستعلام والتحليل المتقدم.\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"اختر أحد الأزرار أدناه لفتح الحساب أو تتبع سجله التاريخي والأرشيف المخبأ فوراً:"
    )
    
    await status.edit_text(report, parse_mode="Markdown", reply_markup=markup)

def main():
    Thread(target=run_web).start()
    
    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_query))
    
    print("Bot is running stable...")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
