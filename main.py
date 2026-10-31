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

    def fetch_tiktok_data():
        url = f"https://www.tiktok.com/@{username}"
        proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
        
        try:
            # استخدام curl_cffi لمحاكاة متصفح Chrome 110
            response = curl_requests.get(
                url,
                impersonate="chrome110",
                proxies=proxies,
                timeout=15,
                allow_redirects=True
            )
            
            # إذا تم حظر الطلب أو لم يتم العثور على الحساب
            if response.status_code != 200:
                return {"error": f"فشل الطلب، كود الحالة: {response.status_code}"}
            
            html = response.text
            
            # استخراج JSON المخفي في الصفحة
            match = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', html)
            if match:
                json_data = json.loads(match.group(1))
                scope = json_data.get("__DEFAULT_SCOPE__", {})
                user_info = scope.get("webapp.user-detail", {}).get("userInfo", {})
                
                if user_info:
                    return user_info
                else:
                    return {"error": "لم يتم العثور على بيانات لهذا الحساب."}
            else:
                return {"error": "تم حظر الطلب من قبل تيك توك (CAPTCHA) أو لم يتم العثور على البيانات."}
                
        except Exception as e:
            return {"error": f"خطأ في الاتصال: {str(e)}"}

    try:
        # تشغيل الطلب في مسار منفصل لتجنب تجميد السيرفر
        user_data = await asyncio.wait_for(asyncio.to_thread(fetch_tiktok_data), timeout=20.0)
        
        if "error" in user_data:
            error_msg = user_data["error"]
        else:
            user = user_data.get("user", {})
            stats = user_data.get("stats", {})
            
            live_data = {
                "Username": user.get("uniqueId", "N/A"),
                "Name": user.get("nickname", "N/A"),
                "Region": user.get("region", "N/A"),
                "Private": "Yes ✅" if user.get("privateAccount") else "No ❌",
                "Verified": "Yes ✅" if user.get("verified") else "No ❌",
                "Followers": f"{stats.get('followerCount', 0):,}",
                "Following": f"{stats.get('followingCount', 0):,}",
                "Likes": f"{stats.get('heartCount', 0):,}",
                "Video Count": f"{stats.get('videoCount', 0):,}",
                "Bio": user.get("signature", "(None)"),
                "Link": user.get("bioLink", {}).get("link", "(None)") if user.get("bioLink") else "(None)"
            }
            
    except asyncio.TimeoutError:
        error_msg = "انتهى وقت الانتظار: الخادم لم يستجب في الوقت المحدد."
    except Exception as e:
        error_msg = f"خطأ غير متوقع: {str(e)}"

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
