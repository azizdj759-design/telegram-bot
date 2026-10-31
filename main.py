from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from TikTokApi import TikTokApi
import os
import sqlite3
import asyncio

app = FastAPI()
templates = Jinja2Templates(directory="templates")

MS_TOKEN = os.getenv("MS_TOKEN", "ضع_الكوكي_هنا")
PROXY_URL = os.getenv("PROXY_URL", None)

def lookup_leaks(username: str):
    try:
        conn = sqlite3.connect('leaks.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email, phone FROM leaked_users WHERE username = ?", (username.lower(),))
        result = cursor.fetchone()
        conn.close()
        if result:
            return {"email": result[0], "phone": result[1]}
        return None
    except Exception:
        return None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "result": None, "error": None, "username": ""})

@app.post("/", response_class=HTMLResponse)
async def search(request: Request, username: str = Form(...)):
    username = username.strip().lstrip('@')
    leaked_data = lookup_leaks(username)
    live_data = None
    error_msg = None

    async def fetch_tiktok_data():
        # ✅ التهيئة الصحيحة: إنشاء نسخة من API ثم استدعاء create_sessions
        api = TikTokApi()
        await api.create_sessions(
            ms_tokens=[MS_TOKEN], 
            num_sessions=1, 
            sleep_after=3,
            browser='chromium',  # تحديد المتصفح بشكل صريح
            override_browser_args=["--no-sandbox", "--disable-dev-shm-usage"] # لتقليل استهلاك الذاكرة
        )
        
        # جلب بيانات المستخدم
        user = api.user(username=username)
        user_data = await user.info()
        
        # إغلاق الجلسة لتحرير الموارد
        await api.close_sessions() 
        return user_data

    try:
        user_data = await asyncio.wait_for(fetch_tiktok_data(), timeout=45.0)
        
        user_info = user_data.get("userInfo", {}).get("user", {})
        user_stats = user_data.get("userInfo", {}).get("stats", {})
        
        live_data = {
            "Username": user_info.get("uniqueId", "N/A"),
            "Name": user_info.get("nickname", "N/A"),
            "Region": user_info.get("region", "N/A"),
            "Private": "Yes ✅" if user_info.get("privateAccount") else "No ❌",
            "Verified": "Yes ✅" if user_info.get("verified") else "No ❌",
            "Followers": f"{user_stats.get('followerCount', 0):,}",
            "Following": f"{user_stats.get('followingCount', 0):,}",
            "Likes": f"{user_stats.get('heartCount', 0):,}",
            "Video Count": f"{user_stats.get('videoCount', 0):,}",
            "Bio": user_info.get("signature", "(None)"),
            "Link": user_info.get("bioLink", {}).get("link", "(None)") if user_info.get("bioLink") else "(None)"
        }
    except asyncio.TimeoutError:
        error_msg = "انتهى وقت الانتظار: تيك توك لم يستجب. قد يكون الـ IP محظوراً أو المتصفح يستهلك ذاكرة كبيرة."
    except Exception as e:
        error_msg = f"فشل الاتصال بتيك توك: {str(e)}"

    final_result = {
        "live_stats": live_data,
        "leaked_info": leaked_data,
        "status": "Success" if (live_data or leaked_data) else "Not Found"
    }

    return templates.TemplateResponse("index.html", {"request": request, "result": final_result, "error": error_msg, "username": username})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
