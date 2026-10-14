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
    return "TikTok Pro OSINT Core is active 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **مرحباً بك في النظام الاستخباراتي المتقدم لتيك توك (Pro OSINT)**\n\n"
        "أرسل لي الآن اسم المستخدم (`Username`) وسأقوم بسحب معلوماته الإحصائية بدقة عالية.",
        parse_mode="Markdown"
    )

async def fetch_tiktok_data_pro(username):
    # محاولة الجلب عبر واجهة تيك توك الرسمية المباشرة المفتوحة للويب
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive"
    }
    
    url = f"https://www.tiktok.com/@{username}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=12) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    
                    # البحث عن كدان البيانات الرقمية المحقونة في صفحة الويب
                    import json
                    start_keyword = 'sigi-persisted-data">'
                    start_pos = html.find(start_keyword)
                    
                    if start_pos != -1:
                        start_pos += len(start_keyword)
                        end_pos = html.find('</script>', start_pos)
                        if end_pos != -1:
                            json_str = html[start_pos:end_pos]
                            data = json.loads(json_str)
                            
                            # استخراج بيانات المستخدم الإحصائية والوصفية
                            users_module = data.get("UserModule", {}).get("users", {})
                            stats_module = data.get("UserModule", {}).get("stats", {})
                            
                            for uid, uinfo in users_module.items():
                                stats = stats_module.get(uid, {})
                                return {
                                    "nickname": uinfo.get("nickname", username),
                                    "username": uinfo.get("uniqueId", username),
                                    "followers": stats.get("followerCount", 0),
                                    "following": stats.get("followingCount", 0),
                                    "likes": stats.get("heartCount", 0),
                                    "videos": stats.get("videoCount", 0),
                                    "bio": uinfo.get("signature", "لا يوجد بايو"),
                                    "verified": uinfo.get("verified", False)
                                }
        except Exception as e:
            logging.error(f"Scrape Error: {e}")
            
    # طريقة بديلة في حال الحظر المباشر لجلب البيانات عبر واجهة تحليل بديلة
    async with aiohttp.ClientSession() as session:
        try:
            fallback_url = f"https://tikwm.com/api/user/info?unique_id={username}"
            async with session.get(fallback_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    if res_json.get("code") == 0:
                        userInfo = res_json.get("data", {}).get("userInfo", {})
                        stats = res_json.get("data", {}).get("stats", {})
                        return {
                            "nickname": userInfo.get("nickname", username),
                            "username": userInfo.get("uniqueId", username),
                            "followers": stats.get("follower_count", 0),
                            "following": stats.get("following_count", 0),
                            "likes": stats.get("heart", 0),
                            "videos": stats.get("video_count", 0),
                            "bio": userInfo.get("signature", "لا يوجد بايو"),
                            "verified": userInfo.get("verified", False)
                        }
        except Exception as e:
            logging.error(f"Fallback API Error: {e}")
            
    return None

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "").replace("https://tiktok.com/@", "")
    username = text.split("/")[0].split("?")[0]
    
    status_msg = await update.message.reply_text(f"🔍 جاري تحليل واختراق جدران حماية تيك توك للحساب `@{username}`...", parse_mode="Markdown")
    
    info = await fetch_tiktok_data_pro(username)
    
    if not info:
        await status_msg.edit_text(f"❌ عذراً، تعذر سحب بيانات الحساب `@{username}`. قد يكون الحساب خاصاً تماماً أو غير موجود.")
        return

    profile_url = f"https://www.tiktok.com/@{info['username']}"
    verified_badge = "✅ حساب موثق" if info['verified'] else "👤 حساب عادية"
    
    report = (
        f"📊 **تقرير بيانات تيك توك المتقدم (Pro OSINT)**\n\n"
        f"👤 **الاسم الظاهر:** {info['nickname']}\n"
        f"📌 **اسم المستخدم:** `@{info['username']}`\n"
        f"🛡️ **الحالة:** {verified_badge}\n"
        f"📝 **البايو:**\n`{info['bio']}`\n\n"
        f"📈 **الإحصائيات الدقيقة:**\n"
        f"👥 **المتابعين:** `{info['followers']:,}`\n"
        f"🫂 **يتابعهم:** `{info['following']:,}`\n"
        f"❤️ **الإعجابات:** `{info['likes']:,}`\n"
        f"🎬 **الفيديوهات:** `{info['videos']:,}`"
    )
    
    keyboard = [[InlineKeyboardButton(text="🔗 فتح الحساب مباشرة", url=profile_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await status_msg.edit_text(report, parse_mode="Markdown", reply_markup=reply_markup)

def main():
    t = Thread(target=run_web)
    t.start()

    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_query))
    
    print("البوت الاحترافي المزدوج يعمل الآن...")
    application.run_polling()

if __name__ == 'main':
    main()
