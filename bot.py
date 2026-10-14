import asyncio
import logging
import re
from bs4 import BeautifulSoup
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# تفعيل تسجيل الأخطاء
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# قائمة واسعة للمنصات التي سيتم فحصها
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
                
                # استخراج عنوان الصفحة لمعرفة الاسم الظاهر إن أمكن
                title = soup.title.string.strip() if soup.title else platform
                
                # البحث عن أي روابط تواصل اجتماعي أخرى داخل الصفحة (في البايو)
                found_links = re.findall(r'https?://(?:www\.)?(?:instagram|twitter|tiktok|facebook|youtube)\.com/[a-zA-Z0-9_.-]+', html)
                unique_links = list(set([l for l in found_links if username not in l]))

                return {
                    "platform": platform,
                    "exists": True,
                    "url": url,
                    "title": title[:40],
                    "extra_links": unique_links[:3] # جلب أول 3 روابط خارجية مكتشفة
                }
            else:
                return {"platform": platform, "exists": False}
    except Exception:
        return {"platform": platform, "exists": False, "error": True}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 **مرحباً بك في بوت التتبع المتقدم (OSINT Username Tracker)**\n\n"
        "أرسل لي اسم المستخدم (`Username`) وسأقوم بفحصه بشكل تزمني فائق السرعة عبر جميع المنصات المتاحة لاستخراج الحسابات والروابط.",
        parse_mode="Markdown"
    )

async def check_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().replace("@", "")
    status_msg = await update.message.reply_text(f"⏳ جاري فحص اسم المستخدم `{username}` عبر جميع المنصات...", parse_mode="Markdown")
    
    # تنفيذ الفحص التزمني المتوازي لجميع المنصات في نفس اللحظة
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
            # إضافة أزرار تفاعلية للانتقال السريع للحسابات المكتشفة
            keyboard.append([InlineKeyboardButton(text=f"فتح {platform_name}", url=url)])

    if found_count == 0:
        text_results.append("❌ لم يتم العثور على حسابات علنية بنفس اسم المستخدم على المنصات المفحوصة.")

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await status_msg.edit_text(
        "\n".join(text_results),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

if __name__ == '__main__':
    # ⚠️ استبدل النص التالي بالتوكن الحقيقي الذي أخذته من BotFather
    TOKEN = "8895436088:AAHPs09G8n1d2n2EREXZIzy9eB5wN1ykqUc"
    
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), check_username))
    
    print("البوت المتطور يعمل الآن...")
    application.run_polling()
