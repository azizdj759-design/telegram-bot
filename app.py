from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import math
import httpx
import asyncio
import yfinance as yf
import ccxt  # <--- المكتبة الجديدة للكريبتو
from datetime import datetime, timedelta
import time

try:
    from tvDatafeed import TvDatafeed, Interval
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False

app = FastAPI(title="Zero Reversal Engine (Real Data)", version="47.0")

TELEGRAM_TOKEN = "8741070555:AAGf6ys8UH8TZwlQpy_vWff9YONZ9BDmOok"
SUBSCRIBERS = set()
LAST_UPDATE_ID = 0

# ... (نفس دوال التلغرام السابقة، لا حاجة لتغييرها)
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
        
        # إعدادات الكريبتو (OKX)
        self.exchange = ccxt.okx({'enableRateLimit': True})
        
        # إعدادات TradingView
        self.tv_map = {
            "XAUUSD": ("OANDA", "XAUUSD"), "XAGUSD": ("OANDA", "XAGUSD"),
            "WTIUSD": ("TVC", "USOIL"), "EURUSD": ("FX_IDC", "EURUSD"),
            "GBPUSD": ("FX_IDC", "GBPUSD"), "USDJPY": ("FX_IDC", "USDJPY"),
            "AUDUSD": ("FX_IDC", "AUDUSD"), "USDCAD": ("FX_IDC", "USDCAD")
        }

        # الأسعار الأساسية (تم تحديثها لتطابق الواقع)
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
            # إصلاح الشمعة العملاقة: منع التغيرات التي تزيد عن 3 أضعاف التقلب الطبيعي
            change = np.random.normal(0, self.volatility * 0.2)
            change = np.clip(change, -self.volatility * 3, self.volatility * 3) 
            prices.append(prices[-1] + change)
            
        df = pd.DataFrame(index=dates)
        df['Close'] = prices
        df['Open'] = df['Close'].shift(1).fillna(prices[0])
        df['High'] = df[['Open', 'Close']].max(axis=1) + np.random.uniform(0, self.volatility*0.2, length)
        df['Low'] = df[['Open', 'Close']].min(axis=1) - np.random.uniform(0, self.volatility*0.2, length)
        df['Volume'] = np.random.uniform(1000, 5000, length)
        return df

    async def fetch_real_data(self):
        if time.time() - self.last_fetch_time < 60 and self.is_real_data:
            return
        self.last_fetch_time = time.time()
        
        # 1. الكريبتو عبر OKX (مستقر جداً على Render)
        if "USDT" in self.symbol:
            try:
                ccxt_sym = self.symbol.replace("USDT", "/USDT")
                ohlcv = await asyncio.to_thread(self.exchange.fetch_ohlcv, ccxt_sym, timeframe='15m', limit=300)
                if ohlcv:
                    df = pd.DataFrame(ohlcv, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume'])
                    df['time'] = pd.to_datetime(df['time'], unit='ms')
                    df.set_index('time', inplace=True)
                    self.df_15m = df
                    self.current_price = float(self.df_15m.iloc[-1]['Close'])
                    self.is_real_data = True
                    self.data_source_name = f"OKX ({ccxt_sym})"
                    return
            except Exception as e:
                print(f"OKX Error: {e}")

        # 2. الفوركس والذهب عبر TradingView
        if TV_AVAILABLE and self.symbol in self.tv_map:
            exchange, tv_symbol = self.tv_map[self.symbol]
            try:
                def get_tv_data():
                    tv = TvDatafeed()
                    return tv.get_hist(symbol=tv_symbol, exchange=exchange, interval=Interval.in_15_minute, n_bars=300)
                
                hist = await asyncio.to_thread(get_tv_data)
                if hist is not None and not hist.empty:
                    hist = hist.dropna().rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                    # فلترة الشموع الشاذة
                    hist = hist[(hist['High'] - hist['Low']) < self.volatility * 10]
                    self.df_15m = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(300)
                    self.current_price = float(self.df_15m.iloc[-1]['Close'])
                    self.is_real_data = True
                    self.data_source_name = f"TradingView ({tv_symbol})"
                    return
            except Exception as e:
                print(f"TV Error: {e}")

        # 3. المحاكاة
        self.is_real_data = False
        self.data_source_name = "Simulation (Fake)"

    def update_live_tick(self):
        if self.is_real_data: return
        self.tick_count += 1
        change = np.random.normal(0, self.volatility * 0.05)
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
            self.df_15m = pd.concat([self.df_15m, new_row]).tail(300)

    # ... (باقي دوال التحليل والاستراتيجيات _add_indicators, calculate_pnl_and_pips, analyze هي نفسها كما في الكود السابق 46.0، لا تحتاج لتعديل، سأختصرها هنا للتوضيح فقط)
    # يرجى نسخ دالة analyze بالكامل من الكود السابق، فهي لم تتغير.

# ... (باقي الكود من 46.0 مع استبدال analyze هنا)
