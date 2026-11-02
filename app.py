from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import yfinance as yf

app = FastAPI(title="Ultimate Institutional AI Trading Engine v6", version="6.0")


class SmartEntryGatekeeper:
  """بوابة الذكاء الاصطناعي لفحص جودة الدخول وتحديد ما إذا كان الوقت مناسباً أم يتطلب الانتظار"""

  def __init__(self, df):
    self.df = df

  def evaluate(self):
    last = self.df.iloc[-1]
    # حساب تقييم شامل لتحديد قوة الفرصة
    score = 0.0
    reasons = []

    # فحص المتوسطات
    if last["Close"] > last["EMA_50"] > last["EMA_200"]:
      score += 1.0
      reasons.append("الهيكل العام صاعد على المدى المتوسط")
    elif last["Close"] < last["EMA_50"] < last["EMA_200"]:
      score -= 1.0
      reasons.append("الهيكل العام هابط على المدى المتوسط")
    else:
      reasons.append("السوق في مرحلة تذبذب وتداخل في المتوسطات")

    # فحص التشبعات عبر RSI
    rsi = last["RSI"]
    if rsi < 35:
      score += 1.2
      reasons.append(
          f"مؤشر القوة النسبية في مناطق تشبع بيعي قوية عند مستوى {rsi:.1f}"
      )
    elif rsi > 65:
      score -= 1.2
      reasons.append(
          f"مؤشر القوة النسبية في مناطق تشبع شرائي قوية عند مستوى {rsi:.1f}"
      )
    else:
      reasons.append(
          f"مؤشر القوة النسبية في منطقة محايدة آمنة عند مستوى {rsi:.1f}"
      )

    # فحص السيولة SMC / ICT
    if last["Order_Block_Buy"] or last["FVG_Bullish"]:
      score += 1.5
      reasons.append("تم رصد تفاعل حقيقي مع منطقة سيولة شرائية (Order Block / FVG)")
    elif last["Order_Block_Sell"] or last["FVG_Bearish"]:
      score -= 1.5
      reasons.append("تم رصد تفاعل حقيقي مع منطقة سيولة بيعية (Order Block / FVG)")
    else:
      reasons.append("لا يوجد تفاعل مؤسسي حالي مع مناطق الأوامر الفراغية")

    # تحديد ما إذا كان الدخول جيداً أم يتطلب الانتظار
    # إذا كانت القوة أقل من عتبة الأمان، ننصح بالانتظار وعدم الدخول العشوائي
    price = float(last["Close"])
    atr = float(last["ATR"])

    if abs(score) < 1.2:
      # السوق غير مناسب والدخول سيء - نطلب الانتظار ونعطي نقطة تعليق
      action = "WAIT"
      title = "حالة ترقب - الدخول الحالي غير آمن (لا تدخل)"
      confidence = round(45.0 + (abs(score) * 10), 1)
      if score >= 0:
        pending_entry = round(price - (0.8 * atr), 2)  # انتظار هبوط لتصحيح
        sl = round(pending_entry - (1.5 * atr), 2)
        tp1 = round(pending_entry + (2.0 * atr), 2)
        tp2 = round(pending_entry + (3.5 * atr), 2)
      else:
        pending_entry = round(price + (0.8 * atr), 2)  # انتظار صعود لتصحيح
        sl = round(pending_entry + (1.5 * atr), 2)
        tp1 = round(pending_entry - (2.0 * atr), 2)
        tp2 = round(pending_entry - (3.5 * atr), 2)
    else:
      if score > 0:
        action = "BUY"
        title = "إشارة شراء مؤكدة وعالية الجودة"
        confidence = round(72.0 + (score * 8), 1)
        pending_entry = round(price, 2)
        sl = round(price - (1.5 * atr), 2)
        tp1 = round(price + (2.0 * atr), 2)
        tp2 = round(price + (3.5 * atr), 2)
      else:
        action = "SELL"
        title = "إشارة بيع مؤكدة وعالية الجودة"
        confidence = round(72.0 + (abs(score) * 8), 1)
        pending_entry = round(price, 2)
        sl = round(price + (1.5 * atr), 2)
        tp1 = round(price - (2.0 * atr), 2)
        tp2 = round(price - (3.5 * atr), 2)

    return action, title, confidence, pending_entry, sl, tp1, tp2, reasons


