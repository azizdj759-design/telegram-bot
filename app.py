import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="Advanced Gold & Market Analyzer API",
    version="1.0",
    description=(
        "تحليل أسواق الذهب عبر استراتيجيات SMC, ICT, موجات أليوت، والتحليل"
        " الكلاسيكي"
    ),
)


class AdvancedGoldAnalyzer:

  def __init__(self, symbol="GC=F", period="60d", interval="1h"):
    self.symbol = symbol
    self.period = period
    self.interval = interval
    self.df = None

  def fetch_data(self):
    ticker = yf.Ticker(self.symbol)
    self.df = ticker.history(period=self.period, interval=self.interval)
    if self.df.empty:
      raise HTTPException(
          status_code=500, detail="لم يتم استرجاع أي بيانات من السوق."
      )
    self.df = self.df[["Open", "High", "Low", "Close", "Volume"]].dropna()

  def apply_technical_analysis(self):
    df = self.df
    df["EMA_50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA_200"] = df["Close"].ewm(span=200, adjust=False).mean()

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(
        axis=1
    )
    df["ATR"] = true_range.rolling(window=14).mean()

  def detect_smc_ict_elements(self):
    df = self.df
    df["FVG_Bullish"] = (df["Low"].shift(-1) > df["High"].shift(1)) & (
        df["Close"] > df["Open"]
    )
    df["FVG_Bearish"] = (df["High"].shift(-1) < df["Low"].shift(1)) & (
        df["Close"] < df["Open"]
    )

    df["Order_Block_Buy"] = (df["Close"].shift(1) < df["Open"].shift(1)) & (
        df["Close"] > df["Open"] * 1.002
    )
    df["Order_Block_Sell"] = (df["Close"].shift(1) > df["Open"].shift(1)) & (
        df["Close"] < df["Open"] * 0.998
    )

  def elliott_wave_approximation(self):
    df = self.df
    window = 5
    df["Swing_High"] = (
        df["High"] == df["High"].rolling(window=window, center=True).max()
    )
    df["Swing_Low"] = (
        df["Low"] == df["Low"].rolling(window=window, center=True).min()
    )

    recent_lows = df[df["Swing_Low"]].tail(3)
    recent_highs = df[df["Swing_High"]].tail(3)

    wave_status = "Neutral"
    if len(recent_lows) >= 2 and len(recent_highs) >= 2:
      if (
          recent_lows["Low"].iloc[-1] > recent_lows["Low"].iloc[-2]
          and recent_highs["High"].iloc[-1] > recent_highs["High"].iloc[-2]
      ):
        wave_status = "Bullish Impulse (Wave 3 or 5 Phase)"
      elif (
          recent_lows["Low"].iloc[-1] < recent_lows["Low"].iloc[-2]
          and recent_highs["High"].iloc[-1] < recent_highs["High"].iloc[-2]
      ):
        wave_status = "Bearish Correction / Impulsive Down"

    return wave_status

  def generate_report(self):
    self.fetch_data()
    self.apply_technical_analysis()
    self.detect_smc_ict_elements()
    wave_state = self.elliott_wave_approximation()

    last_row = self.df.iloc[-1]
    current_price = float(last_row["Close"])
    atr = float(last_row["ATR"])
    rsi = float(last_row["RSI"])
    ema_50 = float(last_row["EMA_50"])
    ema_200 = float(last_row["EMA_200"])

    score = 0
    reasons = []

    if current_price > ema_50 > ema_200:
      score += 2
      reasons.append("اتجاه صاعد (EMA 50 > EMA 200)")
    elif current_price < ema_50 < ema_200:
      score -= 2
      reasons.append("اتجاه هابط (EMA 50 < EMA 200)")

    if rsi < 40:
      score += 1
      reasons.append(f"RSI في مناطق تشبع بيعي ({rsi:.1f})")
    elif rsi > 60:
      score -= 1
      reasons.append(f"RSI في مناطق تشبع شرائي ({rsi:.1f})")

    if last_row["FVG_Bullish"] or last_row["Order_Block_Buy"]:
      score += 3
      reasons.append("تم اكتشاف منطقة سيولة شرائية (Bullish OB / FVG - ICT/SMC)")
    if last_row["FVG_Bearish"] or last_row["Order_Block_Sell"]:
      score -= 3
      reasons.append("تم اكتشاف منطقة سيولة بيعية (Bearish OB / FVG - ICT/SMC)")

    reasons.append(f"حالة موجات أليوت: {wave_state}")
    if "Bullish" in wave_state:
      score += 2
    elif "Bearish" in wave_state:
      score -= 2

    signal = "NEUTRAL (انتظار فرصة أوضح)"
    entry_zone = [
        round(current_price - (0.5 * atr), 2),
        round(current_price + (0.5 * atr), 2),
    ]
    stop_loss = 0
    take_profit_1 = 0
    take_profit_2 = 0

    if score >= 3:
      signal = "BUY (شراء - فرصة قوية متوافقة)"
      stop_loss = round(current_price - (1.5 * atr), 2)
      take_profit_1 = round(current_price + (2.0 * atr), 2)
      take_profit_2 = round(current_price + (3.5 * atr), 2)
    elif score <= -3:
      signal = "SELL (بيع - فرصة قوية متوافقة)"
      stop_loss = round(current_price + (1.5 * atr), 2)
      take_profit_1 = round(current_price - (2.0 * atr), 2)
      take_profit_2 = round(current_price - (3.5 * atr), 2)

    return {
        "symbol": self.symbol,
        "current_price": round(current_price, 2),
        "signal": signal,
        "total_score": score,
        "strategy_levels": {
            "entry_zone": entry_zone,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
        },
        "indicators": {"rsi": round(rsi, 2), "atr": round(atr, 2)},
        "reasons": reasons,
    }


@app.get("/")
def home():
  return {
      "message": "مرحباً بك في نظام تحليل الذهب المتقدم (SMC, ICT, Elliott Wave)",
      "docs_endpoint": "/docs",
      "analyze_endpoint": "/analyze/gold",
  }


@app.get("/analyze/gold")
def analyze_gold():
  analyzer = AdvancedGoldAnalyzer(symbol="GC=F", period="60d", interval="1h")
  return analyzer.generate_report()
