from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import asyncio
import json
import websockets
import httpx
from datetime import datetime

app = FastAPI(title="Super Institutional Signal Engine", version="13.0")

class SuperSignalEngine:
    def __init__(self, symbol="BTCUSDT", account_balance=30.0, risk_pct=0.01):
        self.symbol = symbol
        self.balance = account_balance
        self.risk_pct = risk_pct
        self.df = pd.DataFrame()
        
    async def fetch_historical_data(self):
        # 1. المحاولة الرئيسية: Binance Vision مع رأس User-Agent
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={self.symbol}&interval=15m&limit=300"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 418:
                    raise Exception("تم حظر عنوان IP الخاص بالخادم من Binance. جاري تجربة مصدر بيانات بديل...")
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                # 2. الخطة البديلة: استخدام static-klines
                print(f"فشل المصدر الرئيسي: {e}. جاري استخدام المصدر البديل...")
                await self.fetch_fallback_data()
                return

        df = pd.DataFrame(data).iloc[:, :6]
        df.columns = ['time', 'Open', 'High', 'Low', 'Close', 'Volume']
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df.set_index('time', inplace=True)
        self.df = df.astype(float)

    async def fetch_fallback_data(self):
        # مصدر بديل: static-klines (بيانات تاريخية محدثة يومياً)
        # ملاحظة: هذا المصدر قد لا يوفر أحدث 300 شمعة، لكنه يضمن عمل الموقع.
        # يمكن استبداله بمصدر آخر مثل IEX Cloud أو Polygon إذا لزم الأمر.
        try:
            url = f"https://raw.githubusercontent.com/finom/static-klines/main/data/{self.symbol}_15m.json"
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
            
            df = pd.DataFrame(data)
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df.set_index('time', inplace=True)
            self.df = df.astype(float)
        except Exception as e:
            raise Exception(f"فشل جلب البيانات من جميع المصادر: {e}")

    def update_live_data(self, kline):
        new_row = pd.DataFrame([{
            "Open": float(kline['o']), "High": float(kline['h']),
            "Low": float(kline['l']), "Close": float(kline['c']), "Volume": float(kline['v'])
        }], index=[pd.to_datetime(kline['t'], unit='ms')])
        
        if not self.df.empty and self.df.index[-1] == new_row.index[0]:
            self.df.iloc[-1] = new_row.iloc[0]
        else:
            self.df = pd.concat([self.df, new_row])
        if len(self.df) > 500: 
            self.df = self.df.tail(500)

    def analyze_strategies(self):
        if len(self.df) < 200: 
            return None
        
        df = self.df.copy()
        
        df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
        df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()
        
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df["RSI"] = 100 - (100 / (1 + (gain / loss)))
        
        high_low = df["High"] - df["Low"]
        high_close = np.abs(df["High"] - df["Close"].shift())
        low_close = np.abs(df["Low"] - df["Close"].shift())
        df["ATR"] = (pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)).rolling(14).mean()

        df["Swing_High"] = df["High"] == df["High"].rolling(5).max()
        df["Swing_Low"] = df["Low"] == df["Low"].rolling(5).min()
        last_swing_high = df[df["Swing_High"]]["High"].iloc[-1] if not df[df["Swing_High"]].empty else 0
        last_swing_low = df[df["Swing_Low"]]["Low"].iloc[-1] if not df[df["Swing_Low"]].empty else 0

        df["FVG_Bull"] = df["Low"] > df["High"].shift(2)
        df["FVG_Bear"] = df["High"] < df["Low"].shift(2)
        df["OB_Bull"] = (df["Close"].shift(1) < df["Open"].shift(1)) & (df["Close"] > df["High"].shift(1))
        df["OB_Bear"] = (df["Close"].shift(1) > df["Open"].shift(1)) & (df["Close"] < df["Low"].shift(1))

        last_closed = df.iloc[-2]
        live_price = df.iloc[-1]["Close"]
        atr = last_closed["ATR"]

        strategies = {}

        if live_price > last_swing_high:
            strategies["SMC"] = {"name": "SMC (كسر هيكل صاعد)", "status": "اختراق قمة سابقة (BOS صاعد)", "score": 2.0}
        elif live_price < last_swing_low:
            strategies["SMC"] = {"name": "SMC (كسر هيكل هابط)", "status": "اختراق قاع سابق (BOS هابط)", "score": -2.0}
        else:
            strategies["SMC"] = {"name": "SMC", "status": "داخل نطاق السيولة", "score": 0}

        if last_closed["FVG_Bull"] or last_closed["OB_Bull"]:
            strategies["ICT"] = {"name": "ICT (فجوة/بلوك)", "status": "فجوة أو بلوك أوامر شرائي", "score": 1.5}
        elif last_closed["FVG_Bear"] or last_closed["OB_Bear"]:
            strategies["ICT"] = {"name": "ICT (فجوة/بلوك)", "status": "فجوة أو بلوك أوامر بيعي", "score": -1.5}
        else:
            strategies["ICT"] = {"name": "ICT", "status": "لا توجد فجوات نشطة", "score": 0}

        if last_closed["EMA_21"] > last_closed["EMA_200"] and live_price > last_closed["EMA_50"]:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة دافعة صاعدة (3/5)", "score": 1.0}
        elif last_closed["EMA_21"] < last_closed["EMA_200"] and live_price < last_closed["EMA_50"]:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة دافعة هابطة (3/5)", "score": -1.0}
        else:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة تصحيحية", "score": 0}

        if last_closed["RSI"] < 35:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"تشبع بيعي ({last_closed['RSI']:.1f})", "score": 1.0}
        elif last_closed["RSI"] > 65:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"تشبع شرائي ({last_closed['RSI']:.1f})", "score": -1.0}
        else:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"محايد ({last_closed['RSI']:.1f})", "score": 0}

        total_score = sum([s["score"] for s in strategies.values()])

        action = "WAIT"
        if total_score >= 4.0: action = "BUY"
        elif total_score <= -4.0: action = "SELL"

        risk_amount = self.balance * self.risk_pct
        sl_dist = 1.5 * atr
        position_size = 0
        warning_msg = ""
        
        if action != "WAIT" and sl_dist > 0:
            entry = live_price
            sl = entry - sl_dist if action == "BUY" else entry + sl_dist
            tp = entry + (3.0 * atr) if action == "BUY" else entry - (3.0 * atr)
            position_size = risk_amount / sl_dist
            if position_size < 0.0001:
                warning_msg = "⚠️ حجم اللوت صغير جداً! قد يرفضه البروكر."
            entry = round(entry, 2)
            sl = round(sl, 2)
            tp = round(tp, 2)
        else:
            entry, sl, tp = 0, 0, 0

        candles = [{"time": int(idx.timestamp()), "open": float(row["Open"]), "high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"])} for idx, row in df.tail(150).iterrows()]

        return {
            "status": "ok", "symbol": self.symbol, "current_price": round(live_price, 2), "action": action,
            "levels": {"entry": entry, "sl": sl, "tp": tp},
            "position_size": round(position_size, 6), "risk_amount": round(risk_amount, 2),
            "warning": warning_msg, "strategies": list(strategies.values()), "candles": candles
        }

@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    await websocket.accept()
    engine = SuperSignalEngine(symbol=symbol, account_balance=30.0, risk_pct=0.01)
    
    try:
        await engine.fetch_historical_data()
        initial_result = engine.analyze_strategies()
        if initial_result:
            await websocket.send_text(json.dumps(initial_result))
        
        binance_url = f"wss://stream.binance.com:443/ws/{symbol.lower()}@kline_15m"
        async with websockets.connect(binance_url) as binance_ws:
            while True:
                msg = await binance_ws.recv()
                data = json.loads(msg)
                engine.update_live_data(data['k'])
                
                result = engine.analyze_strategies()
                if result:
                    await websocket.send_text(json.dumps(result))
                
    except Exception as e:
        error_msg = json.dumps({"status": "error", "message": f"فشل الاتصال بالبيانات: {str(e)}"})
        try:
            await websocket.send_text(error_msg)
        except:
            pass

# ... (باقي كود الواجهة HTML يبقى كما هو، لا حاجة لتغييره)
