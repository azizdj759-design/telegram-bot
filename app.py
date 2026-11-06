from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import math
import httpx
import asyncio
import yfinance as yf
from datetime import datetime, timedelta
import time

# استيراد مكتبة TradingView
try:
    from tvDatafeed import TvDatafeed, Interval
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False
    print("⚠️ مكتبة tvdatafeed غير مثبتة. سيتم الاعتماد على Yahoo.")

app = FastAPI(title="Zero Reversal Engine (TradingView Data)", version="46.0")

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

@app.get("/test-telegram")
async def test_telegram():
    success = await send_telegram_message("🚀 <b>النظام متصل!</b>\nهذه رسالة تجريبية.")
    return {"status": "success" if success else "error"}

engines = {}

class MarketEngine:
    def __init__(self, symbol):
        self.symbol = symbol
        self.tick_count = 0
        self.active_trade = None 
        self.is_real_data = False
        self.data_source_name = "Simulation"
        self.last_fetch_time = 0
        
        # خريطة الرموز لـ TradingView (المنصة، الرمز)
        self.tv_map = {
            "BTCUSDT": ("BINANCE", "BTCUSDT"),
            "ETHUSDT": ("BINANCE", "ETHUSDT"),
            "XAUUSD": ("OANDA", "XAUUSD"),
            "XAGUSD": ("OANDA", "XAGUSD"),
            "WTIUSD": ("TVC", "USOIL"),
            "EURUSD": ("FX_IDC", "EURUSD"),
            "GBPUSD": ("FX_IDC", "GBPUSD"),
            "USDJPY": ("FX_IDC", "USDJPY"),
            "AUDUSD": ("FX_IDC", "AUDUSD"),
            "USDCAD": ("FX_IDC", "USDCAD")
        }

        # خريطة الرموز لـ Yahoo (كخطة بديلة)
        self.yf_map = {
            "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD",
            "XAUUSD": "GC=F", "XAGUSD": "SI=F", "WTIUSD": "CL=F",
            "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X",
            "AUDUSD": "AUDUSD=X", "USDCAD": "CAD=X"
        }
        
        # إعدادات المحاكاة
        np.random.seed(sum([ord(c) for c in symbol]))
        if symbol == "BTCUSDT": self.base_price, self.volatility, self.decimals = 75000.0, 150.0, 2
        elif symbol == "ETHUSDT": self.base_price, self.volatility, self.decimals = 3500.0, 15.0, 2
        elif symbol == "XAUUSD": self.base_price, self.volatility, self.decimals = 2350.0, 4.0, 2
        elif symbol == "EURUSD": self.base_price, self.volatility, self.decimals = 1.08500, 0.0015, 5
        elif symbol == "GBPUSD": self.base_price, self.volatility, self.decimals = 1.27000, 0.0018, 5
        elif symbol == "USDJPY": self.base_price, self.volatility, self.decimals = 155.000, 0.25, 3
        elif symbol == "AUDUSD": self.base_price, self.volatility, self.decimals = 0.66000, 0.0012, 5
        elif symbol == "USDCAD": self.base_price, self.volatility, self.decimals = 1.37000, 0.0014, 5
        elif symbol == "XAGUSD": self.base_price, self.volatility, self.decimals = 30.0, 0.3, 2
        else: self.base_price, self.volatility, self.decimals = 78.0, 0.8, 2

        self.current_price = self.base_price
        self.df_15m = self._generate_simulated_data(300)

    def _generate_simulated_data(self, length):
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

    async def fetch_real_data(self):
        # تحديث كل 60 ثانية لتجنب حظر المصادر
        if time.time() - self.last_fetch_time < 60 and self.is_real_data:
            return
            
        self.last_fetch_time = time.time()
        
        # --- 1. المحاولة الأولى: TradingView ---
        if TV_AVAILABLE and self.symbol in self.tv_map:
            exchange, tv_symbol = self.tv_map[self.symbol]
            try:
                # جلب البيانات في Thread منفصل لتجنب تجميد السيرفر
                def get_tv_data():
                    tv = TvDatafeed()
                    return tv.get_hist(symbol=tv_symbol, exchange=exchange, interval=Interval.in_15_minute, n_bars=500)
                
                hist = await asyncio.to_thread(get_tv_data)
                
                if hist is not None and not hist.empty:
                    hist = hist.dropna()
                    hist = hist[hist['close'] > 0]
                    hist = hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                    
                    # تصفية الشموع الشاذة (الشمعة العملاقة)
                    hist = hist[hist['High'] - hist['Low'] < self.volatility * 10]
                    
                    self.df_15m = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(500)
                    self.current_price = float(self.df_15m.iloc[-1]['Close'])
                    self.is_real_data = True
                    self.data_source_name = "TradingView (Real)"
                    return
            except Exception as e:
                print(f"TradingView Error ({self.symbol}): {e}")

        # --- 2. المحاولة الثانية: Yahoo Finance ---
        yf_symbol = self.yf_map.get(self.symbol)
        if yf_symbol:
            try:
                def get_yf_data():
                    return yf.Ticker(yf_symbol).history(period="5d", interval="15m")
                
                hist = await asyncio.to_thread(get_yf_data)
                if not hist.empty:
                    hist = hist.dropna()
                    hist = hist[hist['Close'] > 0]
                    # تصفية الشموع الشاذة
                    hist = hist[(hist['High'] - hist['Low']) < self.volatility * 10]
                    
                    self.df_15m = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(500)
                    self.current_price = float(self.df_15m.iloc[-1]['Close'])
                    self.is_real_data = True
                    self.data_source_name = "Yahoo Finance (Real)"
                    return
            except Exception as e:
                print(f"Yahoo Error ({self.symbol}): {e}")

        # --- 3. المحاكاة (إذا فشل الاثنان) ---
        self.is_real_data = False
        self.data_source_name = "Simulation (Fake)"

    def update_live_tick(self):
        # لا نقوم بتحديث السعر يدوياً إذا كنا نستخدم بيانات حقيقية (نتركها كما هي حتى التحديث القادم)
        if self.is_real_data:
            return

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
            self.df_15m = pd.concat([self.df_15m, new_row]).tail(500)

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

    def calculate_pnl_and_pips(self, sl_dist, tp_dist):
        lot_size = 0.01
        if "USD" in self.symbol and "USDT" not in self.symbol: 
            if self.symbol == "XAUUSD": loss_usd = sl_dist * 1.0; profit_usd = tp_dist * 1.0; sl_pips = round(sl_dist * 10); tp_pips = round(tp_dist * 10)
            elif self.symbol == "XAGUSD": loss_usd = sl_dist * 50.0; profit_usd = tp_dist * 50.0; sl_pips = round(sl_dist * 100); tp_pips = round(tp_dist * 100)
            elif self.symbol == "USDJPY": loss_usd = sl_dist * 10.0; profit_usd = tp_dist * 10.0; sl_pips = round(sl_dist / 0.01); tp_pips = round(tp_dist / 0.01)
            else: loss_usd = sl_dist * 1000.0; profit_usd = tp_dist * 1000.0; sl_pips = round(sl_dist / 0.0001); tp_pips = round(tp_dist / 0.0001)
        else:
            sl_pips = "---"; tp_pips = "---"
            loss_usd = sl_dist * lot_size; profit_usd = tp_dist * lot_size
        return sl_pips, tp_pips, round(loss_usd, 2), round(profit_usd, 2)

    def analyze(self):
        if len(self.df_15m) < 200:
            return {"status": "loading", "message": "جاري جمع الشموع..."}

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
        smc_strong = False 
        veto_buy = False
        veto_sell = False

        # 1. SMC
        swing_highs = df_15m[df_15m["Swing_High"]]["High"].tail(3).values
        swing_lows = df_15m[df_15m["Swing_Low"]]["Low"].tail(3).values
        smc_status, smc_score, smc_detail = "لا يوجد كسر هيكل", 0, "السعر يتحرك داخل نطاق عرضي."
        
        if len(swing_highs) > 0 and price > swing_highs[-1]:
            smc_strong = True
            smc_status, smc_score = "كسر هيكل صاعد (BOS)" if htf_trend == "BULLISH" else "تغيير شخصية صاعد (CHoCH)", 2.5
            smc_detail = f"اختراق قمة سابقة عند {swing_highs[-1]:.{self.decimals}f}."
        elif len(swing_lows) > 0 and price < swing_lows[-1]:
            smc_strong = True
            smc_status, smc_score = "كسر هيكل هابط (BOS)" if htf_trend == "BEARISH" else "تغيير شخصية هابط (CHoCH)", -2.5
            smc_detail = f"اختراق قاع سابق عند {swing_lows[-1]:.{self.decimals}f}."

        if len(swing_lows) > 0 and prev["Low"] < swing_lows[-1] and prev["Close"] > swing_lows[-1]:
            smc_strong = True; smc_status, smc_score = "اصطياد سيولة شرائية (Sweep)", 3.0; smc_detail = "السعر كسر قاعاً وهمياً وأغلق فوقه."
        elif len(swing_highs) > 0 and prev["High"] > swing_highs[-1] and prev["Close"] < swing_highs[-1]:
            smc_strong = True; smc_status, smc_score = "اصطياد سيولة بيعية (Sweep)", -3.0; smc_detail = "السعر كسر قمة وهمية وأغلق تحتها."

        strategies["SMC"] = {"name": "SMC", "status": smc_status, "detail": smc_detail, "score": smc_score}
        total_score += smc_score

        # 2. ICT
        fvg_bull = df_15m["Low"] > df_15m["High"].shift(2)
        fvg_bear = df_15m["High"] < df_15m["Low"].shift(2)
        ict_status, ict_score, ict_detail = "لا توجد فجوات", 0, ""
        if fvg_bull.tail(10).any(): ict_status, ict_score, ict_detail = "فجوة صاعدة", 1.5, "فجوة غير مغلقة تدعم الصعود."
        elif fvg_bear.tail(10).any(): ict_status, ict_score, ict_detail = "فجوة هابطة", -1.5, "فجوة غير مغلقة تدعم الهبوط."
        strategies["ICT"] = {"name": "ICT", "status": ict_status, "detail": ict_detail, "score": ict_score}
        total_score += ict_score

        # 3. Divergence
        div_status, div_score, div_detail = "لا يوجد", 0, ""
        recent_df = df_15m.tail(30)
        price_min_idx = recent_df['Low'].idxmin()
        if price_min_idx != recent_df.index[-1]:
            prev_min_idx = recent_df.loc[:price_min_idx].iloc[:-1]['Low'].idxmin()
            if prev_min_idx is not None and not pd.isna(prev_min_idx):
                if recent_df.loc[price_min_idx, 'Low'] < recent_df.loc[prev_min_idx, 'Low'] and recent_df.loc[price_min_idx, 'RSI'] > recent_df.loc[prev_min_idx, 'RSI']:
                    div_status, div_score = "دايفرجنس صاعد", 1.5; div_detail = "السعر قاع أدنى، RSI قاع أعلى."; veto_sell = True
        price_max_idx = recent_df['High'].idxmax()
        if price_max_idx != recent_df.index[-1]:
            prev_max_idx = recent_df.loc[:price_max_idx].iloc[:-1]['High'].idxmax()
            if prev_max_idx is not None and not pd.isna(prev_max_idx):
                if recent_df.loc[price_max_idx, 'High'] > recent_df.loc[prev_max_idx, 'High'] and recent_df.loc[price_max_idx, 'RSI'] < recent_df.loc[prev_max_idx, 'RSI']:
                    div_status, div_score = "دايفرجنس هابط", -1.5; div_detail = "السعر قمة أعلى، RSI قمة أدنى."; veto_buy = True
        strategies["Divergence"] = {"name": "الدايفرجنس", "status": div_status, "detail": div_detail, "score": div_score}
        total_score += div_score

        # 4. Elliott
        elliott_status, elliott_score, elliott_detail = "موجة تصحيحية", 0, ""
        if htf_trend == "BULLISH" and len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
                elliott_status, elliott_score, elliott_detail = "موجة دافعة صاعدة", 1.0, "قمم وقيعان متصاعدة."
        elif htf_trend == "BEARISH" and len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
                elliott_status, elliott_score, elliott_detail = "موجة دافعة هابطة", -1.0, "قمم وقيعان متنازلة."
        strategies["Elliott"] = {"name": "إليوت", "status": elliott_status, "detail": elliott_detail, "score": elliott_score}
        total_score += elliott_score

        # 5. Technical
        tech_status, tech_score, tech_detail = "محايد", 0, f"RSI: {last['RSI']:.1f}"
        if last["RSI"] < 40 and last["MACD"] > last["Signal_Line"]: tech_status, tech_score, tech_detail = "تشبع بيعي", 1.0, "تقاطع MACD إيجابي."
        elif last["RSI"] > 60 and last["MACD"] < last["Signal_Line"]: tech_status, tech_score, tech_detail = "تشبع شرائي", -1.0, "تقاطع MACD سلبي."
        strategies["Technical"] = {"name": "الفني", "status": tech_status, "detail": tech_detail, "score": tech_score}
        total_score += tech_score

        action = "WAIT"
        reason = "لا توجد صفقة. الشروط غير مكتملة."
        
        if self.active_trade is None and smc_strong and self.is_real_data:
            if htf_trend == "BULLISH" and total_score >= 4.0 and not veto_buy:
                action = "BUY"; reason = "توافق صاعد خارق (Zero Reversal)."
            elif htf_trend == "BEARISH" and total_score <= -4.0 and not veto_sell:
                action = "SELL"; reason = "توافق هابط خارق (Zero Reversal)."

        def clean(v): return 0.0 if pd.isna(v) or math.isinf(v) else round(float(v), self.decimals)

        sl_dist = 1.5 * atr
        tp_dist = 6.0 * atr
        sl_pips, tp_pips, loss_usd, profit_usd = self.calculate_pnl_and_pips(sl_dist, tp_dist)

        entry, sl, tp = 0, 0, 0
        if action != "WAIT" and sl_dist > 0:
            entry = clean(price)
            sl = clean(entry - sl_dist if action == "BUY" else entry + sl_dist)
            tp = clean(entry + tp_dist if action == "BUY" else entry - tp_dist)

        if action != "WAIT":
            self.active_trade = {"action": action, "entry": entry, "sl": sl, "tp": tp, "loss_usd": loss_usd, "profit_usd": profit_usd}
            msg = f"🚀 <b>صفقة جديدة: {self.symbol}</b>\n\n"
            msg += f"الاتجاه: {action}\nسعر الدخول: {entry}\n"
            msg += f"<b>وقف الخسارة (SL):</b> {sl}\n<i>(خسارة: {loss_usd}$ | {sl_pips} Pips)</i>\n"
            msg += f"<b>الهدف (TP):</b> {tp}\n<i>(ربح: {profit_usd}$ | {tp_pips} Pips)</i>\n\n"
            msg += f"<b>سبب الدخول:</b>\n{reason}\n• SMC: {smc_status}\n• ICT: {ict_status}\n• الدايفرجنس: {div_status}"
            asyncio.create_task(send_telegram_message(msg))

        if self.active_trade:
            t = self.active_trade
            if t["action"] == "BUY":
                if price >= t["tp"]: asyncio.create_task(send_telegram_message(f"✅ <b>تم تحقيق الهدف ({self.symbol})</b>\nربح: +${t['profit_usd']}")); self.active_trade = None
                elif price <= t["sl"]: asyncio.create_task(send_telegram_message(f"❌ <b>تم ضرب وقف الخسارة ({self.symbol})</b>\nخسارة: -${t['loss_usd']}")); self.active_trade = None
            elif t["action"] == "SELL":
                if price <= t["tp"]: asyncio.create_task(send_telegram_message(f"✅ <b>تم تحقيق الهدف ({self.symbol})</b>\nربح: +${t['profit_usd']}")); self.active_trade = None
                elif price >= t["sl"]: asyncio.create_task(send_telegram_message(f"❌ <b>تم ضرب وقف الخسارة ({self.symbol})</b>\nخسارة: -${t['loss_usd']}")); self.active_trade = None

        # تصفية الشموع لإرسالها للواجهة (نأخذ 300 شمعة فقط لضمان سلاسة الشارت)
        df_clean = df_15m.dropna().copy()
        df_clean = df_clean[df_clean['Close'] > 0]
        candles = [{"time": int(idx.timestamp()), "open": clean(row["Open"]), "high": clean(row["High"]), "low": clean(row["Low"]), "close": clean(row["Close"])} for idx, row in df_clean.tail(300).iterrows()]

        return {
            "status": "ok", "current_price": clean(price), "action": action, "htf_trend": htf_trend, "reason": reason,
            "levels": {"entry": entry, "sl": sl, "tp": tp, "sl_pips": sl_pips, "tp_pips": tp_pips, "loss_usd": loss_usd, "profit_usd": profit_usd},
            "active_trade": self.active_trade, "is_real_data": self.is_real_data,
            "strategies": list(strategies.values()), "candles": candles,
            "source": self.data_source_name
        }

