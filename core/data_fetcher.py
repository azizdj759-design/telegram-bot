import ccxt
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
import time

class DataFetcher:
    def __init__(self):
        # قائمة البورصات البديلة: OKX و Kraken لا تحظر خوادم Render عادة
        self.exchanges = [
            ccxt.okx({"enableRateLimit": True}),
            ccxt.kraken({"enableRateLimit": True}),
            ccxt.binance({"enableRateLimit": True})
        ]

    def fetch_ohlcv(self, symbol="BTC/USDT", timeframe="4h", limit=500):
        # إذا كان الرمز خاصاً بالفوركس أو الذهب، استخدم yfinance
        if "XAU" in symbol or "GC=F" in symbol or "=X" in symbol:
            return self._fetch_yfinance(symbol, timeframe, limit)
        
        # للكريبتو: جرب البورصات بالترتيب
        for exchange in self.exchanges:
            try:
                raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                if not raw or len(raw) < 50:
                    continue
                df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df.set_index("timestamp", inplace=True)
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.dropna(inplace=True)
                return df
            except Exception as e:
                print(f"فشل {exchange.id}: {e}")
                continue
        
        raise ConnectionError("فشلت جميع البورصات في جلب البيانات. يرجى المحاولة لاحقاً.")

    def _fetch_yfinance(self, symbol, timeframe, limit):
        # تحويل الإطار الزمني إلى صيغة yfinance
        interval_map = {"1h": "1h", "4h": "1h", "1d": "1d"} # 4h غير مدعوم مباشرة، نستخدم 1h كبديل
        yf_symbol = "GC=F" if "XAU" in symbol else "XAUUSD=X"
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="60d", interval=interval_map.get(timeframe, "1h"))
        if df.empty:
            raise ValueError(f"لا توجد بيانات متاحة لـ {symbol}")
        df.index = df.index.tz_localize('UTC') if df.index.tz is None else df.index
        return df[["Open", "High", "Low", "Close", "Volume"]].rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )

    def get_current_price(self, symbol="BTC/USDT"):
        if "XAU" in symbol or "GC=F" in symbol:
            return self._fetch_yfinance(symbol, "1h", 1)["close"].iloc[-1]
        for exchange in self.exchanges:
            try:
                ticker = exchange.fetch_ticker(symbol)
                return float(ticker["last"])
            except:
                continue
        raise ConnectionError("فشل جلب السعر الحالي")