class MarketEngine:

  def __init__(self, symbol="GC=F", period="180d", interval="1h"):
    self.symbol = symbol
    self.period = period
    self.interval = interval
    self.df = None

  def fetch(self):
    ticker = yf.Ticker(self.symbol)
    self.df = ticker.history(period=self.period, interval=self.interval)
    if self.df.empty:
      raise HTTPException(status_code=500, detail="فشل في جلب البيانات.")
    self.df = self.df[["Open", "High", "Low", "Close", "Volume"]].dropna()

  def process(self):
    df = self.df
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
    df["ATR"] = (
        pd.concat([high_low, high_close, low_close], axis=1)
        .max(axis=1)
        .rolling(14)
        .mean()
    )

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

  def analyze(self):
    self.fetch()
    self.process()

    gatekeeper = SmartEntryGatekeeper(self.df)
    action, title, confidence, entry, sl, tp1, tp2, reasons = (
        gatekeeper.evaluate()
    )

    last = self.df.iloc[-1]
    price = float(last["Close"])

    candles = []
    for idx, row in self.df.tail(150).iterrows():
      candles.append({
          "time": int(idx.timestamp()),
          "open": float(row["Open"]),
          "high": float(row["High"]),
          "low": float(row["Low"]),
          "close": float(row["Close"]),
      })

    return {
        "symbol": self.symbol,
        "current_price": round(price, 2),
        "action": action,
        "title": title,
        "confidence": confidence,
        "levels": {"entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2},
        "reasons": reasons,
        "candles": candles,
    }


@app.get("/", response_class=HTMLResponse)
def home():
  return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>Advanced AI Market Gateway</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: system-ui, -apple-system, sans-serif; background-color: #000000; color: #ffffff; height: 100vh; overflow: hidden; }
            .header { height: 60px; background: #050505; border-bottom: 1px solid #141414; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }
            .brand { font-size: 15px; font-weight: 700; color: #e5e5e5; }
            .menu { display: flex; gap: 8px; }
            .m-btn { background: #0a0a0a; border: 1px solid #222; color: #888; padding: 7px 16px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; }
            .m-btn.active { background: #222; color: #fff; border-color: #444; }
            .layout { display: flex; height: calc(100vh - 60px); }
            .panel { width: 340px; background: #030303; border-right: 1px solid #121212; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
            .box { background: #080808; border: 1px solid #161616; padding: 14px; border-radius: 6px; }
            .badge-buy { background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 8px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 13px; }
            .badge-sell { background: rgba(248, 113, 113, 0.1); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3); padding: 8px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 13px; }
            .badge-wait { background: rgba(234, 179, 8, 0.1); color: #eab308; border: 1px solid rgba(234, 179, 8, 0.3); padding: 8px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 13px; }
            .row { display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px; padding-bottom: 4px; border-bottom: 1px solid #111; }
            .lbl { color: #666; }
            .val { font-family: monospace; font-weight: 600; }
            .chart-wrap { flex: 1; background: #000000; position: relative; }
            #chart { width: 100%; height: 100%; }
            .strat-list { font-size: 11px; color: #888; list-style: none; max-height: 180px; overflow-y: auto; }
            .strat-list li { margin-bottom: 6px; padding-right: 8px; border-right: 2px solid #333; }
            .status-bar { font-size: 10px; color: #22c55e; text-align: center; margin-top: 4px; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="brand">ULTIMATE INSTITUTIONAL ENGINE</div>
            <div class="menu">
                <button class="m-btn active" id="btn-GC=F" onclick="switchAsset('GC=F')">GOLD</button>
                <button class="m-btn" id="btn-CL=F" onclick="switchAsset('CL=F')">OIL</button>
                <button class="m-btn" id="btn-BTC-USD" onclick="switchAsset('BTC-USD')">BITCOIN</button>
            </div>
        </div>
        <div class="layout">
            <div class="panel">
                <div class="box">
                    <div style="font-size:10px; color:#666; margin-bottom:4px;">حالة فحص جودة الدخول</div>
                    <div id="signal-badge" class="badge-wait">جاري الفحص...</div>
                    <div style="font-size:11px; color:#888; margin-top:6px; text-align:center;">نسبة احتمال النجاح: <span id="conf-val" style="color:#fff;">0</span>%</div>
                    <div class="status-bar" id="live-status">التحديث الحي: مفعل (كل 30 ثانية)</div>
                </div>
                <div class="box">
                    <div style="font-size:10px; color:#666; margin-bottom:8px;">المستويات الحية ومناطق الانتظار</div>
                    <div class="row"><span class="lbl">السعر الحي الحالي</span><span id="p-live" class="val" style="color:#facc15;">0.00</span></div>
                    <div class="row"><span class="lbl">منطقة الدخول (أو المنتظرة)</span><span id="p-entry" class="val" style="color:#38bdf8;">0.00</span></div>
                    <div class="row"><span class="lbl">وقف الخسارة (SL)</span><span id="p-sl" class="val" style="color:#f87171;">0.00</span></div>
                    <div class="row"><span class="lbl">الهدف الأول (TP1)</span><span id="p-tp1" class="val" style="color:#4ade80;">0.00</span></div>
                </div>
                <div class="box" style="flex:1;">
                    <div style="font-size:10px; color:#666; margin-bottom:8px;">فحص المعايير الاستراتيجية</div>
                    <ul id="reasons-ul" class="strat-list"></ul>
                </div>
            </div>
            <div class="chart-wrap">
                <div id="chart"></div>
            </div>
        </div>
        <script>
            let chart, series, activeLines = [];
            let currentSymbol = 'GC=F';
            let updateInterval = null;

            function initChart() {
                chart = LightweightCharts.createChart(document.getElementById('chart'), {
                    layout: { background: { type: 'solid', color: '#000000' }, textColor: '#666' },
                    grid: { vertLines: { color: '#0a0a0a' }, horzLines: { color: '#0a0a0a' } },
                    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                    timeScale: { borderColor: '#161616', timeVisible: true }
                });
                series = chart.addCandlestickSeries({
                    upColor: '#22c55e', downColor: '#ef4444', borderVisible: false,
                    wickUpColor: '#22c55e', wickDownColor: '#ef4444'
                });
                window.addEventListener('resize', () => chart.applyOptions({ width: document.getElementById('chart').clientWidth, height: document.getElementById('chart').clientHeight }));
            }

            function clearLines() {
                activeLines.forEach(l => series.removePriceLine(l));
                activeLines = [];
            }

            async function loadMarket(symbol, isBackground = false) {
                if(!chart) initChart();
                if(!isBackground) {
                    currentSymbol = symbol;
                    document.querySelectorAll('.m-btn').forEach(b => b.classList.remove('active'));
                    document.getElementById('btn-' + symbol).classList.add('active');
                }

                try {
                    let res = await fetch('/analyze/' + symbol);
                    let data = await res.json();

                    // تحديث الشارت والبيانات
                    series.setData(data.candles);
                    clearLines();

                    const badge = document.getElementById('signal-badge');
                    badge.innerText = data.title;
                    if(data.action === 'BUY') badge.className = 'badge-buy';
                    else if(data.action === 'SELL') badge.className = 'badge-sell';
                    else badge.className = 'badge-wait';

                    document.getElementById('conf-val').innerText = data.confidence;
                    document.getElementById('p-live').innerText = data.current_price;
                    document.getElementById('p-entry').innerText = data.levels.entry;
                    document.getElementById('p-sl').innerText = data.levels.sl;
                    document.getElementById('p-tp1').innerText = data.levels.tp1;

                    let html = '';
                    data.reasons.forEach(r => { html += `<li>${r}</li>`; });
                    document.getElementById('reasons-ul').innerHTML = html;

                    // تحديد ألوان الخطوط على الشارت بناء على نوع الصفقة (أزرق للشراء، أحمر للبيع، أصفر للانتظار)
                    let themeColor = data.action === 'BUY' ? '#38bdf8' : (data.action === 'SELL' ? '#f87171' : '#eab308');

                    // خط السعر الحي
                    const liveLine = series.createPriceLine({
                        price: data.current_price,
                        color: '#facc15',
                        lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Dotted,
                        axisLabelVisible: true,
                        title: 'LIVE PRICE',
                    });

                    // خط الدخول أو منطقة الانتظار
                    const entryLine = series.createPriceLine({
                        price: data.levels.entry,
                        color: themeColor,
                        lineWidth: 2,
                        lineStyle: data.action === 'WAIT' ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
                        axisLabelVisible: true,
                        title: data.action === 'WAIT' ? 'PENDING WAIT ZONE' : data.action + ' ENTRY',
                    });

                    // وقف الخسارة
                    const slLine = series.createPriceLine({
                        price: data.levels.sl,
                        color: '#ef4444',
                        lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'STOP LOSS',
                    });

                    // الهدف
                    const tp1Line = series.createPriceLine({
                        price: data.levels.tp1,
                        color: '#22c55e',
                        lineWidth: 2,
                        lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'TARGET 1',
                    });

                    activeLines.push(liveLine, entryLine, slLine, tp1Line);
                    if(!isBackground) chart.timeScale().fitContent();

                } catch(e) {
                    console.error(e);
                }
            }

            function switchAsset(symbol) {
                loadMarket(symbol, false);
            }

            window.onload = () => {
                loadMarket('GC=F', false);
                // تفعيل التحديث التلقائي كل 30 ثانية لتحديث الحركة والتحليل
                if(updateInterval) clearInterval(updateInterval);
                updateInterval = setInterval(() => {
                    loadMarket(currentSymbol, true);
                }, 30000);
            };
        </script>
    </body>
    </html>
    """


@app.get("/analyze/{symbol}")
def analyze(symbol: str):
  engine = MarketEngine(symbol=symbol, period="180d", interval="1h")
  return engine.analyze()
