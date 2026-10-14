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
    return "TikTok Pro Info Bot is active 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **مرحباً بك في بوت تحليل ومعلومات تيك توك الاحترافي (Pro Info)**\n\n"
        "أرسل لي الآن اسم المستخدم (`Username`) أو رابط الحساب، وسأقوم بجلب كافة المعلومات المتاحة له بدقة عالية.",
        parse_mode="Markdown"
    )

async def fetch_tiktok_pro_data(username):
    # استخدام واجهة اتصال متقدمة ومستقرة لجلب البيانات العامة الحية
    url = f"https://tikwm.com/api/user/info?unique_id={username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
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
                            "id": u.get("id", "غير معروف"),
                            "secUid": u.get("secUid", "غير متوفر"),
                            "signature": u.get("signature", "لا يوجد وصف (Bio)"),
                            "followers": s.get("follower_count", 0),
                            "following": s.get("following_count", 0),
                            "likes": s.get("heart", 0),
                            "videos": s.get("video_count", 0),
                            "verified": u.get("verified", False),
                            "private": u.get("secret", False),
                            "region": data.get("region", "غير محدد")
                        }
        except Exception as e:
            logging.error(f"Pro API Error: {e}")
            
    return None

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status = await update.message.reply_text(f"⏳ جاري الاتصال وجلب معلومات الحساب `@{username}`...", parse_mode="Markdown")
    
    info = await fetch_tiktok_pro_data(username)
    
    if not info:
        # طريقة احتياطية في حال تعذر جلب الـ API لضمان عدم توقف البوت
        profile_url = f"https://www.tiktok.com/@{username}"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 فتح الحساب مباشرة", url=profile_url)]])
        await status.edit_text(
            f"❌ **عذراً، تعذر جلب البيانات الإحصائية للحساب `@{username}`.**\n\n"
            f"قد يكون الحساب محذوفاً أو أن حمايته مفعلة. يمكنك فتحه مباشرة عبر الزر أدناه:",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    profile_url = f"https://www.tiktok.com/@{info['username']}"
    verified_badge = "✅ حساب موثق (Verified)" if info['verified'] else "👤 حساب عادي"
    privacy_status = "🔒 حساب خاص (Private)" if info['private'] else "🌐 حساب عام (Public)"
    
    report = (
        f"📊 **تقرير معلومات تيك توك الشامل**\n\n"
        f"👤 **الاسم الظاهر:** {info['nickname']}\n"
        f"📌 **اسم المستخدم:** `@{info['username']}`\n"
        f"🌍 **منطقة السيرفر / الدولة:** `{info['region']}`\n"
        f"🛡️ **الحالة:** {privacy_status} | {verified_badge}\n"
        f"🆔 **معرف النظام (ID):** `{info['id']}`\n\n"
        f"📝 **البايو (Bio):**\n`{info['signature']}`\n\n"
        f"📈 **الإحصائيات الحية:**\n"
        f"👥 **المتابعين:** `{info['followers']:,}`\n"
        f"🫂 **يتابعهم:** `{info['following']:,}`\n"
        f"❤️ **مجموع الإعجابات:** `{info['likes']:,}`\n"
        f"🎬 **عدد الفيديوهات المنشورة:** `{info['videos']:,}`"
    )
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 فتح الحساب في تيك توك", url=profile_url)]])
    await status.edit_text(report, parse_mode="Markdown", reply_markup=markup)

def main():
    Thread(target=run_web).start()
    
    # التوكن الخاص بك
    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_query))
    app_bot.run_polling()

if __name__ == '__main__':
    main()
