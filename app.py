from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import asyncio
import json
import httpx
import yfinance as yf
from datetime import datetime, timedelta
import time

app = FastAPI(title="Super Signal Engine", version="22.0")

class SignalEngine:
    def __init__(self, symbol, balance=30.0, risk_usd=3.0):
        self.symbol = symbol
        self.balance = balance
        self.risk_usd = risk_usd
        self.df = pd.DataFrame()
        self.source = "Unknown"
        self.last_fetch_time = 0

    async def fetch_data(self):
        # منع جلب البيانات بشكل متكرر جداً
        if time.time() - self.last_fetch_time < 10:
            return
        
        self.last_fetch_time = time.time()

        # 1. البيتكوين والذهب عبر OKX
        if self.symbol in ["BTCUSDT", "XAUUSD"]:
            okx_symbol = "BTC-USDT" if self.symbol == "BTCUSDT" else "PAXG-USDT"
            url = f"https://www.okx.com/api/v5/market/candles?instId={okx_symbol}&bar=15m&limit=300"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.get(url)
                    data = res.json()
                    if data.get("code") == "0":
                        klines = data["data"]
                        klines.reverse()
                        df = pd.DataFrame(klines).iloc[:, :6]
                        df.columns = ['time', 'Open', 'High', 'Low', 'Close', 'Volume']
                        df['time'] = pd.to_datetime(df['time'].astype(float), unit='ms')
                        df.set_index('time', inplace=True)
                        self.df = df.astype(float)
                        self.source = f"OKX ({okx_symbol})"
                        return
            except Exception as e:
                print(f"OKX Error: {e}")

        # 2. النفط عبر Yahoo Finance (مع محاولة إعادة المحاولة)
        elif self.symbol == "WTIUSD":
            for attempt in range(2):
                try:
                    ticker = yf.Ticker("CL=F")
                    hist = ticker.history(period="5d", interval="15m")
                    if not hist.empty:
                        self.df = hist[['Open', 'High', 'Low', 'Close', 'Volume']]
                        self.source = "Yahoo Finance (Oil)"
                        return
                except Exception as e:
                    print(f"Yahoo Error (attempt {attempt+1}): {e}")
                    await asyncio.sleep(2)

        # 3. خطة الطوارئ (محاكاة)
        if self.df.empty or len(self.df) < 200:
            dates = [datetime.now() - timedelta(minutes=15*i) for i in range(300)]
            dates.reverse()
            base_price = 60000 if "BTC" in self.symbol else (2400 if "XAU" in self.symbol else 80)
            prices = [base_price + np.random.uniform(-base_price*0.01, base_price*0.01) for _ in range(300)]
            df = pd.DataFrame({
                'Open': prices, 'High': [p + np.random.uniform(10, 50) for p in prices],
                'Low': [p - np.random.uniform(10, 50) for p in prices],
                'Close': [p + np.random.uniform(-20, 20) for p in prices],
                'Volume': [np.random.uniform(100, 1000) for _ in range(300)]
            }, index=dates)
            self.df = df
            self.source = "Simulation (Fallback)"

    def analyze(self):
        if len(self.df) < 200:
            return {"status": "loading", "message": "جاري جمع البيانات..."}
        
        df = self.df.copy()
        
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

        df["Swing_High"] = df["High"] == df["High"].rolling(5).max()
        df["Swing_Low"] = df["Low"] == df["Low"].rolling(5).min()
        last_swing_high = df[df["Swing_High"]]["High"].iloc[-1] if not df[df["Swing_High"]].empty else 0
        last_swing_low = df[df["Swing_Low"]]["Low"].iloc[-1] if not df[df["Swing_Low"]].empty else 0

        df["FVG_Bull"] = df["Low"] > df["High"].shift(2)
        df["FVG_Bear"] = df["High"] < df["Low"].shift(2)
        df["OB_Bull"] = (df["Close"].shift(1) < df["Open"].shift(1)) & (df["Close"] > df["High"].shift(1))
        df["OB_Bear"] = (df["Close"].shift(1) > df["Open"].shift(1)) & (df["Close"] < df["Low"].shift(1))

        last = df.iloc[-2]
        price = df.iloc[-1]["Close"]
        atr = last["ATR"]

        strategies = {}

        if price > last_swing_high:
            strategies["SMC"] = {"name": "SMC (كسر هيكل صاعد)", "status": "اختراق قمة سابقة (BOS)", "score": 2.0}
        elif price < last_swing_low:
            strategies["SMC"] = {"name": "SMC (كسر هيكل هابط)", "status": "اختراق قاع سابق (BOS)", "score": -2.0}
        else:
            strategies["SMC"] = {"name": "SMC", "status": "داخل نطاق السيولة", "score": 0}

        if last["FVG_Bull"] or last["OB_Bull"]:
            strategies["ICT"] = {"name": "ICT (فجوة/بلوك)", "status": "فجوة أو بلوك أوامر شرائي", "score": 1.5}
        elif last["FVG_Bear"] or last["OB_Bear"]:
            strategies["ICT"] = {"name": "ICT (فجوة/بلوك)", "status": "فجوة أو بلوك أوامر بيعي", "score": -1.5}
        else:
            strategies["ICT"] = {"name": "ICT", "status": "لا توجد فجوات نشطة", "score": 0}

        if last["EMA_21"] > last["EMA_200"] and price > last["EMA_50"]:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة دافعة صاعدة (3/5)", "score": 1.0}
        elif last["EMA_21"] < last["EMA_200"] and price < last["EMA_50"]:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة دافعة هابطة (3/5)", "score": -1.0}
        else:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة تصحيحية", "score": 0}

        if last["RSI"] < 35:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"تشبع بيعي ({last['RSI']:.1f})", "score": 1.0}
        elif last["RSI"] > 65:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"تشبع شرائي ({last['RSI']:.1f})", "score": -1.0}
        else:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"محايد ({last['RSI']:.1f})", "score": 0}

        total_score = sum(s["score"] for s in strategies.values())

        action = "WAIT"
        if total_score >= 4.0: action = "BUY"
        elif total_score <= -4.0: action = "SELL"

        sl_dist = 1.5 * atr
        position_size = 0
        warning_msg = ""
        
        if action != "WAIT" and sl_dist > 0:
            entry = price
            sl = entry - sl_dist if action == "BUY" else entry + sl_dist
            tp = entry + (3.0 * atr) if action == "BUY" else entry - (3.0 * atr)
            position_size = self.risk_usd / sl_dist
            if position_size < 0.0001:
                warning_msg = "⚠️ حجم اللوت صغير جداً! قد يرفضه البروكر."
            entry, sl, tp = round(entry, 2), round(sl, 2), round(tp, 2)
        else:
            entry, sl, tp = 0, 0, 0

        candles = [{"time": int(idx.timestamp()), "open": float(row["Open"]), "high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"])} for idx, row in df.tail(150).iterrows()]

        return {
            "status": "ok", "symbol": self.symbol, "current_price": round(price, 2), "action": action,
            "levels": {"entry": entry, "sl": sl, "tp": tp},
            "position_size": round(position_size, 4), "risk_usd": self.risk_usd,
            "warning": warning_msg, "strategies": list(strategies.values()), "candles": candles,
            "source": self.source
        }

