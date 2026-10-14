import asyncio
import logging
import re
import os
from bs4 import BeautifulSoup
import aiohttp
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# تفعيل تسجيل الأخطاء
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# إنشاء خادم ويب وهمي لكي تستمر خدمة Render في العمل دون أن تغلق
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# قائمة المنصات للفحص
PLATFORMS = {
    "GitHub": "https://github.com/{}",
    "Reddit": "https://www.reddit.com/user/{}/",
    "Pinterest": "https://www.pinterest.com/{}/",
    "Telegram": "https://t.me/{}",
    "Medium": "https://medium.com/@{}",
    "Twitch": "https://www.twitch.tv/{}",
    "Steam": "https://steamcommunity.com/id/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "X (Twitter)": "https://x.com/{}",
    "Instagram": "https://www.instagram.com/{}/"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

async def fetch_platform(session, platform, url_template, username):
    url = url_template.format(username)
    try:
        async with session.get(url, headers=HEADERS, timeout=7) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.string.strip() if soup.title else platform
                found_links = re.findall(r'https?://(?:www\.)?(?:instagram|twitter|tiktok|facebook|youtube)\.com/[a-zA-Z0-9_.-]+', html)
                unique_links = list(set([l for l in found_links if username not in l]))

                return {
                    "platform": platform,
                    "exists": True,
                    "url": url,
                    "title": title[:40],
                    "extra_links": unique_links[:3]
                }
            else:
                return {"platform": platform, "exists": False}
    except Exception:
        return {"platform": platform, "exists": False, "error": True}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 **مرحباً بك في بوت التتبع المتقدم (OSINT Username Tracker)**\n\n"
        "أرسل لي اسم المستخدم (`Username`) وسأقوم بفحصه فوراً عبر المنصات المتاحة.",
        parse_mode="Markdown"
    )

async def check_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().replace("@", "")
    status_msg = await update.message.reply_text(f"⏳ جاري فحص اسم المستخدم `{username}` عبر جميع المنصات...", parse_mode="Markdown")
    
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_platform(session, platform, url_template, username)
            for platform, url_template in PLATFORMS.items()
        ]
        results = await asyncio.gather(*tasks)

    found_count = 0
    text_results = [f"📊 **نتائج البحث عن الحساب:** `{username}`\n"]
    keyboard = []

    for res in results:
        if res.get("exists"):
            found_count += 1
            platform_name = res["platform"]
            url = res["url"]
            
            line = f"✅ **{platform_name}**: [زيارة الحساب]({url})"
            if res.get("extra_links"):
                line += f"\n   └ 🔗 **روابط بداخل الصفحة:** " + ", ".join(res["extra_links"])
            
            text_results.append(line)
            keyboard.append([InlineKeyboardButton(text=f"فتح {platform_name}", url=url)])

    if found_count == 0:
        text_results.append("❌ لم يتم العثور على حسابات علنية بنفس اسم المستخدم.")

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await status_msg.edit_text(
        "\n".join(text_results),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

def main():
    # تشغيل خادم الويب في خلفية منفصلة ليتوافق مع قيود Render
    t = Thread(target=run_web)
    t.start()

    # تشغيل بوت تيليغرام بالتوكن الجديد
    TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), check_username))
    
    print("البوت وخادم الويب يعملان معاً...")
    application.run_polling()

if __name__ == '__main__':
    main()
