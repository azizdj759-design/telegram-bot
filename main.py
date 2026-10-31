from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from TikTokApi import TikTokApi
import os
import sqlite3
import asyncio  # <-- أضفنا هذه المكتبة

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

    # دالة داخلية لجلب البيانات
    async def fetch_tiktok_data():
        async with TikTokApi() as api:
            kwargs = {"ms_tokens": [MS_TOKEN], "num_sessions": 1, "sleep_after": 3}
            if PROXY_URL:
                kwargs["proxies"] = [PROXY_URL]
            await api.create_sessions(**kwargs)
            user = api.user(username=username)
            return await user.info()

    try:
        # إجبار الكود على التوقف بعد 25 ثانية كحد أقصى
        user_data = await asyncio.wait_for(fetch_tiktok_data(), timeout=25.0)
        
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
        error_msg = "انتهى وقت الانتظار: تيك توك لم يستجب. (قد يكون الـ IP محظوراً أو المتصفح يستهلك ذاكرة كبيرة)."
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
