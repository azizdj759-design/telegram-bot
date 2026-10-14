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
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), process_target))
    await app_bot.initialize()
    return app_bot

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("OSINT Core Online. Send TikTok username.")

async def process_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    target = text.replace("@", "").replace("https://www.tiktok.com/@", "").split("/")[0].split("?")[0]
    
    api_url = f"https://tikwm.com/api/user/info?unique_id={target}"
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("code") == 0:
                        data = res.get("data", {})
                        u = data.get("userInfo", {})
                        s = data.get("stats", {})
                        
                        report = (
                            f"🎯 TARGET: @{u.get('uniqueId', target)}\n"
                            f"👤 NICKNAME: {u.get('nickname', 'N/A')}\n"
                            f"🆔 UID: {u.get('id', 'N/A')}\n"
                            f"🌍 REGION: {data.get('region', 'N/A')}\n"
                            f"🛡️ VERIFIED: {'YES' if u.get('verified') else 'NO'}\n"
                            f"📝 BIO: {u.get('signature', 'None')}\n"
                            f"----------------------------\n"
                            f"👥 FOLLOWERS: {s.get('follower_count', 0):,}\n"
                            f"🫂 FOLLOWING: {s.get('following_count', 0):,}\n"
                            f"❤️ LIKES: {s.get('heart', 0):,}\n"
                            f"🎬 POSTS: {s.get('video_count', 0):,}"
                        )
                        await update.message.reply_text(report)
                        return
        except Exception as e:
            logging.error(f"Error: {e}")

    await update.message.reply_text(f"❌ Failed to fetch data for @{target}. Account might be private or restricted.")

@app.route('/')
def home():
    return "Bot is running clean."

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    global telegram_app
    try:
        json_data = request.get_json(force=True)
        if json_data and "message" in json_data:
            update = Update.de_json(json_data, telegram_app.bot)
            asyncio.run(telegram_app.process_update(update))
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    return "OK", 200

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    telegram_app = loop.run_until_complete(setup_bot())
    app.run(host="0.0.0.0", port=PORT)
