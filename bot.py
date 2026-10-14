import os
import logging
import aiohttp
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

app = Flask(__name__)

@app.route('/')
def home():
    return "TikTok Fast Tracker Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 **مرحباً بك في بوت فحص وسحب بيانات تيك توك المباشر**\n\n"
        "أرسل لي الآن اسم المستخدم (`Username`) أو رابط الحساب، وسأقوم بسحب البيانات الإحصائية والبايو الحقيقي له.",
        parse_mode="Markdown"
    )

async def fetch_tiktok_data_fast(username):
    # استخدام واجهة API معالجة لتجاوز حظر Cloudflare/Render
    api_url = f"https://countik.com/api/userinfo/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://countik.com/"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success" or "followerCount" in data:
                        return {
                            "status": True,
                            "nickname": data.get("nickname", username),
                            "username": data.get("uniqueId", username),
                            "followers": data.get("followerCount", 0),
                            "following": data.get("followingCount", 0),
                            "likes": data.get("heartCount", 0),
                            "videos": data.get("videoCount", 0),
                            "bio": data.get("signature", "لا يوجد بايو"),
                            "avatar": data.get("avatar", ""),
                            "secUid": data.get("secUid", "غير متوفر")
                        }
        except Exception as e:
            logging.error(f"API 1 Error: {e}")
            
    return None

async def handle_tiktok_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "").replace("https://tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status_msg = await update.message.reply_text(f"⏳ جاري سحب بيانات الحساب `@{username}` وتجاوز الحظر...", parse_mode="Markdown")
    
    info = await fetch_tiktok_data_fast(username)
    
    if not info:
        await status_msg.edit_text(
            f"❌ تعذر جلب البيانات للحساب `@{username}`.\n"
            f"يرجى التأكد من أن الحساب موجود وصحيح وغير محذوف."
        )
        return

    profile_url = f"https://www.tiktok.com/@{info['username']}"
    
    report_text = (
        f"📊 **بيانات حساب تيك توك الحقيقية**\n\n"
        f"👤 **الاسم الظاهر:** {info['nickname']}\n"
        f"📌 **اسم المستخدم:** `@{info['username']}`\n"
        f"📝 **البايو (Bio):**\n`{info['bio']}`\n\n"
        f"📈 **الإحصائيات المباشرة:**\n"
        f"👥 **المتابعين:** `{info['followers']:,}`\n"
        f"🫂 **يتابعهم:** `{info['following']:,}`\n"
        f"❤️ **مجموع الإعجابات:** `{info['likes']:,}`\n"
        f"🎬 **عدد الفيديوهات:** `{info['videos']:,}`\n\n"
        f"🆔 **SecUID:** `{info['secUid'][:25]}...`"
    )
    
    keyboard = [[InlineKeyboardButton(text="🔗 فتح الحساب في تيك توك", url=profile_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await status_msg.edit_text(report_text, parse_mode="Markdown", reply_markup=reply_markup)

def main():
    t = Thread(target=run_web)
    t.start()

    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_tiktok_query))
    
    print("البوت السريع والمضمون يعمل الآن...")
    application.run_polling()

if __name__ == '__main__':
    main()