@app.get("/health")
def health_check():
    return {"status": "alive"}

@app.get("/api/data/{symbol}")
async def get_data(symbol: str):
    if symbol not in engines:
        engines[symbol] = MarketEngine(symbol=symbol)
    
    await engines[symbol].fetch_real_data()
    engines[symbol].update_live_tick()
    return engines[symbol].analyze()

@app.get("/", response_class=HTMLResponse)
def home():
    # نفس كود HTML السابق مع تعديلات بسيطة في الشريط العلوي
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Zero Reversal Engine</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: system-ui, sans-serif; background-color: #000; color: #fff; height: 100dvh; overflow: hidden; display: flex; flex-direction: column; }
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
            
            .row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-top: 6px; padding-bottom: 3px; border-bottom: 1px solid #111; }
            .val { font-family: monospace; font-weight: bold; }
            .sub-val { font-size: 10px; display: block; margin-top: 2px;}
            
            .strat-card { background: #0a0a0a; border: 1px solid #222; padding: 8px; border-radius: 4px; margin-bottom: 6px; }
            .strat-title { font-size: 12px; font-weight: bold; color: #eee; margin-bottom: 3px; display: flex; justify-content: space-between; }
            .strat-status { font-size: 11px; margin-bottom: 2px; }
            .strat-detail { font-size: 10px; color: #888; }

            .trend-bull { color: #22c55e; font-weight: bold; }
            .trend-bear { color: #ef4444; font-weight: bold; }
            .real-warning { background: #ef4444; color: white; text-align: center; font-size: 10px; padding: 4px; font-weight: bold; display: none; }
        </style>
    </head>
    <body>
        <div id="real-warning" class="real-warning">⚠️ تحذير: أنت في وضع المحاكاة (البيانات غير حقيقية). لن يتم إرسال إشارات للتلغرام.</div>
        
        <div class="header">
            <div class="brand">ZERO REVERSAL</div>
            <div class="menu">
                <button class="m-btn active" id="btn-BTCUSDT" onclick="switchSymbol('BTCUSDT')">BTC</button>
                <button class="m-btn" id="btn-ETHUSDT" onclick="switchSymbol('ETHUSDT')">ETH</button>
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
                    <div style="font-size:10px; color:#888; margin-bottom:4px;">إشارة التداول (Zero Reversal)</div>
                    <div id="signal-badge" class="badge-wait">جاري التحميل...</div>
                    <div id="reason-text" style="font-size:10px; color:#aaa; margin-top:4px;"></div>
                    <div style="margin-top:8px; font-size:11px; color:#aaa; display:flex; justify-content:space-around;">
                        <div>الاتجاه: <span id="htf-trend">-</span></div>
                    </div>
                </div>
                
                <div class="box">
                    <div style="font-size:10px; color:#888; margin-bottom:4px;">مستويات التنفيذ (لـ 0.01 لوت)</div>
                    <div class="row"><span class="lbl">السعر الحالي</span><span id="p-live" class="val" style="color:#facc15;">0.00</span></div>
                    <div class="row"><span class="lbl">منطقة الدخول</span><span id="p-entry" class="val" style="color:#38bdf8;">0.00</span></div>
                    <div class="row">
                        <span class="lbl">وقف الخسارة (SL)</span>
                        <div style="text-align:left;">
                            <span id="p-sl" class="val" style="color:#ef4444;">0.00</span>
                            <span id="sl-detail" class="sub-val" style="color:#ef4444;"></span>
                        </div>
                    </div>
                    <div class="row">
                        <span class="lbl">الهدف (TP)</span>
                        <div style="text-align:left;">
                            <span id="p-tp" class="val" style="color:#4ade80;">0.00</span>
                            <span id="tp-detail" class="sub-val" style="color:#4ade80;"></span>
                        </div>
                    </div>
                    <div style="font-size:9px; color:#555; text-align:center; margin-top:4px;" id="source-text"></div>
                </div>
                
                <div class="box" style="flex:1;">
                    <div style="font-size:10px; color:#888; margin-bottom:6px;">التفاصيل الدقيقة للاستراتيجيات</div>
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
                        if (data.status === 'loading') {
                            document.getElementById('signal-badge').innerText = data.message;
                            return;
                        }
                        
                        series.setData(data.candles);
                        clearLines();
                        
                        const realWarning = document.getElementById('real-warning');
                        const sourceText = document.getElementById('source-text');
                        
                        if (!data.is_real_data) {
                            realWarning.style.display = 'block';
                            sourceText.innerText = "Source: Simulation (Fake)";
                            sourceText.style.color = "#ef4444";
                        } else {
                            realWarning.style.display = 'none';
                            sourceText.innerText = "Source: " + data.source;
                            sourceText.style.color = "#22c55e";
                        }

                        const badge = document.getElementById('signal-badge');
                        const reasonText = document.getElementById('reason-text');
                        const entryEl = document.getElementById('p-entry');
                        const slEl = document.getElementById('p-sl');
                        const tpEl = document.getElementById('p-tp');
                        const slDetail = document.getElementById('sl-detail');
                        const tpDetail = document.getElementById('tp-detail');

                        if (data.active_trade) {
                            let t = data.active_trade;
                            badge.innerText = (t.action === 'BUY' ? 'BUY' : 'SELL') + ' (ACTIVE)';
                            badge.className = t.action === 'BUY' ? 'badge-buy' : 'badge-sell';
                            reasonText.innerText = "هناك صفقة نشطة حالياً.";
                            entryEl.innerText = t.entry; slEl.innerText = t.sl; tpEl.innerText = t.tp;
                            slDetail.innerText = `(-${data.levels.loss_usd}$ | ${data.levels.sl_pips} Pips)`;
                            tpDetail.innerText = `(+${data.levels.profit_usd}$ | ${data.levels.tp_pips} Pips)`;
                            activeLines.push(series.createPriceLine({ price: t.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' }));
                            activeLines.push(series.createPriceLine({ price: t.sl, color: '#ef4444', lineWidth: 2, title: 'SL' }));
                            activeLines.push(series.createPriceLine({ price: t.tp, color: '#22c55e', lineWidth: 2, title: 'TP' }));
                        } 
                        else {
                            badge.innerText = data.action === 'BUY' ? 'STRONG BUY' : data.action === 'SELL' ? 'STRONG SELL' : 'WAIT';
                            badge.className = data.action === 'BUY' ? 'badge-buy' : data.action === 'SELL' ? 'badge-sell' : 'badge-wait';
                            reasonText.innerText = data.reason;
                            entryEl.innerText = data.levels.entry; slEl.innerText = data.levels.sl; tpEl.innerText = data.levels.tp;
                            if (data.action !== 'WAIT') {
                                slDetail.innerText = `(-${data.levels.loss_usd}$ | ${data.levels.sl_pips} Pips)`;
                                tpDetail.innerText = `(+${data.levels.profit_usd}$ | ${data.levels.tp_pips} Pips)`;
                                activeLines.push(series.createPriceLine({ price: data.levels.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' }));
                                activeLines.push(series.createPriceLine({ price: data.levels.sl, color: '#ef4444', lineWidth: 2, title: 'SL' }));
                                activeLines.push(series.createPriceLine({ price: data.levels.tp, color: '#22c55e', lineWidth: 2, title: 'TP' }));
                            } else {
                                slDetail.innerText = ""; tpDetail.innerText = "";
                            }
                        }

                        const trendEl = document.getElementById('htf-trend');
                        trendEl.innerText = data.htf_trend === 'BULLISH' ? 'صاعد (1H)' : 'هابط (1H)';
                        trendEl.className = data.htf_trend === 'BULLISH' ? 'trend-bull' : 'trend-bear';

                        document.getElementById('p-live').innerText = data.current_price;
                        
                        let stratHtml = '';
                        data.strategies.forEach(s => {
                            let color = s.score > 0 ? '#4ade80' : (s.score < 0 ? '#f87171' : '#888');
                            stratHtml += `
                            <div class="strat-card">
                                <div class="strat-title"><span>${s.name}</span><span style="color:${color}">${s.score > 0 ? '+' : ''}${s.score}</span></div>
                                <div class="strat-status" style="color:${color}"><strong>${s.status}</strong></div>
                                <div class="strat-detail">${s.detail}</div>
                            </div>`;
                        });
                        document.getElementById('strategies-container').innerHTML = stratHtml;
                    })
                    .catch(err => console.error(err));
            }

            function switchSymbol(symbol) {
                currentSymbol = symbol;
                document.querySelectorAll('.m-btn').forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + symbol).classList.add('active');
                series.setData([]);
                clearLines();
                document.getElementById('signal-badge').innerText = "جاري التحميل...";
                document.getElementById('strategies-container').innerHTML = "";
                if (intervalId) clearInterval(intervalId);
                setTimeout(() => {
                    fetchData();
                    chart.timeScale().fitContent();
                    intervalId = setInterval(fetchData, 5000); 
                }, 500);
            }

            window.onload = () => { initChart(); switchSymbol('BTCUSDT'); };
        </script>
    </body>
    </html>
    """
