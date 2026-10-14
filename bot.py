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
    return "TikTok Bot is active!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **مرحباً بك في بوت تتبع تيك توك المتقدم**\n\n"
        "أرسل لي الآن اسم المستخدم (`Username`) وسأقوم بتزويدك برابط الحساب المباشر ومعلوماته بدقة.",
        parse_mode="Markdown"
    )

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status = await update.message.reply_text(f"⏳ جاري التحقق من الحساب `@{username}`...", parse_mode="Markdown")
    
    profile_url = f"https://www.tiktok.com/@{username}"
    
    # فحص تواجد الحساب عبر محاكاة متصفح حقيقي
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(profile_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    if "This account is private" in html:
                        status_msg = f"🔒 الحساب `@{username}` موجود ولكنه **خاص (Private)**."
                    elif "Couldn't find this account" in html or "not found" in html.lower():
                        await status.edit_text(f"❌ عذراً، الحساب `@{username}` غير موجود أو محذوف.")
                        return
                    else:
                        status_msg = f"✅ **تم التحقق من الحساب بنجاح!**"
                else:
                    await status.edit_text(f"❌ لم يتم العثور على حساب نشط باسم `@{username}`.")
                    return
        except Exception:
            # في حال الحظر السحابي، نعتمد على توفير الرابط المباشر والأداة المؤكدة للمستخدم
            status_msg = f"⚠️ تم العثور على رابط الحساب المباشر:"

    report = (
        f"📊 **نتيجة فحص تيك توك**\n\n"
        f"📌 **اسم المستخدم:** `@{username}`\n"
        f"💬 {status_msg}\n\n"
        f"🔗 **الرابط المباشر للفتح والفحص اليدوي:**\n{profile_url}"
    )
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 فتح الحساب في تيك توك", url=profile_url)]] )
    await status.edit_text(report, parse_mode="Markdown", reply_markup=markup)

def main():
    Thread(target=run_web).start()
    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_query))
    app_bot.run_polling()

if __name__ == '__main__':
    main()