# --- نقطة نهاية للحفاظ على نشاط التطبيق (Keep-Alive) ---
@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    await websocket.accept()
    engine = SignalEngine(symbol=symbol)
    
    # بدء مهمة جلب البيانات في الخلفية
    asyncio.create_task(engine.fetch_data())
    
    try:
        while True:
            # محاولة جلب البيانات إذا لم تكن جاهزة بعد
            if len(engine.df) < 200:
                await engine.fetch_data()
            
            result = engine.analyze()
            await websocket.send_text(json.dumps(result))
            await asyncio.sleep(3) # تحديث كل 3 ثوانٍ
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket Error: {e}")

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Super Signal Engine</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: system-ui, sans-serif; background-color: #000; color: #fff; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
            .header { height: 50px; background: #050505; border-bottom: 1px solid #141414; display: flex; align-items: center; justify-content: space-between; padding: 0 15px; }
            .header .brand { font-size: 13px; font-weight: bold; }
            .header .menu { display: flex; gap: 6px; }
            .m-btn { background: #222; color: #fff; border: 1px solid #444; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; }
            .m-btn.active { background: #444; font-weight: bold; }
            .layout { display: flex; flex: 1; overflow: hidden; }
            .panel { width: 320px; background: #030303; border-left: 1px solid #121212; padding: 12px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
            .box { background: #080808; border: 1px solid #161616; padding: 10px; border-radius: 5px; }
            .badge-buy { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid #22c55e; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 14px; }
            .badge-sell { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid #ef4444; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 14px; }
            .badge-wait { background: rgba(234, 179, 8, 0.1); color: #eab308; border: 1px solid #eab308; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 14px; }
            .row { display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px; padding-bottom: 3px; border-bottom: 1px solid #111; }
            .val { font-family: monospace; font-weight: bold; }
            .strat-item { font-size: 11px; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #111; }
            .warning-box { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; padding: 6px; border-radius: 4px; font-size: 10px; text-align: center; display: none; margin-top: 4px; }
            .source-tag { font-size: 9px; color: #666; text-align: center; margin-top: 4px; }
            .chart-wrap { flex: 1; background: #000; position: relative; }
            #chart { width: 100%; height: 100%; }
            @media (max-width: 768px) {
                .layout { flex-direction: column; }
                .panel { width: 100%; border-left: none; border-bottom: 1px solid #121212; height: 50%; }
                .chart-wrap { height: 50%; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="brand">SIGNAL ENGINE (Loss: $3)</div>
            <div class="menu">
                <button class="m-btn" id="btn-XAUUSD" onclick="switchSymbol('XAUUSD')">GOLD</button>
                <button class="m-btn" id="btn-WTIUSD" onclick="switchSymbol('WTIUSD')">OIL</button>
                <button class="m-btn active" id="btn-BTCUSDT" onclick="switchSymbol('BTCUSDT')">BITCOIN</button>
            </div>
        </div>
        <div class="layout">
            <div class="panel">
                <div class="box" style="text-align:center;">
                    <div style="font-size:10px; color:#888; margin-bottom:4px;">إشارة التداول (15 دقيقة)</div>
                    <div id="signal-badge" class="badge-wait">جاري التحميل...</div>
                    <div style="margin-top:8px; font-size:11px; color:#aaa;">
                        حجم المركز: <strong id="pos-size" style="color:#38bdf8; font-size:14px;">0.00</strong><br>
                        <span style="font-size:9px;">(مخاطرة ثابتة: $3.00 خسارة قصوى)</span>
                    </div>
                    <div id="warn-box" class="warning-box"></div>
                    <div id="source-tag" class="source-tag"></div>
                </div>
                <div class="box">
                    <div style="font-size:10px; color:#888; margin-bottom:4px;">مستويات الدخول</div>
                    <div class="row"><span class="lbl">السعر</span><span id="p-live" class="val" style="color:#facc15;">0.00</span></div>
                    <div class="row"><span class="lbl">الدخول</span><span id="p-entry" class="val" style="color:#38bdf8;">0.00</span></div>
                    <div class="row"><span class="lbl">وقف الخسارة</span><span id="p-sl" class="val" style="color:#ef4444;">0.00</span></div>
                    <div class="row"><span class="lbl">الهدف</span><span id="p-tp" class="val" style="color:#4ade80;">0.00</span></div>
                </div>
                <div class="box" style="flex:1;">
                    <div style="font-size:10px; color:#888; margin-bottom:4px;">تلاقي الاستراتيجيات</div>
                    <div id="strategies-container"></div>
                </div>
            </div>
            <div class="chart-wrap"><div id="chart"></div></div>
        </div>
        <script>
            let chart, series, activeLines = [];
            let ws = null;
            let currentSymbol = 'BTCUSDT';

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
                if (ws) { ws.onclose = null; ws.close(); }
                currentSymbol = symbol;
                
                document.querySelectorAll('.m-btn').forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + symbol).classList.add('active');
                
                document.getElementById('signal-badge').innerText = "جاري جلب البيانات...";
                document.getElementById('signal-badge').className = 'badge-wait';
                
                let proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                ws = new WebSocket(proto + window.location.host + '/ws/' + symbol);

                ws.onmessage = (event) => {
                    let data = JSON.parse(event.data);
                    if (data.status === 'loading') {
                        document.getElementById('signal-badge').innerText = data.message;
                        return;
                    }
                    series.setData(data.candles);
                    clearLines();
                    
                    const badge = document.getElementById('signal-badge');
                    badge.innerText = data.action === 'BUY' ? 'شراء قوي' : data.action === 'SELL' ? 'بيع قوي' : 'ترقب';
                    badge.className = data.action === 'BUY' ? 'badge-buy' : data.action === 'SELL' ? 'badge-sell' : 'badge-wait';
                    
                    document.getElementById('pos-size').innerText = data.position_size;
                    document.getElementById('p-live').innerText = data.current_price;
                    document.getElementById('p-entry').innerText = data.levels.entry;
                    document.getElementById('p-sl').innerText = data.levels.sl;
                    document.getElementById('p-tp').innerText = data.levels.tp;
                    document.getElementById('source-tag').innerText = "المصدر: " + data.source;
                    
                    const warnBox = document.getElementById('warn-box');
                    warnBox.style.display = data.warning ? 'block' : 'none';
                    if (data.warning) warnBox.innerText = data.warning;
                    
                    let stratHtml = '';
                    data.strategies.forEach(s => {
                        let color = s.score > 0 ? '#4ade80' : (s.score < 0 ? '#f87171' : '#888');
                        stratHtml += `<div class="strat-item"><strong>${s.name}</strong><br><span style="color:${color}">${s.status} (${s.score > 0 ? '+' : ''}${s.score})</span></div>`;
                    });
                    document.getElementById('strategies-container').innerHTML = stratHtml;
                    
                    if (data.action !== 'WAIT') {
                        activeLines.push(series.createPriceLine({ price: data.levels.entry, color: '#38bdf8', lineWidth: 2, title: 'ENTRY' }));
                        activeLines.push(series.createPriceLine({ price: data.levels.sl, color: '#ef4444', lineWidth: 2, title: 'SL' }));
                        activeLines.push(series.createPriceLine({ price: data.levels.tp, color: '#22c55e', lineWidth: 2, title: 'TP' }));
                    }
                };
                ws.onclose = () => { setTimeout(() => switchSymbol(currentSymbol), 3000); };
            }

            window.onload = () => { initChart(); switchSymbol('BTCUSDT'); };
        </script>
    </body>
    </html>
    """
