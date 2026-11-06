from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import asyncio
import json
import yfinance as yf
from datetime import datetime, timedelta

app = FastAPI(title="Institutional AI Engine - Corrected", version="8.0")

class AdvancedInstitutionalEngine:
    def __init__(self, symbol="GC=F", period="180d", interval="1h", account_balance=20.0):
        self.symbol = symbol
        self.period = period
        self.interval = interval
        self.account_balance = account_balance  # رصيد الحساب الافتراضي
        self.risk_per_trade = 0.01  # المخاطرة 1% من الحساب
        self.df = None

    def fetch_and_process(self):
        ticker = yf.Ticker(self.symbol)
        raw_df = ticker.history(period=self.period, interval=self.interval)
        
        if raw_df.empty:
            return False
            
        # إزالة الشمعة الحالية غير المكتملة لمنع تغير الإشارة (Repainting)
        self.df = raw_df[["Open", "High", "Low", "Close", "Volume"]].dropna().iloc[:-1]
        df = self.df.copy()

        # المؤشرات الأساسية (بدون تسريب بيانات مستقبلية)
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

        # تصحيح FVG (Fair Value Gap) الحقيقي: فجوة بين الشمعة الحالية وشمعة قبل شمعتين
        # Bullish FVG: Low[current] > High[current-2]
        df["FVG_Bullish"] = df["Low"] > df["High"].shift(2)
        # Bearish FVG: High[current] < Low[current-2]
        df["FVG_Bearish"] = df["High"] < df["Low"].shift(2)

        # تصحيح Order Blocks: شمعة خمراء سابقة اخترقها السعر لأعلى (Buy OB) أو العكس
        df["Order_Block_Buy"] = (df["Close"].shift(1) < df["Open"].shift(1)) & (df["Close"] > df["High"].shift(1))
        df["Order_Block_Sell"] = (df["Close"].shift(1) > df["Open"].shift(1)) & (df["Close"] < df["Low"].shift(1))

        # تصحيح Swing High/Low (بدون center=True)
        df["Swing_High"] = (df["High"] == df["High"].rolling(window=5).max().shift(1))
        df["Swing_Low"] = (df["Low"] == df["Low"].rolling(window=5).min().shift(1))

        self.df = df
        return True

    def analyze_market(self):
        if not self.fetch_and_process():
            return {"error": "Failed to fetch data"}

        last = self.df.iloc[-1]
        price = float(last["Close"])
        atr = float(last["ATR"])
        rsi = float(last["RSI"])

        # --- التحليل التفصيلي (بناء على شموع مغلقة فقط) ---
        strategies = {}
        
        # 1. SMC (Smart Money Concepts)
        smc_val = 1.0 if last["Order_Block_Buy"] else (-1.0 if last["Order_Block_Sell"] else (0.5 if price > last["EMA_50"] else -0.5))
        strategies["SMC"] = {
            "name": "مفاهيم الأموال الذكية (SMC)",
            "status": "اختراق Order Block شرائي" if last["Order_Block_Buy"] else ("اختراق Order Block بيعي" if last["Order_Block_Sell"] else "لا يوجد Order Block نشط"),
            "score": smc_val
        }

        # 2. ICT (Fair Value Gaps)
        ict_val = 1.2 if last["FVG_Bullish"] else (-1.2 if last["FVG_Bearish"] else (0.4 if price > last["EMA_21"] else -0.4))
        strategies["ICT"] = {
            "name": "فجوات السعر (ICT FVG)",
            "status": "فجوة صاعدة (Bullish FVG)" if last["FVG_Bullish"] else ("فجوة هابطة (Bearish FVG)" if last["FVG_Bearish"] else "لا توجد فجوات سعرية"),
            "score": ict_val
        }

        # 3. Elliott Wave (مبسط)
        strategies["Elliott"] = {
            "name": "موجات أليوت الهيكلية",
            "status": "موجة دافعة صاعدة" if price > last["EMA_50"] and last["EMA_50"] > last["EMA_200"] else "موجة تصحيحية هابطة",
            "score": 0.8 if price > last["EMA_50"] and last["EMA_50"] > last["EMA_200"] else -0.8
        }

        # 4. Wyckoff
        strategies["Wyckoff"] = {
            "name": "منهجية ويكوف (السيولة)",
            "status": "مرحلة تجميع" if rsi < 40 and price > last["EMA_200"] else ("مرحلة تصريف" if rsi > 60 else "منطقة متذبذبة"),
            "score": 0.6 if rsi < 40 else (-0.6 if rsi > 60 else 0)
        }

        # 5. Technical
        strategies["Technical"] = {
            "name": "الزخم الفني (RSI / EMAs)",
            "status": f"RSI: {rsi:.1f} | الاتجاه: {'صاعد' if last['EMA_50'] > last['EMA_200'] else 'هابط'}",
            "score": 1.0 if last["EMA_50"] > last["EMA_200"] and rsi < 70 else -1.0 if last["EMA_50"] < last["EMA_200"] else 0
        }

        # حساب المجموع الكلي
        total_score = sum([s["score"] for s in strategies.values()])
        
        # إشارة نهائية حازمة
        if total_score >= 2.0:
            action = "BUY"
            title = "إشارة شراء مؤسسية (تأكيد متعدد)"
        elif total_score <= -2.0:
            action = "SELL"
            title = "إشارة بيع مؤسسية (تأكيد متعدد)"
        else:
            action = "WAIT"
            title = "حالة ترقب (السوق غير واضح)"

        # --- إدارة المخاطر وحساب حجم اللوت ---
        entry = price
        sl_distance = 1.5 * atr
        if action == "BUY":
            sl = entry - sl_distance
            tp1 = entry + (2.0 * atr)
            risk_amount = self.account_balance * self.risk_per_trade
            position_size = risk_amount / sl_distance if sl_distance > 0 else 0
        elif action == "SELL":
            sl = entry + sl_distance
            tp1 = entry - (2.0 * atr)
            risk_amount = self.account_balance * self.risk_per_trade
            position_size = risk_amount / sl_distance if sl_distance > 0 else 0
        else:
            sl, tp1, position_size = 0, 0, 0

        # إعداد الشموع للشارت
        candles = []
        for idx, row in self.df.tail(120).iterrows():
            candles.append({
                "time": int(idx.timestamp()),
                "open": float(row["Open"]), "high": float(row["High"]),
                "low": float(row["Low"]), "close": float(row["Close"]),
            })

        return {
            "symbol": self.symbol,
            "current_price": round(price, 2),
            "action": action,
            "title": title,
            "position_size": round(position_size, 4) if action != "WAIT" else 0,
            "levels": {"entry": round(entry, 2) if action != "WAIT" else 0, "sl": round(sl, 2) if action != "WAIT" else 0, "tp1": round(tp1, 2) if action != "WAIT" else 0},
            "strategies": list(strategies.values()),
            "candles": candles,
        }

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>Institutional AI Engine v8</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: system-ui, sans-serif; background-color: #000000; color: #ffffff; height: 100vh; overflow: hidden; }
            .header { height: 55px; background: #050505; border-bottom: 1px solid #141414; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }
            .brand { font-size: 14px; font-weight: 700; color: #e5e5e5; }
            .menu { display: flex; gap: 8px; }
            .m-btn { background: #0a0a0a; border: 1px solid #222; color: #888; padding: 6px 14px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; }
            .m-btn.active { background: #222; color: #fff; border-color: #444; }
            .layout { display: flex; height: calc(100vh - 55px); }
            .panel { width: 360px; background: #030303; border-right: 1px solid #121212; padding: 15px; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; }
            .box { background: #080808; border: 1px solid #161616; padding: 12px; border-radius: 6px; }
            .badge-buy { background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 7px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 13px; }
            .badge-sell { background: rgba(248, 113, 113, 0.1); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3); padding: 7px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 13px; }
            .badge-wait { background: rgba(234, 179, 8, 0.1); color: #eab308; border: 1px solid rgba(234, 179, 8, 0.3); padding: 7px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 13px; }
            .row { display: flex; justify-content: space-between; font-size: 11px; margin-top: 5px; padding-bottom: 3px; border-bottom: 1px solid #111; }
            .lbl { color: #666; }
            .val { font-family: monospace; font-weight: 600; }
            .strat-item { font-size: 11px; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #111; }
            .strat-title { color: #aaa; font-weight: bold; }
            .strat-desc { color: #666; margin-top: 2px; }
            .chart-wrap { flex: 1; background: #000000; position: relative; }
            #chart { width: 100%; height: 100%; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="brand">REAL-TIME INSTITUTIONAL ENGINE v8 (NO REPAINTING)</div>
            <div class="menu">
                <button class="m-btn active" id="btn-GC=F" onclick="switchSymbol('GC=F')">GOLD</button>
                <button class="m-btn" id="btn-CL=F" onclick="switchSymbol('CL=F')">OIL</button>
                <button class="m-btn" id="btn-BTC-USD" onclick="switchSymbol('BTC-USD')">BITCOIN</button>
            </div>
        </div>
        <div class="layout">
            <div class="panel">
                <div class="box">
                    <div style="font-size:10px; color:#666; margin-bottom:4px;">حالة قرار الذكاء الاصطناعي</div>
                    <div id="signal-badge" class="badge-wait">جاري الاتصال...</div>
                    <div style="font-size:11px; color:#888; margin-top:6px; text-align:center;">حجم المركز المقترح (Lots): <span id="lot-size" style="color:#38bdf8; font-weight:bold;">0.00</span></div>
                </div>

                <div class="box">
                    <div style="font-size:10px; color:#666; margin-bottom:6px;">مستويات التنفيذ</div>
                    <div class="row"><span class="lbl">السعر الحي</span><span id="p-live" class="val" style="color:#facc15;">0.00</span></div>
                    <div class="row"><span class="lbl">منطقة الدخول</span><span id="p-entry" class="val" style="color:#38bdf8;">0.00</span></div>
                    <div class="row"><span class="lbl">وقف الخسارة</span><span id="p-sl" class="val" style="color:#f87171;">0.00</span></div>
                    <div class="row"><span class="lbl">الهدف</span><span id="p-tp1" class="val" style="color:#4ade80;">0.00</span></div>
                </div>

                <div class="box" style="flex:1;">
                    <div style="font-size:10px; color:#666; margin-bottom:6px;">التحليل التفصيلي (شمعة مغلقة)</div>
                    <div id="strategies-container"></div>
                </div>
            </div>
            <div class="chart-wrap">
                <div id="chart"></div>
            </div>
        </div>
        <script>
            let chart, series, activeLines = [];
            let ws = null;

            function initChart() {
                chart = LightweightCharts.createChart(document.getElementById('chart'), {
                    layout: { background: { type: 'solid', color: '#000000' }, textColor: '#666' },
                    grid: { vertLines: { color: '#0a0a0a' }, horzLines: { color: '#0a0a0a' } },
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

            function connectWS(symbol) {
                if (ws) ws.close();
                let proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                ws = new WebSocket(proto + window.location.host + '/ws/' + symbol);

                ws.onmessage = function(event) {
                    let data = JSON.parse(event.data);
                    if(data.error) return;
                    
                    series.setData(data.candles);
                    clearLines();

                    const badge = document.getElementById('signal-badge');
                    badge.innerText = data.title;
                    if(data.action === 'BUY') badge.className = 'badge-buy';
                    else if(data.action === 'SELL') badge.className = 'badge-sell';
                    else badge.className = 'badge-wait';

                    document.getElementById('lot-size').innerText = data.position_size;
                    document.getElementById('p-live').innerText = data.current_price;
                    document.getElementById('p-entry').innerText = data.levels.entry;
                    document.getElementById('p-sl').innerText = data.levels.sl;
                    document.getElementById('p-tp1').innerText = data.levels.tp1;

                    let stratHtml = '';
                    data.strategies.forEach(s => {
                        let color = s.score > 0 ? '#4ade80' : (s.score < 0 ? '#f87171' : '#facc15');
                        stratHtml += `
                            <div class="strat-item">
                                <div class="strat-title">${s.name}</div>
                                <div class="strat-desc" style="color: ${color};">${s.status}</div>
                            </div>
                        `;
                    });
                    document.getElementById('strategies-container').innerHTML = stratHtml;

                    if (data.action !== 'WAIT') {
                        activeLines.push(series.createPriceLine({ price: data.levels.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' }));
                        activeLines.push(series.createPriceLine({ price: data.levels.sl, color: '#ef4444', lineWidth: 2, title: 'SL' }));
                        activeLines.push(series.createPriceLine({ price: data.levels.tp1, color: '#22c55e', lineWidth: 2, title: 'TP' }));
                    }
                };
            }

            function switchSymbol(symbol) {
                document.querySelectorAll('.m-btn').forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + symbol).classList.add('active');
                connectWS(symbol);
            }

            window.onload = () => {
                initChart();
                connectWS('GC=F');
            };
        </script>
    </body>
    </html>
    """

@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    await websocket.accept()
    # تم تمرير رصيد 20 دولار كمثال
    engine = AdvancedInstitutionalEngine(symbol=symbol, period="180d", interval="1h", account_balance=20.0)
    try:
        while True:
            data = engine.analyze_market()
            if "error" in data:
                await websocket.send_text(json.dumps(data))
            else:
                await websocket.send_text(json.dumps(data))
            # تحديث كل 5 ثواني بدلاً من ثانية لتخفيف الضغط على yfinance وتجنب الحظر
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
