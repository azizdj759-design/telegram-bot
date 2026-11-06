from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import asyncio
import json
import websockets
from datetime import datetime

app = FastAPI(title="Live Institutional Signal Engine", version="10.0")

class LiveSignalEngine:
    def __init__(self, symbol="BTCUSDT", account_balance=1000.0, risk_pct=0.01):
        self.symbol = symbol
        self.balance = account_balance  # رصيد حسابك (يمكنك تعديله هنا)
        self.risk_pct = risk_pct        # نسبة المخاطرة (1%)
        self.df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        self.latest_news = "لا توجد أخبار جارية" # مكان مخصص لربط الـ API لاحقاً
        
    def update_data(self, kline):
        # تحويل بيانات Binance اللحظية إلى DataFrame
        new_row = pd.DataFrame([{
            "Open": float(kline['o']), "High": float(kline['h']),
            "Low": float(kline['l']), "Close": float(kline['c']), "Volume": float(kline['v'])
        }], index=[pd.to_datetime(kline['t'], unit='ms')])
        
        # تحديث الشمعة الحالية أو إضافة جديدة
        if not self.df.empty and self.df.index[-1] == new_row.index[0]:
            self.df.iloc[-1] = new_row.iloc[0]
        else:
            self.df = pd.concat([self.df, new_row])

        # الحفاظ على حجم البيانات لتجنب استهلاك الذاكرة
        if len(self.df) > 500: 
            self.df = self.df.tail(500)

    def calculate_indicators(self):
        if len(self.df) < 200: 
            return False
        
        # 1. المؤشرات الفنية الأساسية
        self.df["EMA_21"] = self.df["Close"].ewm(span=21, adjust=False).mean()
        self.df["EMA_50"] = self.df["Close"].ewm(span=50, adjust=False).mean()
        self.df["EMA_200"] = self.df["Close"].ewm(span=200, adjust=False).mean()
        
        delta = self.df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        self.df["RSI"] = 100 - (100 / (1 + (gain / loss)))
        
        high_low = self.df["High"] - self.df["Low"]
        high_close = np.abs(self.df["High"] - self.df["Close"].shift())
        low_close = np.abs(self.df["Low"] - self.df["Close"].shift())
        self.df["ATR"] = (pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)).rolling(14).mean()

        # 2. مفاهيم SMC (Swing Highs/Lows)
        self.df["Swing_High"] = self.df["High"] == self.df["High"].rolling(5).max()
        self.df["Swing_Low"] = self.df["Low"] == self.df["Low"].rolling(5).min()
        
        # 3. مفاهيم ICT (Fair Value Gap)
        self.df["FVG_Bull"] = self.df["Low"] > self.df["High"].shift(2)
        self.df["FVG_Bear"] = self.df["High"] < self.df["Low"].shift(2)
        
        return True

    def generate_signal(self):
        if not self.calculate_indicators(): 
            return {"status": "loading", "message": "جاري جمع البيانات اللازمة للتحليل (200 شمعة)..."}
        
        # نستخدم الشمعة المغلقة الأخيرة للتحليل (لمنع التزييف)
        last_closed = self.df.iloc[-2] 
        # السعر اللحظي للعرض فقط
        live_price = self.df.iloc[-1]["Close"] 
        atr = last_closed["ATR"]

        strategies = {}
        
        # --- 1. استراتيجية SMC (Smart Money Concepts) ---
        smc_score = 0
        smc_status = "منطقة متوازنة"
        if last_closed["Swing_High"]: 
            smc_score = -1.5; smc_status = "قمم سيولة بيعية (اختراق هيكلي)"
        elif last_closed["Swing_Low"]: 
            smc_score = 1.5; smc_status = "قيعان سيولة شرائية (اختراق هيكلي)"
        
        if live_price > last_closed["EMA_50"]: 
            smc_score += 0.5
        strategies["SMC"] = {"name": "الأموال الذكية (SMC)", "status": smc_status, "score": smc_score}

        # --- 2. استراتيجية ICT (Fair Value Gaps) ---
        ict_score = 0
        ict_status = "لا توجد فجوات سعرية"
        if last_closed["FVG_Bull"]: 
            ict_score = 2.0; ict_status = "فجوة سعرية صاعدة (Bullish FVG)"
        elif last_closed["FVG_Bear"]: 
            ict_score = -2.0; ict_status = "فجوة سعرية هابطة (Bearish FVG)"
        strategies["ICT"] = {"name": "فجوات السعر (ICT)", "status": ict_status, "score": ict_score}

        # --- 3. موجات إليوت (Elliott Wave) ---
        ew_score = 0
        ew_status = "موجة تصحيحية"
        if last_closed["EMA_21"] > last_closed["EMA_200"] and live_price > last_closed["EMA_50"]:
            ew_score = 1.0; ew_status = "موجة دافعة صاعدة (Wave 3/5)"
        elif last_closed["EMA_21"] < last_closed["EMA_200"] and live_price < last_closed["EMA_50"]:
            ew_score = -1.0; ew_status = "موجة دافعة هابطة (Wave 3/5)"
        strategies["Elliott"] = {"name": "موجات إليوت", "status": ew_status, "score": ew_score}

        # --- 4. التحليل الفني ---
        tech_score = 0
        tech_status = f"RSI: {last_closed['RSI']:.1f}"
        if last_closed["RSI"] < 30: 
            tech_score = 1.0; tech_status += " (تشبع بيعي)"
        elif last_closed["RSI"] > 70: 
            tech_score = -1.0; tech_status += " (تشبع شرائي)"
        elif last_closed["EMA_50"] > last_closed["EMA_200"]: 
            tech_score = 0.5; tech_status += " (اتجاه صاعد)"
        else: 
            tech_score = -0.5; tech_status += " (اتجاه هابط)"
        strategies["Technical"] = {"name": "التحليل الفني (RSI/EMA)", "status": tech_status, "score": tech_score}

        # --- اتخاذ القرار ---
        total_score = sum([s["score"] for s in strategies.values()])
        action = "WAIT"
        if total_score >= 2.0: action = "BUY"
        elif total_score <= -2.0: action = "SELL"

        # --- إدارة المخاطر وحساب اللوت ---
        risk_amount = self.balance * self.risk_pct
        sl_dist = 1.5 * atr
        position_size = 0
        entry, sl, tp = 0, 0, 0
        
        if action != "WAIT" and sl_dist > 0:
            entry = live_price
            if action == "BUY":
                sl = entry - sl_dist
                tp = entry + (2.5 * atr)
            else:
                sl = entry + sl_dist
                tp = entry - (2.5 * atr)
            position_size = risk_amount / sl_dist

        # إعداد الشموع للشارت
        candles = [{"time": int(idx.timestamp()), "open": float(row["Open"]), "high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"])} for idx, row in self.df.tail(150).iterrows()]

        return {
            "status": "ok", "symbol": self.symbol, "current_price": round(live_price, 2), "action": action,
            "levels": {"entry": round(entry, 2), "sl": round(sl, 2), "tp": round(tp, 2)},
            "position_size": round(position_size, 4), "risk_amount": round(risk_amount, 2),
            "strategies": list(strategies.values()), "candles": candles, "news": self.latest_news
        }

