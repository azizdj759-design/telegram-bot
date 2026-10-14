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
    return "TikTok Professional OSINT Bot is Active!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ **مرحباً بك في بوت تحليل تيك توك الاحترافي (OSINT Pro)**\n\n"
        "أرسل الآن اسم المستخدم (`Username`) أو رابط الحساب للحصول على البيانات الشاملة والإحصائيات الحية فوراً.",
        parse_mode="Markdown"
    )

async def fetch_professional_tiktok_data(username):
    # استخدام واجهة موثوقة وعالية الأداء لجلب بيانات الحساب بدقة
    url = f"https://tikwm.com/api/user/info?unique_id={username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    async strong_session = aiohttp.ClientSession()
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as resp:
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
                            "id": u.get("id", "غير متوفر"),
                            "signature": u.get("signature", "لا يوجد وصف (Bio)"),
                            "followers": s.get("follower_count", 0),
                            "following": s.get("following_count", 0),
                            "likes": s.get("heart", 0),
                            "videos": s.get("video_count", 0),
                            "verified": u.get("verified", False),
                            "region": data.get("region", "غير محدد"),
                            "avatar": u.get("avatarLarger", "")
                        }
        except Exception as e:
            logging.error(f"API Connection Error: {e}")
            
    return {"success": False}

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status = await update.message.reply_text(f"🔍 جاري استخراج البيانات الاستخباراتية للحساب `@{username}`...", parse_mode="Markdown")
    
    result = await fetch_professional_tiktok_data(username)
    
    profile_url = f"https://www.tiktok.com/@{username}"
    
    if not result.get("success"):
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 فتح الحساب مباشرة", url=profile_url)]])
        await status.edit_text(
            f"❌ عذراً، لم نتمكن من جلب بيانات الحساب `@{username}`.\nقد يكون الحساب خاصاً أو تم تغييره.",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    verified_badge = "✅ حساب موثق (Verified)" if result['verified'] else "👤 حساب عادي"
    
    report = (
        f"📊 **التقرير الاستخباراتي الشامل لتيك توك**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **الاسم الظاهر:** {result['nickname']}\n"
        f"📌 **اسم المستخدم:** `@{result['username']}`\n"
        f"🆔 **معرف الحساب (UID):** `{result['id']}`\n"
        f"🌍 **منطقة السيرفر:** `{result['region']}`\n"
        f"🛡️ **حالة الحساب:** {verified_badge}\n\n"
        f"📝 **البايو (Bio):**\n`{result['signature']}`\n\n"
        f"📈 **إحصائيات الأداء والحساب:**\n"
        f"👥 المتابعين: `{result['followers']:,}`\n"
        f"🫂 يتابعهم: `{result['following']:,}`\n"
        f"❤️ إجمالي الإعجابات: `{result['likes']:,}`\n"
        f"🎬 عدد الفيديوهات: `{result['videos']:,}`\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    
    buttons = [
        [InlineKeyboardButton("🔗 فتح الملف الشخصي في تيك توك", url=profile_url)],
        [InlineKeyboardButton("🏛️ فحص الأرشيف التاريخي", url=f"https://web.archive.org/web/*/{profile_url}")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    
    await status.edit_text(report, parse_mode="Markdown", reply_markup=markup)

def main():
    Thread(target=run_web).start()
    
    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_query))
    
    print("Professional OSINT Bot is running...")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
