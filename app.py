from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import yfinance as yf

app = FastAPI(
    title="Institutional Market Intelligence & Backtesting Engine",
    version="2.0",
    description=(
        "النظام الآلي المتقدم لتحليل أسواق الذهب، البترول، والبيتكوين وإجراء"
        " الاختبارات العكسية"
    ),
)


class InstitutionalMarketAnalyzer:

  def __init__(self, symbol="GC=F", period="180d", interval="1h"):
    self.symbol = symbol
    self.period = period
    self.interval = interval
    self.df = None

  def fetch_data(self):
    ticker = yf.Ticker(self.symbol)
    self.df = ticker.history(period=self.period, interval=self.interval)
    if self.df.empty:
      raise HTTPException(
          status_code=500, detail="فشل في استرداد بيانات السوق الحية."
      )
    self.df = self.df[["Open", "High", "Low", "Close", "Volume"]].dropna()

  def apply_core_analytics(self):
    df = self.df
    # التحليل الكلاسيكي للزخم والاتجاه
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

    # رصد الفجوات السعرية (FVG) ومنطاق أوامر البنوك (Order Blocks) - SMC & ICT
    df["FVG_Bullish"] = (df["Low"].shift(-1) > df["High"].shift(1)) & (
        df["Close"] > df["Open"]
    )
    df["FVG_Bearish"] = (df["High"].shift(-1) < df["Low"].shift(1)) & (
        df["Close"] < df["Open"]
    )

    df["Order_Block_Buy"] = (df["Close"].shift(1) < df["Open"].shift(1)) & (
        df["Close"] > df["Open"] * 1.0015
    )
    df["Order_Block_Sell"] = (df["Close"].shift(1) > df["Open"].shift(1)) & (
        df["Close"] < df["Open"] * 0.9985
    )

  def run_backtest(self):
    """محرك اختبار عكسي حقيقي يقيس دقة الاستراتيجية على البيانات التاريخية"""
    df = self.df.copy()
    capital = 10000.0
    position = 0
    entry_price = 0.0
    trades = []

    for i in range(200, len(df) - 1):
      current_slice = df.iloc[:i]
      price = current_slice["Close"].iloc[-1]
      atr = current_slice["ATR"].iloc[-1]
      rsi = current_slice["RSI"].iloc[-1]
      ema_50 = current_slice["EMA_50"].iloc[-1]
      ema_200 = current_slice["EMA_200"].iloc[-1]

      score = 0
      if price > ema_50 > ema_200:
        score += 2
      elif price < ema_50 < ema_200:
        score -= 2

      if rsi < 40:
        score += 1
      elif rsi > 60:
        score -= 1

      if (
          current_slice["FVG_Bullish"].iloc[-1]
          or current_slice["Order_Block_Buy"].iloc[-1]
      ):
        score += 3
      if (
          current_slice["FVG_Bearish"].iloc[-1]
          or current_slice["Order_Block_Sell"].iloc[-1]
      ):
        score -= 3

      # تنفيذ الصفقات الافتراضية بناء على النتيجة
      if position == 0:
        if score >= 3:
          position = 1  # شراء
          entry_price = price
        elif score <= -3:
          position = -1  # بيع
          entry_price = price
      elif position == 1:
        # جني ارباح او وقف خسارة
        if price >= entry_price + (2.0 * atr) or price <= entry_price - (
            1.5 * atr
        ):
          pnl = (price - entry_price) / entry_price
          capital *= 1 + pnl
          trades.append(1 if pnl > 0 else 0)
          position = 0
      elif position == -1:
        if price <= entry_price - (2.0 * atr) or price >= entry_price + (
            1.5 * atr
        ):
          pnl = (entry_price - price) / entry_price
          capital *= 1 + pnl
          trades.append(1 if pnl > 0 else 0)
          position = 0

    win_rate = (sum(trades) / len(trades) * 100) if trades else 0.0
    return {
        "final_capital": round(capital, 2),
        "total_trades": len(trades),
        "win_rate_percentage": round(win_rate, 2),
    }

  def generate_live_analysis(self):
    self.fetch_data()
    self.apply_core_analytics()
    backtest_results = self.run_backtest()

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
      reasons.append("الهيكل العام صاعد (EMA 50 فوق EMA 200)")
    elif current_price < ema_50 < ema_200:
      score -= 2
      reasons.append("الهيكل العام هابط (EMA 50 تحت EMA 200)")

    if rsi < 40:
      score += 1
      reasons.append(
          f"مؤشر القوة النسبية في مناطق تشبع بيعي عند مستوى {rsi:.1f}"
      )
    elif rsi > 60:
      score -= 1
      reasons.append(
          f"مؤشر القوة النسبية في مناطق تشبع شرائي عند مستوى {rsi:.1f}"
      )

    if last_row["FVG_Bullish"] or last_row["Order_Block_Buy"]:
      score += 3
      reasons.append("تم رصد منطقة سيولة مؤسسية شرائية (SMC / ICT FVG)")
    if last_row["FVG_Bearish"] or last_row["Order_Block_Sell"]:
      score -= 3
      reasons.append("تم رصد منطقة سيولة مؤسسية بيعية (SMC / ICT FVG)")

    signal = "NEUTRAL (حياد - انتظار اكتمال المعايير)"
    entry_zone = [
        round(current_price - (0.3 * atr), 2),
        round(current_price + (0.3 * atr), 2),
    ]
    stop_loss = 0.0
    take_profit_1 = 0.0
    take_profit_2 = 0.0

    if score >= 3:
      signal = "STRONG BUY (فرصة شراء مؤسسية عالية الاحتمالية)"
      stop_loss = round(current_price - (1.5 * atr), 2)
      take_profit_1 = round(current_price + (2.0 * atr), 2)
      take_profit_2 = round(current_price + (3.5 * atr), 2)
    elif score <= -3:
      signal = "STRONG SELL (فرصة بيع مؤسسية عالية الاحتمالية)"
      stop_loss = round(current_price + (1.5 * atr), 2)
      take_profit_1 = round(current_price - (2.0 * atr), 2)
      take_profit_2 = round(current_price - (3.5 * atr), 2)

    return {
        "symbol": self.symbol,
        "current_price": round(current_price, 2),
        "signal": signal,
        "consensus_score": score,
        "execution_levels": {
            "entry_zone": entry_zone,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
        },
        "indicators": {"rsi": round(rsi, 2), "atr": round(atr, 2)},
        "backtest_performance": backtest_results,
        "analytical_reasons": reasons,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
  html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>منصة التحليل المالي المؤسسي المتقدم</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; }
            .container { max-width: 1000px; margin: auto; background: #161b22; padding: 30px; border-radius: 8px; border: 1px solid #30363d; }
            h1 { text-align: center; color: #58a6ff; font-size: 24px; margin-bottom: 30px; }
            .controls { display: flex; justify-content: center; gap: 15px; margin-bottom: 30px; }
            button { background: #238636; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; }
            button:hover { background: #2ea043; }
            .card { background: #21262d; border: 1px solid #30363d; padding: 20px; border-radius: 6px; margin-bottom: 20px; }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
            .label { color: #8b949e; font-size: 13px; }
            .value { font-size: 18px; font-weight: bold; color: #f0f6fc; margin-top: 5px; }
            ul { margin: 0; padding-right: 20px; }
            li { margin-bottom: 8px; }
            .loading { text-align: center; font-size: 16px; color: #8b949e; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>منصة الخوارزميات المؤسسية والتحليل المتقدم</h1>
            <div class="controls">
                <button onclick="loadMarket('GC=F')">تحليل الذهب (Gold)</button>
                <button onclick="loadMarket('CL=F')">تحليل البترول (Oil)</button>
                <button onclick="loadMarket('BTC-USD')">تحليل البيتكوين (Bitcoin)</button>
            </div>
            <div id="content" class="loading">اختر الأصل المالي لعرض التحليل الحي ونتائج الاختبار العكسي...</div>
        </div>

        <script>
            async function loadMarket(symbol) {
                document.getElementById('content').innerHTML = '<div class="loading">جاري سحب البيانات التاريخية وتشغيل نماذج SMC و ICT واختبار الأداء...</div>';
                try {
                    let response = await fetch('/analyze/' + symbol);
                    let data = await response.json();
                    
                    let html = `
                        <div class="card">
                            <div class="label">الأصل المالي والأسعار الحية</div>
                            <div class="value">${data.symbol} | السعر الحالي: ${data.current_price} USD</div>
                            <div class="label" style="margin-top: 15px;">قرار الإجماع المؤسسي النهائي</div>
                            <div class="value" style="color: ${data.consensus_score >= 3 ? '#3fb950' : data.consensus_score <= -3 ? '#f85149' : '#d29922'};">${data.signal}</div>
                        </div>
                        
                        <div class="grid">
                            <div class="card">
                                <h3>مستويات التنفيذ الاستراتيجية</h3>
                                <div class="label">منطقة الدخول المقترحة</div>
                                <div class="value">${data.execution_levels.entry_zone[0]} الى ${data.execution_levels.entry_zone[1]}</div>
                                <div class="label" style="margin-top: 10px;">وقف الخسارة (Stop Loss)</div>
                                <div class="value" style="color: #f85149;">${data.execution_levels.stop_loss}</div>
                                <div class="label" style="margin-top: 10px;">الهدف الأول (TP1) / الثاني (TP2)</div>
                                <div class="value" style="color: #3fb950;">${data.execution_levels.take_profit_1} / ${data.execution_levels.take_profit_2}</div>
                            </div>
                            
                            <div class="card">
                                <h3>نتائج الاختبار العكسي التاريخي (Backtest)</h3>
                                <div class="label">إجمالي الصفقات المُختبرة</div>
                                <div class="value">${data.backtest_performance.total_trades} صفقة</div>
                                <div class="label" style="margin-top: 10px;">نسبة النجاح التاريخية (Win Rate)</div>
                                <div class="value">${data.backtest_performance.win_rate_percentage}%</div>
                                <div class="label" style="margin-top: 10px;">رأس المال النهائي (افتراضي من 10,000)</div>
                                <div class="value">${data.backtest_performance.final_capital} USD</div>
                            </div>
                        </div>

                        <div class="card">
                            <h3>المبررات الفنية والمؤسسية</h3>
                            <ul>
                                ${data.analytical_reasons.map(r => `<li>${r}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                    document.getElementById('content').innerHTML = html;
                } catch (err) {
                    document.getElementById('content').innerHTML = '<div style="color: #f85149; text-align: center;">حدث خطأ أثناء جلب البيانات وتحليل السوق.</div>';
                }
            }
            // تحميل الذهب افتراضياً عند فتح الصفحة
            loadMarket('GC=F');
        </script>
    </body>
    </html>
    """
  return html_content


@app.get("/analyze/{symbol}")
def get_analysis(symbol: str):
  analyzer = InstitutionalMarketAnalyzer(
      symbol=symbol, period="180d", interval="1h"
  )
  return analyzer.generate_live_analysis()
