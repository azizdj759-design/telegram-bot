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
    return "OSINT Archive TikTok Bot is Online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔎 **مرحباً بك في بوت استعلام أرشيف تيك توك المتقدم (OSINT Cloud)**\n\n"
        "أرسل اسم المستخدم (`Username`) لاستخراج البيانات من قواعد البيانات والأرشيف العالمي المتاح.",
        parse_mode="Markdown"
    )

async def fetch_archive_data(username):
    """
    استعلام ذاكرة المعلومات والأرشيف عبر واجهات البيانات المستقرة
    """
    url = f"https://tikwm.com/api/user/info?unique_id={username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=12) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("code") == 0:
                        data = res.get("data", {})
                        u = data.get("userInfo", {})
                        s = data.get("stats", {})
                        return {
                            "success": True,
                            "nickname": u.get("nickname", username),
                            "username": u.get("uniqueId", username),
                            "id": u.get("id", "غير محدد"),
                            "signature": u.get("signature", "لا يوجد وصف محدد"),
                            "followers": s.get("follower_count", 0),
                            "following": s.get("following_count", 0),
                            "likes": s.get("heart", 0),
                            "videos": s.get("video_count", 0),
                            "verified": u.get("verified", False),
                            "region": data.get("region", "عام")
                        }
        except Exception as e:
            logging.error(f"Archive Fetch Error: {e}")
            
    return None

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status = await update.message.reply_text(f"🔍 جاري البحث عن `@{username}` في قواعد البيانات والأرشيف...", parse_mode="Markdown")
    
    info = await fetch_archive_data(username)
    
    # روابط استخباراتية إضافية سريعة ومفتوحة المصدر (Wayback Archive & Google Cache)
    archive_url = f"https://web.archive.org/web/*/{username}"
    profile_url = f"https://www.tiktok.com/@{username}"
    
    buttons = [
        [InlineKeyboardButton("🔗 فتح الصفحة الحالية", url=profile_url)],
        [InlineKeyboardButton("🏛️ فحص الأرشيف التاريخي (Wayback)", url=archive_url)]
    ]
    markup = InlineKeyboardMarkup(buttons)

    if not info:
        await status.edit_text(
            f"⚠️ **تعذر استخراج البيانات اللحظية للحساب `@{username}`**\n\n"
            f"يمكنك الاطلاع على الأرشيف التاريخي المخزن مباشرة عبر الرابط أدناه:",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    verified_badge = "✅ حساب موثق" if info['verified'] else "👤 حساب عادي"
    
    report = (
        f"📊 **تقرير ذاكرة البيانات الحرة (TikTok OSINT)**\n\n"
        f"👤 **الاسم:** {info['nickname']}\n"
        f"📌 **اسم المستخدم:** `@{info['username']}`\n"
        f"🆔 **معرف النظام (ID):** `{info['id']}`\n"
        f"🌍 **منطقة التسجيل:** `{info['region']}`\n"
        f"🛡️ **الحالة:** {verified_badge}\n\n"
        f"📝 **الوصف (Bio):**\n`{info['signature']}`\n\n"
        f"📈 **الإحصائيات المتاحة:**\n"
        f"👥 المتابعين: `{info['followers']:,}`\n"
        f"🫂 يتابعهم: `{info['following']:,}`\n"
        f"❤️ الإعجابات: `{info['likes']:,}`\n"
        f"🎬 عدد الفيديوهات: `{info['videos']:,}`"
    )
    
    await status.edit_text(report, parse_mode="Markdown", reply_markup=markup)

def main():
    Thread(target=run_web).start()
    
    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_query))
    
    print("Cloud OSINT Bot is running...")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
