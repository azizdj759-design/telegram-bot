import ccxt
import pandas as pd
import time
from datetime import datetime, timezone

class DataFetcher:
    def __init__(self, exchange_id="binance"):
        self.exchange = getattr(ccxt, exchange_id)({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

    def fetch_ohlcv(self, symbol="BTC/USDT", timeframe="4h", limit=500):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                raw = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                if not raw or len(raw) < 50:
                    raise ValueError("بيانات غير كافية من المصدر")
                df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df.set_index("timestamp", inplace=True)
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.dropna(inplace=True)
                return df
            except Exception as e:
                if attempt == max_retries - 1:
                    raise ConnectionError(f"فشل جلب البيانات بعد {max_retries} محاولات: {e}")
                time.sleep(2 ** attempt)  # تراجع أسي

    def get_current_price(self, symbol="BTC/USDT"):
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"])
