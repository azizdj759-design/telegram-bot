from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from curl_cffi import requests as curl_requests
import os
import sqlite3
import asyncio
import json
import re
import httpx

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- إعدادات قاعدة البيانات المسربة ---
def init_db():
    conn = sqlite3.connect('leaks.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS leaks (identifier TEXT PRIMARY KEY, email TEXT, phone TEXT, username TEXT)''')
    # بيانات تجريبية للاختبار
    dummy_data = [
        ('test@example.com', 'test@example.com', '+1234567890', 'testuser'),
        ('+1234567890', 'test@example.com', '+1234567890', 'testuser')
    ]
    cursor.executemany('INSERT OR IGNORE INTO leaks VALUES (?, ?, ?, ?)', dummy_data)
    conn.commit()
    conn.close()

init_db()

def lookup_leaks_db(identifier: str):
    """البحث في قاعدة البيانات المسربة"""
    try:
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email, phone, username FROM leaks WHERE LOWER(identifier) = ?", (identifier.lower(),))
        result = cursor.fetchone()
        conn.close()
        if result:
            return {"email": result[0], "phone": result[1], "username": result[2], "source": "Leaked Database"}
        return None
    except Exception:
        return None

async def check_email_via_password_reset(email: str):
    """التحقق من وجود البريد الإلكتروني عبر واجهة استعادة كلمة المرور"""
    # محاكاة طلب إلى واجهة برمجة التطبيقات الداخلية لتيك توك
    # ملاحظة: هذا يتطلب ترويسات محددة ومحاكاة دقيقة
    url = "https://api2-19-h2.musical.ly/aweme/v1/passport/find-password-via-email/"
    headers = {
        "User-Agent": "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 12; en; Redmi Note 8; Build/SP1A.210812.016; Cronet/58.0.2991.0)"
    }
    payload = {"email": email}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("message") == "success" or "Sent successfully" in str(data):
                    return {"status": "valid", "message": "البريد الإلكتروني مرتبط بحساب تيك توك"}
            return {"status": "invalid", "message": "البريد الإلكتروني غير مرتبط بأي حساب"}
    except Exception as e:
        return {"status": "error", "message": f"فشل التحقق: {str(e)}"}

def fetch_public_profile(username: str):
    """جلب البيانات العامة من صفحة الحساب"""
    url = f"https://www.tiktok.com/@{username}"
    try:
        response = curl_requests.get(url, impersonate="chrome110", timeout=15)
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
                    "region": user.get("region"),
                    "followers": stats.get("followerCount"),
                    "likes": stats.get("heartCount"),
                    "bio": user.get("signature"),
                }
        return None
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None, "error": None, "query": ""})

@app.post("/", response_class=HTMLResponse)
async def search(request: Request, query: str = Form(...)):
    query = query.strip()
    results = {}
    error_msg = None

    # 1. البحث في قاعدة البيانات المسربة
    leaked_data = lookup_leaks_db(query)
    if leaked_data:
        results["leaked_info"] = leaked_data

    # 2. إذا كان الاستعلام يبدو كبريد إلكتروني، تحقق منه
    if "@" in query:
        email_check = await check_email_via_password_reset(query)
        results["email_check"] = email_check
    
    # 3. جلب البيانات العامة (سواء كان الاستعلام اسم مستخدم أو بريد)
    # سنحاول البحث عن اسم المستخدم في النتائج المسربة أولاً
    username_to_check = query
    if leaked_data and leaked_data.get("username"):
        username_to_check = leaked_data["username"]
    elif "@" not in query:
        username_to_check = query.lstrip('@')
    else:
        username_to_check = None # لا يمكن استخدام البريد كاسم مستخدم مباشرة

    if username_to_check:
        live_data = await asyncio.to_thread(fetch_public_profile, username_to_check)
        if live_data:
            results["live_profile"] = live_data

    if not results:
        error_msg = "لم يتم العثور على أي نتائج في المصادر المتاحة."

    return templates.TemplateResponse("index.html", {"request": request, "result": results, "error": error_msg, "query": query})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
