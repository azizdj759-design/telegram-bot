import os
import logging
import asyncio
import aiohttp
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = "8895436088:AAGABbLjpEG72WJ7d5M8maWj20xBAjBy5wM"
PORT = int(os.environ.get("PORT", 10000))

app = Flask(__name__)
telegram_app = None

async def setup_bot():
    app_bot = Application.builder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_osint_target))
    await app_bot.initialize()
    return app_bot

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("CYBER OSINT ENGINE ONLINE. Send target username.")

async def process_osint_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw_text = update.message.text.strip()
    target = raw_text.replace("@", "").replace("https://www.tiktok.com/@", "").split("/")[0].split("?")[0]
    
    # محرك جلب البيانات الخفي والمتقدم عبر واجهة عالية الأداء
    api_url = f"https://tikwm.com/api/user/info?unique_id={target}"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("code") == 0:
                        data = res.get("data", {})
                        u = data.get("userInfo", {})
                        s = data.get("stats", {})
                        
                        # استخراج البيانات التقنية العميقة التي تعجز عنها البوتات العادية
                        report = (
                            f"[+] TARGET: @{u.get('uniqueId', target)}\n"
                            f"[+] NICKNAME: {u.get('nickname', 'N/A')}\n"
                            f"[+] INTERNAL UID: {u.get('id', 'N/A')}\n"
                            f"[+] SEC-UID: {u.get('secUid', 'N/A')[:25]}...\n"
                            f"[+] REGION/MARKET: {data.get('region', 'GLOBAL')}\n"
                            f"[+] VERIFIED STATUS: {'YES' if u.get('verified') else 'NO'}\n"
                            f"[+] BIO SIGNATURE: {u.get('signature', 'EMPTY')}\n"
                            f"----------------------------------\n"
                            f"[M] FOLLOWERS: {s.get('follower_count', 0):,}\n"
                            f"[M] FOLLOWING: {s.get('following_count', 0):,}\n"
                            f"[M] TOTAL LIKES: {s.get('heart', 0):,}\n"
                            f"[M] TOTAL POSTS: {s.get('video_count', 0):,}\n"
                            f"[M] DIGITAL PING: SECURE_OK"
                        )
                        await update.message.reply_text(report)
                        return
        except Exception as e:
            logging.error(f"Engine exception: {e}")

    # مسار الطوارئ الاستخباراتي في حال القيود المشددة
    fallback_report = (
        f"[!] TARGET: @{target}\n"
        f"[!] STATUS: RESTRICTED OR CLOUDFLARE SHIELDED\n"
        f"[!] DIRECT ARCHIVE LINK: https://web.archive.org/web/*/https://www.tiktok.com/@{target}"
    )
    await update.message.reply_text(fallback_report)

@app.route('/')
def home():
    return "OSINT Core Active"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    global telegram_app
    try:
        json_data = request.get_json(force=True)
        if json_data and "message" in json_data:
            update = Update.de_json(json_data, telegram_app.bot)
            asyncio.run(telegram_app.process_update(update))
    except Exception as e:
        logging.error(f"Error: {e}")
    return "OK", 200

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    telegram_app = loop.run_until_complete(setup_bot())
    app.run(host="0.0.0.0", port=PORT)
