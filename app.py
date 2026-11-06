from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import math
import httpx
import asyncio
from datetime import datetime, timedelta

app = FastAPI(title="Ultimate Pro Signal Engine", version="35.0")

TELEGRAM_TOKEN = "8741070555:AAGf6ys8UH8TZwlQpy_vWff9YONZ9BDmOok"

SUBSCRIBERS = set()
LAST_UPDATE_ID = 0

async def sync_subscribers():
    global LAST_UPDATE_ID
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={LAST_UPDATE_ID + 1}"
        async with httpx.AsyncClient() as client:
            res = await client.get(url)
            data = res.json()
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    LAST_UPDATE_ID = update["update_id"]
                    if "message" in update and "chat" in update["message"]:
                        SUBSCRIBERS.add(update["message"]["chat"]["id"])
    except Exception:
        pass

async def send_telegram_message(message: str):
    await sync_subscribers() 
    if not SUBSCRIBERS: return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        for chat_id in list(SUBSCRIBERS):
            try:
                await client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
            except:
                pass
    return True

@app.get("/subscribers")
async def get_subscribers():
    await sync_subscribers()
    return {"subscribers_count": len(SUBSCRIBERS)}

engines = {}

class MarketSimulator:
    def __init__(self, symbol, balance=30.0, risk_usd=5.0):
        self.symbol = symbol
        self.risk_usd = risk_usd
        self.tick_count = 0
        self.active_trade = None
        self.last_action = "WAIT"
        
        # إعدادات الأصول الجديدة (محاكاة دقيقة لأسعار Exness)
        if symbol == "BTCUSDT": self.base_price, self.volatility, self.decimals = 65000.0, 150.0, 2
        elif symbol == "ETHUSDT": self.base_price, self.volatility, self.decimals = 3500.0, 15.0, 2
        elif symbol == "SOLUSDT": self.base_price, self.volatility, self.decimals = 150.0, 2.5, 2
        elif symbol == "BNBUSDT": self.base_price, self.volatility, self.decimals = 600.0, 10.0, 2
        elif symbol == "XRPUSDT": self.base_price, self.volatility, self.decimals = 0.5500, 0.015, 4
        elif symbol == "XAUUSD": self.base_price, self.volatility, self.decimals = 2350.0, 4.0, 2
        elif symbol == "XAGUSD": self.base_price, self.volatility, self.decimals = 30.0, 0.3, 2
        elif symbol == "EURUSD": self.base_price, self.volatility, self.decimals = 1.08500, 0.0015, 5
        elif symbol == "GBPUSD": self.base_price, self.volatility, self.decimals = 1.27000, 0.0018, 5
        elif symbol == "USDJPY": self.base_price, self.volatility, self.decimals = 155.000, 0.25, 3
        elif symbol == "AUDUSD": self.base_price, self.volatility, self.decimals = 0.66000, 0.0012, 5
        elif symbol == "USDCAD": self.base_price, self.volatility, self.decimals = 1.37000, 0.0014, 5
        else: self.base_price, self.volatility, self.decimals = 78.0, 0.8, 2 # WTI

        self.current_price = self.base_price
        self.df_15m = self._generate_historical_data(5200)

    def _generate_historical_data(self, length):
        dates = [datetime.now() - timedelta(minutes=15*i) for i in range(length)]
        dates.reverse()
        prices = [self.base_price]
        for _ in range(length - 1):
            change = np.random.normal(0, self.volatility)
            prices.append(prices[-1] + change)
            
        df = pd.DataFrame(index=dates)
        df['Close'] = prices
        df['Open'] = df['Close'].shift(1).fillna(prices[0])
        df['High'] = df[['Open', 'Close']].max(axis=1) + np.random.uniform(0, self.volatility*0.5, length)
        df['Low'] = df[['Open', 'Close']].min(axis=1) - np.random.uniform(0, self.volatility*0.5, length)
        df['Volume'] = np.random.uniform(1000, 5000, length)
        return df

    def update_live_tick(self):
        self.tick_count += 1
        change = np.random.normal(0, self.volatility * 0.2)
        self.current_price += change
        
        self.df_15m.iloc[-1, self.df_15m.columns.get_loc('Close')] = self.current_price
        self.df_15m.iloc[-1, self.df_15m.columns.get_loc('High')] = max(self.df_15m.iloc[-1]['High'], self.current_price)
        self.df_15m.iloc[-1, self.df_15m.columns.get_loc('Low')] = min(self.df_15m.iloc[-1]['Low'], self.current_price)
        
        if self.tick_count >= 10:
            self.tick_count = 0
            new_time = self.df_15m.index[-1] + timedelta(minutes=15)
            new_row = pd.DataFrame({
                'Open': [self.current_price], 'High': [self.current_price],
                'Low': [self.current_price], 'Close': [self.current_price],
                'Volume': [np.random.uniform(1000, 5000)]
            }, index=[new_time])
            self.df_15m = pd.concat([self.df_15m, new_row]).tail(5200)

    def _add_indicators(self, df):
        df = df.copy()
        df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
        df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()
        
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df["RSI"] = 100 - (100 / (1 + (gain / loss)))
        
        exp1 = df["Close"].ewm(span=12, adjust=False).mean()
        exp2 = df["Close"].ewm(span=26, adjust=False).mean()
        df["MACD"] = exp1 - exp2
        df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()

        high_low = df["High"] - df["Low"]
        high_close = np.abs(df["High"] - df["Close"].shift())
        low_close = np.abs(df["Low"] - df["Close"].shift())
        df["ATR"] = (pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)).rolling(14).mean()
        
        df["Swing_High"] = df["High"] == df["High"].rolling(7, center=True).max()
        df["Swing_Low"] = df["Low"] == df["Low"].rolling(7, center=True).min()
        return df

    def analyze(self):
        df_15m = self._add_indicators(self.df_15m)
        df_1h = self.df_15m.resample('1h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        df_1h = self._add_indicators(df_1h)

        htf_last = df_1h.iloc[-2]
        htf_trend = "BULLISH" if htf_last["EMA_50"] > htf_last["EMA_200"] else "BEARISH"

        last = df_15m.iloc[-2]
        prev = df_15m.iloc[-3]
        price = df_15m.iloc[-1]["Close"]
        atr = last["ATR"] if not pd.isna(last["ATR"]) else self.volatility

        strategies = {}
        total_score = 0

        # 1. SMC (BOS, CHoCH, Sweeps)
        swing_highs = df_15m[df_15m["Swing_High"]]["High"].tail(3).values
        swing_lows = df_15m[df_15m["Swing_Low"]]["Low"].tail(3).values
        
        smc_status, smc_score, smc_detail = "لا يوجد كسر هيكل", 0, "السعر يتحرك داخل نطاق عرضي."
        if len(swing_highs) > 0 and price > swing_highs[-1]:
            if htf_trend == "BEARISH":
                smc_status, smc_score = "تغيير شخصية صاعد (CHoCH)", 2.5
                smc_detail = f"اختراق قمة هابطة سابقة عند {swing_highs[-1]:.{self.decimals}f}."
            else:
                smc_status, smc_score = "كسر هيكل صاعد (BOS)", 2.0
                smc_detail = f"تم اختراق القمة السابقة عند {swing_highs[-1]:.{self.decimals}f}."
        elif len(swing_lows) > 0 and price < swing_lows[-1]:
            if htf_trend == "BULLISH":
                smc_status, smc_score = "تغيير شخصية هابط (CHoCH)", -2.5
                smc_detail = f"اختراق قاع صاعد سابق عند {swing_lows[-1]:.{self.decimals}f}."
            else:
                smc_status, smc_score = "كسر هيكل هابط (BOS)", -2.0
                smc_detail = f"تم اختراق القاع السابق عند {swing_lows[-1]:.{self.decimals}f}."

        if len(swing_lows) > 0 and prev["Low"] < swing_lows[-1] and prev["Close"] > swing_lows[-1]:
            smc_status, smc_score = "اصطياد سيولة شرائية (Sweep)", 3.0
            smc_detail = "السعر كسر قاعاً وهمياً وأغلق فوقه (انعكاس قوي)."
        elif len(swing_highs) > 0 and prev["High"] > swing_highs[-1] and prev["Close"] < swing_highs[-1]:
            smc_status, smc_score = "اصطياد سيولة بيعية (Sweep)", -3.0
            smc_detail = "السعر كسر قمة وهمية وأغلق تحتها (انعكاس قوي)."

        strategies["SMC"] = {"name": "SMC (الهيكل والسيولة)", "status": smc_status, "detail": smc_detail, "score": smc_score}
        total_score += smc_score

        # 2. ICT (FVG)
        fvg_bull = df_15m["Low"] > df_15m["High"].shift(2)
        fvg_bear = df_15m["High"] < df_15m["Low"].shift(2)
        
        ict_status, ict_score, ict_detail = "لا توجد فجوات سعرية", 0, "لم يتم اكتشاف فجوات قريبة."
        if fvg_bull.tail(10).any():
            ict_status, ict_score = "فجوة صاعدة (Bullish FVG)", 1.5
            ict_detail = "يوجد فجوة سعرية غير مغلقة تدعم الصعود."
        elif fvg_bear.tail(10).any():
            ict_status, ict_score = "فجوة هابطة (Bearish FVG)", -1.5
            ict_detail = "يوجد فجوة سعرية غير مغلقة تدعم الهبوط."
            
        strategies["ICT"] = {"name": "ICT (الفجوات السعرية)", "status": ict_status, "detail": ict_detail, "score": ict_score}
        total_score += ict_score

        # 3. RSI Divergence
        div_status, div_score, div_detail = "لا يوجد دايفرجنس", 0, "لا يوجد تباعد بين السعر والمؤشر."
        recent_df = df_15m.tail(30)
        price_min_idx = recent_df['Low'].idxmin()
        if price_min_idx != recent_df.index[-1]:
            prev_price_min_idx = recent_df.loc[:price_min_idx].iloc[:-1]['Low'].idxmin()
            if prev_price_min_idx is not None and not pd.isna(prev_price_min_idx):
                if recent_df.loc[price_min_idx, 'Low'] < recent_df.loc[prev_price_min_idx, 'Low'] and \
                   recent_df.loc[price_min_idx, 'RSI'] > recent_df.loc[prev_price_min_idx, 'RSI']:
                    div_status, div_score = "دايفرجنس صاعد (Bullish Div)", 1.5
                    div_detail = "السعر كوّن قاعاً أدنى ومؤشر RSI كوّن قاعاً أعلى."

        price_max_idx = recent_df['High'].idxmax()
        if price_max_idx != recent_df.index[-1]:
            prev_price_max_idx = recent_df.loc[:price_max_idx].iloc[:-1]['High'].idxmax()
            if prev_price_max_idx is not None and not pd.isna(prev_price_max_idx):
                if recent_df.loc[price_max_idx, 'High'] > recent_df.loc[prev_price_max_idx, 'High'] and \
                   recent_df.loc[price_max_idx, 'RSI'] < recent_df.loc[prev_price_max_idx, 'RSI']:
                    div_status, div_score = "دايفرجنس هابط (Bearish Div)", -1.5
                    div_detail = "السعر كوّن قمة أعلى ومؤشر RSI كوّن قمة أدنى."

        strategies["Divergence"] = {"name": "الدايفرجنس (Divergence)", "status": div_status, "detail": div_detail, "score": div_score}
        total_score += div_score

        # 4. Elliott
        elliott_status, elliott_score, elliott_detail = "موجة تصحيحية معقدة", 0, "السوق غير واضح هيكلياً."
        if htf_trend == "BULLISH" and len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
                elliott_status, elliott_score = "موجة دافعة صاعدة (3 أو 5)", 1.0
                elliott_detail = "قمم وقيعان متصاعدة تؤكد الموجة الصاعدة."
        elif htf_trend == "BEARISH" and len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
                elliott_status, elliott_score = "موجة دافعة هابطة (3 أو 5)", -1.0
                elliott_detail = "قمم وقيعان متنازلة تؤكد الموجة الهابطة."
                
        strategies["Elliott"] = {"name": "إليوت (الموجات)", "status": elliott_status, "detail": elliott_detail, "score": elliott_score}
        total_score += elliott_score

        # 5. Technical
        tech_status, tech_score, tech_detail = "محايد", 0, f"RSI: {last['RSI']:.1f}"
        if last["RSI"] < 40 and last["MACD"] > last["Signal_Line"]:
            tech_status, tech_score = "تشبع بيعي + تقاطع MACD", 1.0
            tech_detail = f"RSI عند {last['RSI']:.1f} مع تقاطع إيجابي."
        elif last["RSI"] > 60 and last["MACD"] < last["Signal_Line"]:
            tech_status, tech_score = "تشبع شرائي + تقاطع MACD", -1.0
            tech_detail = f"RSI عند {last['RSI']:.1f} مع تقاطع سلبي."
            
        strategies["Technical"] = {"name": "الفني (الزخم)", "status": tech_status, "detail": tech_detail, "score": tech_score}
        total_score += tech_score

        action = "WAIT"
        reason = "الشروط غير مكتملة. النظام يحمي رأس مالك."
        
        if htf_trend == "BULLISH" and total_score >= 3.5:
            action = "BUY"
            reason = "توافق صاعد: الاتجاه العام والاستراتيجيات تدعم الشراء."
        elif htf_trend == "BEARISH" and total_score <= -3.5:
            action = "SELL"
            reason = "توافق هابط: الاتجاه العام والاستراتيجيات تدعم البيع."

        def clean(v): return 0.0 if pd.isna(v) or math.isinf(v) else round(float(v), self.decimals)

        sl_dist = 1.5 * atr
        position_size, entry, sl, tp, warning_msg = 0, 0, 0, 0, ""
        
        if action != "WAIT" and sl_dist > 0:
            entry = clean(price)
            sl = clean(entry - sl_dist if action == "BUY" else entry + sl_dist)
            tp = clean(entry + (3.0 * atr) if action == "BUY" else entry - (3.0 * atr))
            position_size = round(self.risk_usd / sl_dist, 4)
            if position_size < 0.0001:
                warning_msg = "⚠️ حجم اللوت صغير جداً!"

        if action != "WAIT" and action != self.last_action:
            self.active_trade = {"action": action, "entry": entry, "sl": sl, "tp": tp}
            msg = f"🚀 <b>إشارة مؤسسية: {self.symbol}</b>\n\n"
            msg += f"الاتجاه: {action}\n"
            msg += f"سعر الدخول: {entry}\n"
            msg += f"وقف الخسارة (SL): {sl}\n"
            msg += f"الهدف (TP): {tp}\n"
            msg += f"حجم المركز: {position_size}\n"
            msg += f"الخسارة القصوى: $5.00\n\n"
            msg += f"<b>سبب الدخول:</b>\n{reason}\n"
            msg += f"• SMC: {smc_status}\n"
            msg += f"• ICT: {ict_status}\n"
            msg += f"• الدايفرجنس: {div_status}"
            asyncio.create_task(send_telegram_message(msg))

        self.last_action = action

        if self.active_trade:
            t = self.active_trade
            if t["action"] == "BUY":
                if price >= t["tp"]:
                    asyncio.create_task(send_telegram_message(f"✅ <b>تم تحقيق الهدف ({self.symbol})</b>\nربح: +$15.00"))
                    self.active_trade = None
                elif price <= t["sl"]:
                    asyncio.create_task(send_telegram_message(f"❌ <b>تم ضرب وقف الخسارة ({self.symbol})</b>\nخسارة: -$5.00"))
                    self.active_trade = None
            elif t["action"] == "SELL":
                if price <= t["tp"]:
                    asyncio.create_task(send_telegram_message(f"✅ <b>تم تحقيق الهدف ({self.symbol})</b>\nربح: +$15.00"))
                    self.active_trade = None
                elif price >= t["sl"]:
                    asyncio.create_task(send_telegram_message(f"❌ <b>تم ضرب وقف الخسارة ({self.symbol})</b>\nخسارة: -$5.00"))
                    self.active_trade = None

        candles = [{"time": int(idx.timestamp()), "open": clean(row["Open"]), "high": clean(row["High"]), "low": clean(row["Low"]), "close": clean(row["Close"])} for idx, row in df_15m.tail(5000).iterrows()]

        return {
            "status": "ok", "current_price": clean(price), "action": action, "htf_trend": htf_trend, "reason": reason,
            "levels": {"entry": entry, "sl": sl, "tp": tp},
            "position_size": position_size, "warning": warning_msg, 
            "strategies": list(strategies.values()), "candles": candles,
            "source": "MTF Deep Simulator (Exness)"
        }

@app.get("/health")
def health_check():
    return {"status": "alive"}

@app.get("/api/data/{symbol}")
async def get_data(symbol: str):
    if symbol not in engines:
        engines[symbol] = MarketSimulator(symbol=symbol)
    
    engines[symbol].update_live_tick()
    return engines[symbol].analyze()

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Ultimate Pro Signal Engine</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: system-ui, sans-serif; background-color: #000; color: #fff; height: 100dvh; overflow: hidden; display: flex; flex-direction: column; }
            /* شريط علوي قابل للتمرير بسلاسة */
            .header { height: 50px; flex-shrink: 0; background: #050505; border-bottom: 1px solid #141414; display: flex; align-items: center; padding: 0 10px; overflow-x: auto; white-space: nowrap; scrollbar-width: none; }
            .header::-webkit-scrollbar { display: none; }
            .header .brand { font-size: 13px; font-weight: bold; margin-left: 10px; color: #38bdf8; }
            .header .menu { display: flex; gap: 6px; }
            .m-btn { background: #222; color: #fff; border: 1px solid #444; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; }
            .m-btn.active { background: #444; font-weight: bold; border-color: #888; }
            
            .layout { display: flex; flex: 1; overflow: hidden; flex-direction: column; }
            
            .chart-wrap { flex: 7.5; background: #000; position: relative; width: 100%; border-bottom: 1px solid #222; }
            #chart { width: 100%; height: 100%; }
            
            .panel { flex: 2.5; width: 100%; background: #030303; padding: 10px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
            
            .box { background: #080808; border: 1px solid #161616; padding: 10px; border-radius: 5px; }
            .badge-buy { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid #22c55e; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 15px; }
            .badge-sell { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid #ef4444; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 15px; }
            .badge-wait { background: rgba(234, 179, 8, 0.1); color: #eab308; border: 1px solid #eab308; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 15px; }
            .row { display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px; padding-bottom: 3px; border-bottom: 1px solid #111; }
            .val { font-family: monospace; font-weight: bold; }
            
            .strat-card { background: #0a0a0a; border: 1px solid #222; padding: 8px; border-radius: 4px; margin-bottom: 6px; }
            .strat-title { font-size: 12px; font-weight: bold; color: #eee; margin-bottom: 3px; display: flex; justify-content: space-between; }
            .strat-status { font-size: 11px; margin-bottom: 2px; }
            .strat-detail { font-size: 10px; color: #888; }

            .trend-bull { color: #22c55e; font-weight: bold; }
            .trend-bear { color: #ef4444; font-weight: bold; }
            .warning-box { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; padding: 6px; border-radius: 4px; font-size: 10px; text-align: center; display: none; margin-top: 4px; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="brand">PRO MTF</div>
            <div class="menu">
                <button class="m-btn active" id="btn-BTCUSDT" onclick="switchSymbol('BTCUSDT')">BTC</button>
                <button class="m-btn" id="btn-ETHUSDT" onclick="switchSymbol('ETHUSDT')">ETH</button>
                <button class="m-btn" id="btn-SOLUSDT" onclick="switchSymbol('SOLUSDT')">SOL</button>
                <button class="m-btn" id="btn-BNBUSDT" onclick="switchSymbol('BNBUSDT')">BNB</button>
                <button class="m-btn" id="btn-XRPUSDT" onclick="switchSymbol('XRPUSDT')">XRP</button>
                <button class="m-btn" id="btn-XAUUSD" onclick="switchSymbol('XAUUSD')">GOLD</button>
                <button class="m-btn" id="btn-XAGUSD" onclick="switchSymbol('XAGUSD')">SILVER</button>
                <button class="m-btn" id="btn-WTIUSD" onclick="switchSymbol('WTIUSD')">OIL</button>
                <button class="m-btn" id="btn-EURUSD" onclick="switchSymbol('EURUSD')">EUR/USD</button>
                <button class="m-btn" id="btn-GBPUSD" onclick="switchSymbol('GBPUSD')">GBP/USD</button>
                <button class="m-btn" id="btn-USDJPY" onclick="switchSymbol('USDJPY')">USD/JPY</button>
                <button class="m-btn" id="btn-AUDUSD" onclick="switchSymbol('AUDUSD')">AUD/USD</button>
                <button class="m-btn" id="btn-USDCAD" onclick="switchSymbol('USDCAD')">USD/CAD</button>
            </div>
        </div>
        
        <div class="layout">
            <div class="chart-wrap"><div id="chart"></div></div>
            
            <div class="panel">
                <div class="box" style="text-align:center;">
                    <div style="font-size:10px; color:#888; margin-bottom:4px;">إشارة التداول (تحليل متعدد الأطر)</div>
                    <div id="signal-badge" class="badge-wait">جاري التحميل...</div>
                    <div id="reason-text" style="font-size:10px; color:#aaa; margin-top:4px;"></div>
                    
                    <div style="margin-top:8px; font-size:11px; color:#aaa; display:flex; justify-content:space-around;">
                        <div>الاتجاه: <span id="htf-trend">-</span></div>
                        <div>حجم المركز: <strong id="pos-size" style="color:#38bdf8;">0.00</strong></div>
                    </div>
                    <div id="warn-box" class="warning-box"></div>
                </div>
                
                <div class="box">
                    <div style="font-size:10px; color:#888; margin-bottom:4px;">مستويات التنفيذ (Exness)</div>
                    <div class="row"><span class="lbl">السعر الحالي</span><span id="p-live" class="val" style="color:#facc15;">0.00</span></div>
                    <div class="row"><span class="lbl">منطقة الدخول</span><span id="p-entry" class="val" style="color:#38bdf8;">0.00</span></div>
                    <div class="row"><span class="lbl">وقف الخسارة (5$)</span><span id="p-sl" class="val" style="color:#ef4444;">0.00</span></div>
                    <div class="row"><span class="lbl">الهدف (15$)</span><span id="p-tp" class="val" style="color:#4ade80;">0.00</span></div>
                </div>
                
                <div class="box" style="flex:1;">
                    <div style="font-size:10px; color:#888; margin-bottom:6px;">التفاصيل الدقيقة للاستراتيجيات (Confluence)</div>
                    <div id="strategies-container"></div>
                </div>
            </div>
        </div>
        
        <script>
            let chart, series, activeLines = [];
            let currentSymbol = 'BTCUSDT';
            let intervalId = null;

            function initChart() {
                chart = LightweightCharts.createChart(document.getElementById('chart'), {
                    layout: { background: { color: '#000' }, textColor: '#666' },
                    grid: { vertLines: { color: '#0a0a0a' }, horzLines: { color: '#0a0a0a' } },
                    timeScale: { timeVisible: true }
                });
                series = chart.addCandlestickSeries({ upColor: '#22c55e', downColor: '#ef4444', borderVisible: false });
                window.addEventListener('resize', () => chart.applyOptions({ width: document.getElementById('chart').clientWidth, height: document.getElementById('chart').clientHeight }));
            }

            function clearLines() { activeLines.forEach(l => series.removePriceLine(l)); activeLines = []; }

            function fetchData() {
                fetch('/api/data/' + currentSymbol)
                    .then(res => res.json())
                    .then(data => {
                        series.setData(data.candles);
                        clearLines();
                        
                        const badge = document.getElementById('signal-badge');
                        badge.innerText = data.action === 'BUY' ? 'STRONG BUY' : data.action === 'SELL' ? 'STRONG SELL' : 'WAIT';
                        badge.className = data.action === 'BUY' ? 'badge-buy' : data.action === 'SELL' ? 'badge-sell' : 'badge-wait';
                        
                        document.getElementById('reason-text').innerText = data.reason;

                        const trendEl = document.getElementById('htf-trend');
                        trendEl.innerText = data.htf_trend === 'BULLISH' ? 'صاعد (1H)' : 'هابط (1H)';
                        trendEl.className = data.htf_trend === 'BULLISH' ? 'trend-bull' : 'trend-bear';

                        document.getElementById('pos-size').innerText = data.position_size;
                        document.getElementById('p-live').innerText = data.current_price;
                        document.getElementById('p-entry').innerText = data.levels.entry;
                        document.getElementById('p-sl').innerText = data.levels.sl;
                        document.getElementById('p-tp').innerText = data.levels.tp;
                        
                        const warnBox = document.getElementById('warn-box');
                        warnBox.style.display = data.warning ? 'block' : 'none';
                        if (data.warning) warnBox.innerText = data.warning;
                        
                        let stratHtml = '';
                        data.strategies.forEach(s => {
                            let color = s.score > 0 ? '#4ade80' : (s.score < 0 ? '#f87171' : '#888');
                            stratHtml += `
                            <div class="strat-card">
                                <div class="strat-title">
                                    <span>${s.name}</span>
                                    <span style="color:${color}">${s.score > 0 ? '+' : ''}${s.score}</span>
                                </div>
                                <div class="strat-status" style="color:${color}"><strong>${s.status}</strong></div>
                                <div class="strat-detail">${s.detail}</div>
                            </div>`;
                        });
                        document.getElementById('strategies-container').innerHTML = stratHtml;
                        
                        if (data.action !== 'WAIT') {
                            activeLines.push(series.createPriceLine({ price: data.levels.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' }));
                            activeLines.push(series.createPriceLine({ price: data.levels.sl, color: '#ef4444', lineWidth: 2, title: 'SL' }));
                            activeLines.push(series.createPriceLine({ price: data.levels.tp, color: '#22c55e', lineWidth: 2, title: 'TP' }));
                        }
                    })
                    .catch(err => console.error(err));
            }

            function switchSymbol(symbol) {
                currentSymbol = symbol;
                document.querySelectorAll('.m-btn').forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + symbol).classList.add('active');
                document.getElementById('signal-badge').innerText = "جاري التحليل...";
                
                if (intervalId) clearInterval(intervalId);
                fetchData();
                
                setTimeout(() => chart.timeScale().fitContent(), 200);
                
                intervalId = setInterval(fetchData, 2000); 
            }

            window.onload = () => { initChart(); switchSymbol('BTCUSDT'); };
        </script>
    </body>
    </html>
    """
