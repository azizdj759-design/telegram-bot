from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import yfinance as yf

app = FastAPI(
    title="AI-Supervised Institutional Trading Engine",
    version="4.0",
)


class AIStrategySupervisor:
  """مشرف الذكاء الاصطناعي الذي يحلل كل إستراتيجية منفصلة ويصدر قرار الشراء/البيع المباشر"""

  def __init__(self, df):
    self.df = df

  def analyze_smc(self):
    last = self.df.iloc[-1]
    ob_buy = last["Order_Block_Buy"]
    ob_sell = last["Order_Block_Sell"]
    if ob_buy:
      return 1.0, "SMC Order Block الشرائي مفعل"
    if ob_sell:
      return -1.0, "SMC Order Block البيعي مفعل"
    return (
        0.2 if last["Close"] > last["EMA_50"] else -0.2
    ), "SMC: سيولة الاتجاه الهيكلي"

  def analyze_ict(self):
    last = self.df.iloc[-1]
    fvg_bull = last["FVG_Bullish"]
    fvg_bear = last["FVG_Bearish"]
    if fvg_bull:
      return 1.0, "ICT Fair Value Gaps (FVG) شرائي"
    if fvg_bear:
      return -1.0, "ICT Fair Value Gaps (FVG) بيعي"
    return (
        0.3 if last["Close"] > last["EMA_21"] else -0.3
    ), "ICT: تتبع نطاق السيولة"

  def analyze_elliott(self):
    recent_lows = self.df[self.df["Swing_Low"]].tail(3)
    recent_highs = self.df[self.df["Swing_High"]].tail(3)
    if len(recent_lows) >= 2 and len(recent_highs) >= 2:
      if (
          recent_lows["Low"].iloc[-1] > recent_lows["Low"].iloc[-2]
          and recent_highs["High"].iloc[-1] > recent_highs["High"].iloc[-2]
      ):
        return 0.9, "Elliott Wave: الموجة الدافعة 3/5 صاعدة"
      elif (
          recent_lows["Low"].iloc[-1] < recent_lows["Low"].iloc[-2]
          and recent_highs["High"].iloc[-1] < recent_highs["High"].iloc[-2]
      ):
        return -0.9, "Elliott Wave: دفق موجي تصحيحي هابط"
    return 0.0, "Elliott Wave: مرحلة تجميع موجي"

  def analyze_technical(self):
    last = self.df.iloc[-1]
    score = 0.0
    if last["EMA_50"] > last["EMA_200"]:
      score += 0.5
    else:
      score -= 0.5
    if last["RSI"] < 40:
      score += 0.5
    elif last["RSI"] > 60:
      score -= 0.5
    return score, f"التحليل الفني (RSI: {last['RSI']:.1f})"

  def evaluate_all(self):
    smc_v, smc_msg = self.analyze_smc()
    ict_v, ict_msg = self.analyze_ict()
    elliott_v, elliott_msg = self.analyze_elliott()
    tech_v, tech_msg = self.analyze_technical()

    # أوزان الذكاء الاصطناعي المرجحة للحسم
    weights = {"SMC": 0.35, "ICT": 0.30, "ELLIOTT": 0.20, "TECH": 0.15}

    final_score = (
        (smc_v * weights["SMC"])
        + (ict_v * weights["ICT"])
        + (elliott_v * weights["ELLIOTT"])
        + (tech_v * weights["TECH"])
    )

    reasons = [smc_msg, ict_msg, elliott_msg, tech_msg]
    return final_score, reasons


