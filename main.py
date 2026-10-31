from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
import sqlite3
import asyncio
import traceback
from tiktokflow import TikTokAPI

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# قراءة المفتاح من إعدادات Render
API_KEY = os.getenv("TIKTOK_API_KEY", "")

def lookup_leaks(username: str):
    """البحث في قاعدة البيانات المسربة"""
    try:
        if not os.path.exists('leaks.db'):
            return None
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email, phone FROM leaks WHERE LOWER(username) = ?", (username.lower(),))
        result = cursor.fetchone()
        conn.close()
        return {"email": result[0], "phone": result[1]} if result else None
    except Exception:
        return None

def fetch_live_data_sync(username: str):
    """جلب البيانات الحية مع استخدام خادم توقيعات بديل ومستقر"""
    if not API_KEY:
        return {"error": "المفتاح غير موجود في إعدادات Render (TIKTOK_API_KEY)."}
    try:
        # ✅ استخدام خادم Euler Stream بدلاً من الخادم الافتراضي البطيء
        api = TikTokAPI(
            api_key=API_KEY,
            signing_server="https://tiktok.eulerstream.com"
        )
        
        user_info = api.user.info(username=username)
        
        if not user_info or "user" not in user_info:
            return {"error": "لم يتم العثور على بيانات لهذا المستخدم."}
            
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
            "Link": user.get("bio_link", {}).get("link", "(None)") if user.get("bio_link") else "(None)",
            "Email (API)": user.get("email", "(None)")
        }
    except Exception as e:
        print("=== خطأ حقيقي في الـ API ===")
        traceback.print_exc()
        print("=============================")
        return {"error": f"API Error: {str(e)}"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None, "error": None, "username": ""})

@app.post("/", response_class=HTMLResponse)
async def search(request: Request, username: str = Form(...)):
    username = username.strip().lstrip('@')
    
    leaked_data = lookup_leaks(username)
    live_data = await asyncio.to_thread(fetch_live_data_sync, username)
    
    error_msg = None
    if isinstance(live_data, dict) and "error" in live_data:
        error_msg = live_data["error"]
        live_data = None

    final_result = {
        "leaked_info": leaked_data,
        "live_stats": live_data,
    }
    return templates.TemplateResponse("index.html", {"request": request, "result": final_result, "error": error_msg, "username": username})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
