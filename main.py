from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from curl_cffi import requests as curl_requests
import os
import sqlite3
import asyncio
import json
import re

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- 1. إنشاء قاعدة بيانات تلقائياً (محاكاة للتسريبات) ---
def init_db():
    conn = sqlite3.connect('leaks.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS leaks (username TEXT, email TEXT, phone TEXT)''')
    # ضع هنا أي حسابات تريد تجربتها
    dummy_data = [
        ('nox.qxx', 'issa.contact@gmail.com', '+212 612-345678'),
        ('test', 'admin@test.com', '+1 555-0199')
    ]
    cursor.executemany('INSERT OR IGNORE INTO leaks VALUES (?, ?, ?)', dummy_data)
    conn.commit()
    conn.close()

init_db()

def lookup_leaks_db(username: str):
    try:
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email, phone FROM leaks WHERE LOWER(username) = ?", (username.lower(),))
        result = cursor.fetchone()
        conn.close()
        return {"email": result[0], "phone": result[1]} if result else None
    except Exception:
        return None

def fetch_public_profile(username: str):
    url = f"https://www.tiktok.com/@{username}"
    try:
        # استخدام curl_cffi لمحاكاة متصفح حقيقي
        response = curl_requests.get(url, impersonate="chrome110", timeout=10)
        if response.status_code != 200:
            return None
        
        match = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', response.text)
        if match:
            json_data = json.loads(match.group(1))
            scope = json_data.get("__DEFAULT_SCOPE__", {})
            user_info = scope.get("webapp.user-detail", {}).get("userInfo", {})
            if user_info:
                user = user_info.get("user", {})
                stats = user_info.get("stats", {})
                return {
                    "username": user.get("uniqueId"),
                    "nickname": user.get("nickname"),
                    "followers": f"{stats.get('followerCount', 0):,}",
                    "likes": f"{stats.get('heartCount', 0):,}",
                    "bio": user.get("signature", "(None)"),
                }
        return None
    except Exception as e:
        print(f"Scraping Error: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None, "error": None, "query": ""})

@app.post("/", response_class=HTMLResponse)
async def search(request: Request, query: str = Form(None)): # وضعنا None لتجنب خطأ الحقل الفارغ
    if not query or query.strip() == "":
        return templates.TemplateResponse("index.html", {"request": request, "result": None, "error": "الرجاء إدخال اسم مستخدم صالح.", "query": ""})
        
    username = query.strip().lstrip('@')
    results = {}
    
    # 1. البحث في التسريبات
    leaked_data = lookup_leaks_db(username)
    if leaked_data:
        results["leaked_info"] = leaked_data

    # 2. الكشط المباشر
    live_data = await asyncio.to_thread(fetch_public_profile, username)
    if live_data:
        results["live_profile"] = live_data

    error_msg = None
    if not results:
        error_msg = "لم يتم العثور على أي بيانات لهذا المستخدم (قد يكون الحساب غير موجود أو تم حظر طلب الكشط من Render)."

    return templates.TemplateResponse("index.html", {"request": request, "result": results, "error": error_msg, "query": query})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