class AbsoluteMarketAnalyzer:

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
          status_code=500, detail="فشل في جلب البيانات من المصدر."
      )
    self.df = self.df[["Open", "High", "Low", "Close", "Volume"]].dropna()

  def prepare_indicators(self):
    df = self.df
    df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
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

    df["FVG_Bullish"] = (df["Low"].shift(-1) > df["High"].shift(1)) & (
        df["Close"] > df["Open"]
    )
    df["FVG_Bearish"] = (df["High"].shift(-1) < df["Low"].shift(1)) & (
        df["Close"] < df["Open"]
    )
    df["Order_Block_Buy"] = (df["Close"].shift(1) < df["Open"].shift(1)) & (
        df["Close"] > df["Open"] * 1.001
    )
    df["Order_Block_Sell"] = (df["Close"].shift(1) > df["Open"].shift(1)) & (
        df["Close"] < df["Open"] * 0.999
    )

    window = 5
    df["Swing_High"] = (
        df["High"] == df["High"].rolling(window=window, center=True).max()
    )
    df["Swing_Low"] = (
        df["Low"] == df["Low"].rolling(window=window, center=True).min()
    )

  def generate_analysis(self):
    self.fetch_data()
    self.prepare_indicators()

    ai_supervisor = AIStrategySupervisor(self.df)
    score, breakdown_reasons = ai_supervisor.evaluate_all()

    last = self.df.iloc[-1]
    price = float(last["Close"])
    atr = float(last["ATR"])

    # قرار الحسم المباشر دون حياد مبهم
    if score >= 0:
      action = "BUY"
      decision_title = "شراء (BUY) - إشارة صريحة من الذكاء الاصطناعي"
      entry_level = round(price, 2)
      stop_loss = round(price - (1.5 * atr), 2)
      tp1 = round(price + (2.0 * atr), 2)
      tp2 = round(price + (3.8 * atr), 2)
    else:
      action = "SELL"
      decision_title = "بيع (SELL) - إشارة صريحة من الذكاء الاصطناعي"
      entry_level = round(price, 2)
      stop_loss = round(price + (1.5 * atr), 2)
      tp1 = round(price - (2.0 * atr), 2)
      tp2 = round(price - (3.8 * atr), 2)

    chart_candles = []
    for idx, row in self.df.tail(120).iterrows():
      chart_candles.append({
          "time": int(idx.timestamp()),
          "open": float(row["Open"]),
          "high": float(row["High"]),
          "low": float(row["Low"]),
          "close": float(row["Close"]),
      })

    return {
        "symbol": self.symbol,
        "price": round(price, 2),
        "action": action,
        "decision_title": decision_title,
        "ai_confidence_score": round(abs(score) * 100, 1),
        "levels": {
            "entry": entry_level,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
        },
        "breakdown": breakdown_reasons,
        "candles": chart_candles,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
  html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>AI Institutional Black Chart Engine</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #000000; color: #ffffff; height: 100vh; overflow: hidden; }
            .header { height: 60px; background: #0a0a0a; border-bottom: 1px solid #1a1a1a; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }
            .title { font-size: 16px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px; }
            .btn-group { display: flex; gap: 8px; }
            .btn { background: #121212; border: 1px solid #262626; color: #a3a3a3; padding: 8px 16px; border-radius: 4px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
            .btn:hover, .btn.active { background: #262626; color: #ffffff; border-color: #404040; }
            .main-layout { display: flex; height: calc(100vh - 60px); }
            .chart-box { flex: 1; height: 100%; background: #000000; position: relative; }
            #chart { width: 100%; height: 100%; }
            .sidebar { width: 320px; background: #050505; border-right: 1px solid #1a1a1a; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
            .status-card { background: #0a0a0a; border: 1px solid #1f1f1f; padding: 15px; border-radius: 6px; }
            .badge-buy { background: #052e16; color: #4ade80; border: 1px solid #14532d; padding: 6px 12px; border-radius: 4px; font-weight: 700; font-size: 14px; text-align: center; }
            .badge-sell { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; padding: 6px 12px; border-radius: 4px; font-weight: 700; font-size: 14px; text-align: center; }
            .level-row { display: flex; justify-content: space-between; font-size: 13px; margin-top: 8px; padding-bottom: 4px; border-bottom: 1px solid #141414; }
            .level-label { color: #737373; }
            .level-val { font-weight: 600; font-family: monospace; }
            .reasons-list { font-size: 12px; color: #a3a3a3; list-style: none; }
            .reasons-list li { margin-bottom: 8px; padding-right: 10px; border-right: 2px solid #262626; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">AI INSTINCT TRADING ENGINE</div>
            <div class="btn-group">
                <button class="btn active" id="btn-GC=F" onclick="changeAsset('GC=F')">GOLD</button>
                <button class="btn" id="btn-CL=F" onclick="changeAsset('CL=F')">OIL</button>
                <button class="btn" id="btn-BTC-USD" onclick="changeAsset('BTC-USD')">BITCOIN</button>
            </div>
        </div>

        <div class="main-layout">
            <div class="sidebar">
                <div class="status-card">
                    <div style="font-size: 11px; color: #737373; margin-bottom: 5px;">قرار الذكاء الاصطناعي والمشرف</div>
                    <div id="badge-action" class="badge-buy">LOADING...</div>
                    <div style="font-size: 12px; color: #a3a3a3; margin-top: 8px; text-align: center;">ثقة النموذج: <span id="val-confidence">0</span>%</div>
                </div>

                <div class="status-card">
                    <div style="font-size: 11px; color: #737373; margin-bottom: 10px;">المستويات المرسومة على الشارت</div>
                    <div class="level-row"><span class="level-label">الدخول المرتقب</span><span id="val-entry" class="level-val" style="color:#38bdf8;">0.00</span></div>
                    <div class="level-row"><span class="level-label">وقف الخسارة (SL)</span><span id="val-sl" class="level-val" style="color:#f87171;">0.00</span></div>
                    <div class="level-row"><span class="level-label">الهدف الأول (TP1)</span><span id="val-tp1" class="level-val" style="color:#4ade80;">0.00</span></div>
                    <div class="level-row"><span class="level-label">الهدف الثاني (TP2)</span><span id="val-tp2" class="level-val" style="color:#4ade80;">0.00</span></div>
                </div>

                <div class="status-card" style="flex:1; overflow-y:auto;">
                    <div style="font-size: 11px; color: #737373; margin-bottom: 10px;">فحص الاستراتيجيات المزدوجة</div>
                    <ul id="reasons-box" class="reasons-list"></ul>
                </div>
            </div>

            <div class="chart-box">
                <div id="chart"></div>
            </div>
        </div>

        <script>
            let chart;
            let candleSeries;
            let currentPriceLines = [];

            function initChart() {
                const container = document.getElementById('chart');
                chart = LightweightCharts.createChart(container, {
                    layout: { background: { type: 'solid', color: '#000000' }, textColor: '#737373' },
                    grid: { vertLines: { color: '#0f0f0f' }, horzLines: { color: '#0f0f0f' } },
                    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                    priceScale: { borderColor: '#1f1f1f' },
                    timeScale: { borderColor: '#1f1f1f', timeVisible: true }
                });

                candleSeries = chart.addCandlestickSeries({
                    upColor: '#22c55e', downColor: '#ef4444', borderVisible: false,
                    wickUpColor: '#22c55e', wickDownColor: '#ef4444'
                });

                window.addEventListener('resize', () => {
                    chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
                });
            }

            function clearPriceLines() {
                currentPriceLines.forEach(line => candleSeries.removePriceLine(line));
                currentPriceLines = [];
            }

            async function changeAsset(symbol) {
                document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + symbol).classList.add('active');
                
                if (!chart) initChart();
                clearPriceLines();

                try {
                    let res = await fetch('/analyze/' + symbol);
                    let data = await res.json();

                    candleSeries.setData(data.candles);

                    // تحديث واجهة الإشارات
                    const badge = document.getElementById('badge-action');
                    badge.innerText = data.action === 'BUY' ? 'إشارة شراء (BUY)' : 'إشارة بيع (SELL)';
                    badge.className = data.action === 'BUY' ? 'badge-buy' : 'badge-sell';

                    document.getElementById('val-confidence').innerText = data.ai_confidence_score;
                    document.getElementById('val-entry').innerText = data.levels.entry;
                    document.getElementById('val-sl').innerText = data.levels.stop_loss;
                    document.getElementById('val-tp1').innerText = data.levels.tp1;
                    document.getElementById('val-tp2').innerText = data.levels.tp2;

                    let listHtml = '';
                    data.breakdown.forEach(item => { listHtml += `<li>${item}</li>`; });
                    document.getElementById('reasons-box').innerHTML = listHtml;

                    // رسم مستويات الدخول والأهداف مباشرة على الشارت
                    const entryLine = candleSeries.createPriceLine({
                        price: data.levels.entry,
                        color: '#38bdf8',
                        lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Solid,
                        axisLabelVisible: true,
                        title: 'ENTRY (منطقة الدخول)',
                    });
                    
                    const slLine = candleSeries.createPriceLine({
                        price: data.levels.stop_loss,
                        color: '#f87171',
                        lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'STOP LOSS',
                    });

                    const tp1Line = candleSeries.createPriceLine({
                        price: data.levels.tp1,
                        color: '#4ade80',
                        lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'TARGET 1',
                    });

                    const tp2Line = candleSeries.createPriceLine({
                        price: data.levels.tp2,
                        color: '#22c55e',
                        lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Dotted,
                        axisLabelVisible: true,
                        title: 'TARGET 2',
                    });

                    currentPriceLines.push(entryLine, slLine, tp1Line, tp2Line);
                    chart.timeScale().fitContent();

                } catch (err) {
                    console.error("Error loading asset data", err);
                }
            }

            window.onload = () => { changeAsset('GC=F'); };
        </script>
    </body>
    </html>
    """
  return html_content


@app.get("/analyze/{symbol}")
def analyze(symbol: str):
  analyzer = AbsoluteMarketAnalyzer(
      symbol=symbol, period="180d", interval="1h"
  )
  return analyzer.generate_analysis()
