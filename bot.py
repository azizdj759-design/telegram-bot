import os
import logging
import json
import re
import aiohttp
from bs4 import BeautifulSoup
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
    return "Cyber OSINT Advanced Engine is active 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# نظام الفحص المتقاطع المتقدم للمنصات الرقمية المرتبطة بالبصمة
CROSS_PLATFORMS = {
    "GitHub": "https://github.com/{}",
    "Reddit": "https://www.reddit.com/user/{}/",
    "Telegram Channel": "https://t.me/{}",
    "Steam Profile": "https://steamcommunity.com/id/{}",
    "X (Twitter)": "https://x.com/{}"
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ **مرحباً بك في وحدة الاستخبارات السيبرانية المتقدمة (Cyber OSINT Core)**\n\n"
        "أرسل لي اسم المستخدم (`Username`) أو رابط تيك توك وسأقوم بتفعيل محرك البحث المتقاطع، تحليل البايو، واكتشاف الروابط الخفية المرتبطة.",
        parse_mode="Markdown"
    )

async def deep_scan_tiktok(username):
    url = f"https://www.tiktok.com/@{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=12) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
                
                start_marker = '<script id="SIGI_STATE" type="application/json">'
                end_marker = '</script>'
                start_pos = html.find(start_marker)
                if start_pos == -1:
                    return None
                
                start_pos += len(start_marker)
                end_pos = html.find(end_marker, start_pos)
                if end_pos == -1:
                    return None
                
                data = json.loads(html[start_pos:end_pos])
                
                # استخراج بيانات المستخدم المتقدمة
                user_info = {}
                user_module = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
                if user_module:
                    u = user_module.get("user", {})
                    s = user_module.get("stats", {})
                    user_info = {
                        "uid": u.get("id", "غير معروف"),
                        "nickname": u.get("nickname", "غير متوفر"),
                        "username": u.get("uniqueId", username),
                        "signature": u.get("signature", ""),
                        "bio_link": u.get("bioLink", {}).get("link", "لا يوجد"),
                        "followers": s.get("followerCount", 0),
                        "following": s.get("followingCount", 0),
                        "likes": s.get("heartCount", 0),
                        "videos": s.get("videoCount", 0),
                        "verified": u.get("verified", False),
                        "private": u.get("privateAccount", False),
                        "region": u.get("region", "مخفي/غير متاح")
                    }
                else:
                    # موديول بديل
                    um = data.get("UserModule", {}).get("users", {})
                    for uid, u in um.items():
                        s = data.get("UserModule", {}).get("stats", {}).get(uid, {})
                        user_info = {
                            "uid": uid,
                            "nickname": u.get("nickname", "غير متوفر"),
                            "username": u.get("uniqueId", username),
                            "signature": u.get("signature", ""),
                            "bio_link": "لا يوجد",
                            "followers": s.get("followerCount", 0),
                            "following": s.get("followingCount", 0),
                            "likes": s.get("heartCount", 0),
                            "videos": s.get("videoCount", 0),
                            "verified": u.get("verified", False),
                            "private": u.get("privateAccount", False),
                            "region": u.get("region", "مخفي/غير متاح")
                        }
                        break
                
                # استخراج الروابط الخارجية المخفية داخل البايو باستخدام RegEx
                links_in_bio = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', user_info.get("signature", ""))
                user_info["extracted_links"] = list(set(links_in_bio))
                
                return user_info
        except Exception as e:
            logging.error(f"Deep scan error: {e}")
            return None

async def check_cross_platform(session, name):
    found = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for platform, url_temp in CROSS_PLATFORMS.items():
        target_url = url_temp.format(name)
        try:
            async with session.get(target_url, headers=headers, timeout=5) as r:
                if r.status == 200:
                    found.append((platform, target_url))
        except:
            pass
    return found

async def handle_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("@", "").replace("https://www.tiktok.com/@", "").replace("https://tiktok.com/@", "")
    username = text.split("/")[0]
    
    status_msg = await update.message.reply_text(
        f"🕵️‍♂️ **جاري تفعيل محرك البحث السيبراني المتقدم...**\n"
        f"⏳ فحص قاعدة البيانات العميقة والتحليل المتقاطع لـ: `@{username}`",
        parse_mode="Markdown"
    )
    
    user_data = await deep_scan_tiktok(username)
    if not user_data:
        await status_msg.edit_text(f"❌ فشل استخراج البصمة الرقمية للحساب `@{username}`. قد يكون الحساب محذوفاً أو تم تفعيل الحماية القصوى.")
        return

    # فحص المنصات المتقاطعة بالتزامن
    async with aiohttp.ClientSession() as session:
        cross_results = await check_cross_platform(session, username)

    verified_str = "🛡️ موثق رسمياً" if user_data['verified'] else "عادي"
    privacy_str = "🔒 خاص (Private)" if user_data['private'] else "🌐 عام (Public)"
    
    report = (
        f"🔍 **تقرير الاستخبارات السيبرانية (OSINT Core Report)**\n\n"
        f"🆔 **معرف النظام (UID):** `{user_data['uid']}`\n"
        f"👤 **الاسم الظاهر:** {user_data['nickname']}\n"
        f"📌 **اسم المستخدم:** `@{user_data['username']}`\n"
        f"🌍 **منطقة السيرفر/الدولة:** `{user_data['region']}`\n"
        f"🛡️ **الحالة:** {privacy_str} | {verified_str}\n\n"
        f"📊 **تحليل الإحصائيات:**\n"
        f"👥 المتابعين: `{user_data['followers']:,}`\n"
        f"🫂 يتابعهم: `{user_data['following']:,}`\n"
        f"❤️ إجمالي الإعجابات: `{user_data['likes']:,}`\n"
        f"🎬 الفيديوهات: `{user_data['videos']:,}`\n\n"
        f"📝 **تحليل البايو والنص الوصفي:**\n"
        f"`{user_data['signature'] if user_data['signature'] else 'لا يوجد نص'}`\n\n"
        f"🔗 **رابط البايو المباشر:** {user_data['bio_link']}\n"
    )
    
    if user_data['extracted_links']:
        report += f"🌐 **روابط خارجية مكتشفة بالبايو:**\n" + "\n".join([f" - {l}" for l in user_data['extracted_links']]) + "\n"

    if cross_results:
        report += f"\n🌐 **نتائج البحث المتقاطع (منصات أخرى بنفس المعرف):**\n"
        for p, u in cross_results:
            report += f" - ✅ {p}: {u}\n"
    else:
        report += f"\n🌐 **البحث المتقاطع:** لم يتم العثور على تطابق بنفس الاسم في المنصات الأخرى.\n"

    profile_url = f"https://www.tiktok.com/@{username}"
    keyboard = [[InlineKeyboardButton(text="🔗 فتح الحساب الهدف", url=profile_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await status_msg.edit_text(report, parse_mode="Markdown", reply_markup=reply_markup)

def main():
    t = Thread(target=run_web)
    t.start()

    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_request))
    
    print("محرك الاستخبارات السيبرانية يعمل الآن بكامل طاقته...")
    application.run_polling()

if __name__ == '__main__':
    main()
