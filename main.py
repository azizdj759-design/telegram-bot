from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import sqlite3
import asyncio
from tiktokflow import TikTokAPI

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- 1. الحصول على مفتاح API مجاني ---
# اذهب إلى بوت تيليجرام: @tiktok_private_api_bot
# أرسل الأمر /key وانسخ المفتاح الذي سيظهر لك
API_KEY = os.getenv("TIKTOK_API_KEY", "ضع_المفتاح_هنا")

# --- 2. دالة البحث في قاعدة البيانات المسربة ---
def lookup_leaks(username: str):
    try:
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        # البحث عن اسم المستخدم (بدون حساسية لحالة الأحرف)
        cursor.execute("SELECT email, phone FROM leaks WHERE LOWER(username) = ?", (username.lower(),))
        result = cursor.fetchone()
        conn.close()
        return {"email": result[0], "phone": result[1]} if result else None
    except Exception:
        return None

# --- 3. دالة جلب البيانات الحية عبر Private API ---
async def fetch_live_data(username: str):
    try:
        # تهيئة الاتصال باستخدام المفتاح
        api = TikTokAPI(api_key=API_KEY)
        
        # جلب بيانات المستخدم
        user_info = api.user.info(username=username)
        
        if not user_info or "user" not in user_info:
            return None
            
        user = user_info["user"]
        stats = user_info.get("stats", {})
        
        return {
            "Username": user.get("unique_id", "N/A"),
            "Name": user.get("nickname", "N/A"),
            "Region": user.get("region", "N/A"),
            "Private": "Yes ✅" if user.get("private_account") else "No ❌",
            "Verified": "Yes ✅" if user.get("verified") else "No ❌",
            "Followers": f"{stats.get('follower_count', 0):,}",
            "Following": f"{stats.get('following_count', 0):,}",
            "Likes": f"{stats.get('heart_count', 0):,}",
            "Video Count": f"{stats.get('video_count', 0):,}",
            "Bio": user.get("signature", "(None)"),
            "Link": user.get("bio_link", {}).get("link", "(None)") if user.get("bio_link") else "(None)"
        }
    except Exception as e:
        print(f"Error fetching live data: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None, "error": None, "username": ""})

@app.post("/", response_class=HTMLResponse)
async def search(request: Request, username: str = Form(...)):
    username = username.strip().lstrip('@')
    
    # 1. البحث في التسريبات أولاً
    leaked_data = lookup_leaks(username)
    
    # 2. جلب البيانات الحية (إذا لم تكن في التسريبات أو حتى لو كانت، لجلب الإحصائيات المحدثة)
    live_data = await fetch_live_data(username)
    
    final_result = {
        "leaked_info": leaked_data,
        "live_stats": live_data,
    }

    return templates.TemplateResponse("index.html", {"request": request, "result": final_result, "error": None, "username": username})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
