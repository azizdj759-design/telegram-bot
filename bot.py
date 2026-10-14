import os
import logging
import aiohttp
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

@app.route('/')
def home():
    return "TikTok OSINT Bot is active!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **مرحباً بك في بوت تتبع تيك توك المتقدم**\n\n"
        "أرسل لي الآن اسم المستخدم (`Username`) لسحب البيانات الإحصائية بدقة.",
        parse_mode="Markdown"
    )

async def fetch_data(username):
    url = f"https://tikwm.com/api/user/info?unique_id={username}"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("code") == 0:
                        u = res.get("data", {}).get("userInfo", {})
                        s = res.get("data", {}).get("stats", {})
                        return {
                            "nickname": u.get("nickname", username),
                            "username": u.get("uniqueId", username),
                            "followers": s.get("follower_count", 0),
                            "following": s.get("following_count", 0),
                            "likes": s.get("heart", 0),
                            "videos": s.get("video_count", 0),
                            "bio": u.get("signature", "لا يوجد بايو"),
                            "verified": u.get("verified", False)
                        }
        except Exception as e:
            logging.error(f"Error: {e}")
    return None

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status = await update.message.reply_text(f"⏳ جاري جلب بيانات `@{username}`...", parse_mode="Markdown")
    info = await fetch_data(username)
    
    if not info:
        await status.edit_text(f"❌ تعذر جلب بيانات الحساب `@{username}`. تأكد من صحة الاسم.")
        return

    profile_url = f"https://www.tiktok.com/@{info['username']}"
    report = (
        f"📊 **تقرير حساب تيك توك**\n\n"
        f"👤 **الاسم:** {info['nickname']}\n"
        f"📌 **المعرف:** `@{info['username']}`\n"
        f"📝 **البايو:**\n`{info['bio']}`\n\n"
        f"📈 **الإحصائيات:**\n"
        f"👥 المتابعين: `{info['followers']:,}`\n"
        f"🫂 يتابعهم: `{info['following']:,}`\n"
        f"❤️ الإعجابات: `{info['likes']:,}`\n"
        f"🎬 الفيديوهات: `{info['videos']:,}`"
    )
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 فتح الحساب", url=profile_url)]])
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