# --- خادم WebSocket المتصل ببيانات Binance اللحظية ---
@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    await websocket.accept()
    # يمكنك تغيير الرصيد الافتراضي (1000$) إلى 20$ إذا أردت
    engine = LiveSignalEngine(symbol=symbol, account_balance=1000.0, risk_pct=0.01)
    
    binance_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_1m"
    
    try:
        async with websockets.connect(binance_url) as binance_ws:
            while True:
                msg = await binance_ws.recv()
                data = json.loads(msg)
                
                # تحديث المحرك بالشمعة اللحظية
                engine.update_data(data['k'])
                
                # إرسال التحليل للواجهة
                signal_data = engine.generate_signal()
                await websocket.send_text(json.dumps(signal_data))
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Error connecting to Binance: {e}")

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>Institutional Signal Engine</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: system-ui, sans-serif; background-color: #000000; color: #ffffff; height: 100vh; overflow: hidden; }
            .header { height: 55px; background: #050505; border-bottom: 1px solid #141414; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }
            .layout { display: flex; height: calc(100vh - 55px); }
            .panel { width: 380px; background: #030303; border-right: 1px solid #121212; padding: 15px; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; }
            .box { background: #080808; border: 1px solid #161616; padding: 12px; border-radius: 6px; }
            .badge-buy { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid #22c55e; padding: 10px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 16px; }
            .badge-sell { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid #ef4444; padding: 10px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 16px; }
            .badge-wait { background: rgba(234, 179, 8, 0.1); color: #eab308; border: 1px solid #eab308; padding: 10px; border-radius: 4px; text-align: center; font-weight: 700; font-size: 16px; }
            .row { display: flex; justify-content: space-between; font-size: 13px; margin-top: 8px; padding-bottom: 4px; border-bottom: 1px solid #111; }
            .val { font-family: monospace; font-weight: bold; font-size: 14px; }
            .strat-item { font-size: 12px; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #111; }
            .news-banner { background: #1e1e1e; border-right: 4px solid #f59e0b; padding: 10px; font-size: 12px; margin-bottom: 10px; }
            .chart-wrap { flex: 1; background: #000000; }
            .nav-btn { background:#222; color:#fff; border:1px solid #444; padding:6px 12px; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold; }
            .nav-btn:hover { background:#333; }
        </style>
    </head>
    <body>
        <div class="header">
            <div style="font-size: 14px; font-weight: bold;">LIVE SIGNAL ENGINE v10 (BINANCE)</div>
            <div style="display:flex; gap: 8px;">
                <button class="nav-btn" onclick="switchSymbol('BTCUSDT')">BTC/USDT</button>
                <button class="nav-btn" onclick="switchSymbol('ETHUSDT')">ETH/USDT</button>
                <button class="nav-btn" onclick="switchSymbol('SOLUSDT')">SOL/USDT</button>
            </div>
        </div>
        <div class="layout">
            <div class="panel">
                <div id="news-banner" class="news-banner">📰 الأخبار: جاري التحميل...</div>
                
                <div class="box" style="text-align:center;">
                    <div style="font-size:11px; color:#888; margin-bottom:5px;">إشارة التداول (شمعة مغلقة)</div>
                    <div id="signal-badge" class="badge-wait">جاري التحليل...</div>
                    <div style="margin-top:10px; font-size:12px; color:#aaa;">
                        حجم المركز المقترح: <strong id="pos-size" style="color:#38bdf8; font-size:16px;">0.00</strong> وحدة<br>
                        <span style="font-size:10px;">(مخاطرة 1% من الرصيد)</span>
                    </div>
                </div>

                <div class="box">
                    <div style="font-size:11px; color:#888; margin-bottom:6px;">مستويات الدخول (للدخول اليدوي)</div>
                    <div class="row"><span class="lbl">السعر الحالي</span><span id="p-live" class="val" style="color:#facc15;">0.00</span></div>
                    <div class="row"><span class="lbl">الدخول (Entry)</span><span id="p-entry" class="val" style="color:#38bdf8;">0.00</span></div>
                    <div class="row"><span class="lbl">وقف الخسارة (SL)</span><span id="p-sl" class="val" style="color:#ef4444;">0.00</span></div>
                    <div class="row"><span class="lbl">الهدف (TP)</span><span id="p-tp" class="val" style="color:#4ade80;">0.00</span></div>
                </div>

                <div class="box" style="flex:1;">
                    <div style="font-size:11px; color:#888; margin-bottom:6px;">تفصيل الاستراتيجيات</div>
                    <div id="strategies-container"></div>
                </div>
            </div>
            <div class="chart-wrap"><div id="chart" style="height:100%;"></div></div>
        </div>

        <script>
            let chart, series, activeLines = [];
            let ws = null;

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

            function switchSymbol(symbol) {
                if (ws) ws.close();
                let proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                ws = new WebSocket(proto + window.location.host + '/ws/' + symbol);

                ws.onmessage = function(event) {
                    let data = JSON.parse(event.data);
                    if (data.status === 'loading') {
                        document.getElementById('signal-badge').innerText = data.message;
                        return;
                    }

                    series.setData(data.candles);
                    clearLines();

                    const badge = document.getElementById('signal-badge');
                    badge.innerText = data.action === 'BUY' ? 'BUY (شراء)' : data.action === 'SELL' ? 'SELL (بيع)' : 'WAIT (ترقب)';
                    badge.className = data.action === 'BUY' ? 'badge-buy' : data.action === 'SELL' ? 'badge-sell' : 'badge-wait';

                    document.getElementById('pos-size').innerText = data.position_size;
                    document.getElementById('p-live').innerText = data.current_price;
                    document.getElementById('p-entry').innerText = data.levels.entry;
                    document.getElementById('p-sl').innerText = data.levels.sl;
                    document.getElementById('p-tp').innerText = data.levels.tp;
                    document.getElementById('news-banner').innerHTML = "📰 الأخبار: " + data.news;

                    let stratHtml = '';
                    data.strategies.forEach(s => {
                        let color = s.score > 0 ? '#4ade80' : (s.score < 0 ? '#f87171' : '#facc15');
                        stratHtml += `<div class="strat-item"><strong>${s.name}</strong><br><span style="color:${color}">${s.status} (${s.score > 0 ? '+' : ''}${s.score})</span></div>`;
                    });
                    document.getElementById('strategies-container').innerHTML = stratHtml;

                    if (data.action !== 'WAIT') {
                        activeLines.push(series.createPriceLine({ price: data.levels.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' }));
                        activeLines.push(series.createPriceLine({ price: data.levels.sl, color: '#ef4444', lineWidth: 2, title: 'SL' }));
                        activeLines.push(series.createPriceLine({ price: data.levels.tp, color: '#22c55e', lineWidth: 2, title: 'TP' }));
                    }
                };
            }
            window.onload = () => { initChart(); switchSymbol('BTCUSDT'); };
        </script>
    </body>
    </html>
    """
