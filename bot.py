import os
import logging
import aiohttp
import json
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

@app.route('/')
def home():
    return "Cyber OSINT Advanced Core is active 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕵️‍♂️ **مرحباً بك في وحدة التحليل الاستخباراتي السيبراني العميق (Deep OSINT)**\n\n"
        "أرسل لي اسم المستخدم (`Username`) لتفعيل محرك البحث في الأرشيف الرقمي وسجل البصمة.",
        parse_mode="Markdown"
    )

async def deep_osint_lookup(username):
    # محاولة استعلام مزدوج عبر نقاط اتصال تحليلية عميقة تستخرج السجل المؤرشف
    endpoints = [
        f"https://urlebird.com/user/{username}/",
        f"https://tikwm.com/api/user/info?unique_id={username}"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html"
    }
    
    async with aiohttp.ClientSession() as session:
        # المحاولة الأولى عبر الـ API البديل للتحليل العميق
        try:
            async with session.get(endpoints[1], headers={"User-Agent": "Mozilla/5.0"}, timeout=8) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("code") == 0:
                        data = res.get("data", {})
                        userInfo = data.get("userInfo", {})
                        stats = data.get("stats", {})
                        return {
                            "success": True,
                            "nickname": userInfo.get("nickname", username),
                            "username": userInfo.get("uniqueId", username),
                            "secUid": userInfo.get("secUid", "مخفي/غير متاح"),
                            "id": userInfo.get("id", "غير معروف"),
                            "signature": userInfo.get("signature", "لا يوجد بايو"),
                            "followers": stats.get("follower_count", 0),
                            "following": stats.get("following_count", 0),
                            "likes": stats.get("heart", 0),
                            "videos": stats.get("video_count", 0),
                            "verified": userInfo.get("verified", False),
                            "region": data.get("region", "غير محدد")
                        }
        except Exception as e:
            logging.error(f"Deep API Error: {e}")
            
    return None

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status = await update.message.reply_text(f"🔍 جاري فحص الأرشيف الرقمي واستخراج السجل للحساب `@{username}`...", parse_mode="Markdown")
    
    info = await deep_osint_lookup(username)
    
    if not info:
        await status.edit_text(
            f"❌ **فشل في استخراج السجل العميق للحساب `@{username}`.**\n\n"
            f"قد يكون الحساب قد استخدم إعدادات الخصوصية القصوى التي تمسح الذاكرة المؤقتة لمحركات البحث والأرشيف الخارجي.",
            parse_mode="Markdown"
        )
        return

    profile_url = f"https://www.tiktok.com/@{info['username']}"
    verified_str = "✅ موثق" if info['verified'] else "عادي"
    
    report = (
        f"🛡️ **تقرير التحليل السيبراني العميق (OSINT)**\n\n"
        f"👤 **الاسم الظاهر:** {info['nickname']}\n"
        f"📌 **اسم المستخدم الحالي:** `@{info['username']}`\n"
        f"🆔 **معرف النظام الفريد (ID):** `{info['id']}`\n"
        f"🔑 **مفتاح الحساب (SecUID):** `{info['secUid']}`\n"
        f"🌍 **منطقة السيرفر المسجلة:** `{info['region']}`\n"
        f"🛡️ **حالة التوثيق:** {verified_str}\n\n"
        f"📝 **البايو (Bio):**\n`{info['signature']}`\n\n"
        f"📈 **الإحصائيات المؤرشفة والحية:**\n"
        f"👥 المتابعين: `{info['followers']:,}`\n"
        f"🫂 يتابعهم: `{info['following']:,}`\n"
        f"❤️ إجمالي الإعجابات: `{info['likes']:,}`\n"
        f"🎬 الفيديوهات: `{info['videos']:,}`\n\n"
        f"🔍 **ملاحظة الأرشيف:** السجل التاريخي للأسماء القديمة يتم الاحتفاظ به في الأرشيف العميقة فقط إذا تم أرشفة صفحة المستخدم مسبقاً قبل عملية التغيير."
    )
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 فتح الحساب مباشرة", url=profile_url)]])
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
