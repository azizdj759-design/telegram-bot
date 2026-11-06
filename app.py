from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import numpy as np
import pandas as pd
import asyncio
import json
import websockets
import httpx

app = FastAPI(title="Super Institutional Signal Engine", version="15.0")

class SuperSignalEngine:
    def __init__(self, symbol="BTC_USDT", account_balance=30.0, risk_pct=0.01):
        # WhiteBIT تستخدم صيغة BTC_USDT بدلاً من BTCUSDT
        self.symbol = symbol
        self.balance = account_balance
        self.risk_pct = risk_pct
        self.df = pd.DataFrame()
        
    async def fetch_historical_data(self):
        # جلب البيانات التاريخية من WhiteBIT (لا يوجد حظر لخوادم Render)
        url = f"https://whitebit.com/api/v4/public/kline?market={self.symbol}&interval=15m&limit=300"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                # WhiteBIT ترجع البيانات كمصفوفة: [timestamp, open, close, high, low, volume]
                df = pd.DataFrame(data, columns=['time', 'Open', 'Close', 'High', 'Low', 'Volume'])
                df['time'] = pd.to_datetime(df['time'], unit='s')
                df.set_index('time', inplace=True)
                # إعادة ترتيب الأعمدة لتطابق التنسيق المطلوب
                self.df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
                
            except Exception as e:
                raise Exception(f"فشل جلب البيانات من WhiteBIT: {e}")

    def update_live_data(self, kline_data):
        # تحديث الشمعة الحالية من البث اللحظي
        new_row = pd.DataFrame([{
            "Open": float(kline_data['open']), "High": float(kline_data['high']),
            "Low": float(kline_data['low']), "Close": float(kline_data['close']), 
            "Volume": float(kline_data['volume'])
        }], index=[pd.to_datetime(kline_data['time'], unit='s')])
        
        if not self.df.empty and self.df.index[-1] == new_row.index[0]:
            self.df.iloc[-1] = new_row.iloc[0]
        else:
            self.df = pd.concat([self.df, new_row])
        if len(self.df) > 500: 
            self.df = self.df.tail(500)

    def analyze_strategies(self):
        if len(self.df) < 200: 
            return None
        
        df = self.df.copy()
        
        # المؤشرات الفنية
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

        # SMC
        df["Swing_High"] = df["High"] == df["High"].rolling(5).max()
        df["Swing_Low"] = df["Low"] == df["Low"].rolling(5).min()
        last_swing_high = df[df["Swing_High"]]["High"].iloc[-1] if not df[df["Swing_High"]].empty else 0
        last_swing_low = df[df["Swing_Low"]]["Low"].iloc[-1] if not df[df["Swing_Low"]].empty else 0

        # ICT
        df["FVG_Bull"] = df["Low"] > df["High"].shift(2)
        df["FVG_Bear"] = df["High"] < df["Low"].shift(2)
        df["OB_Bull"] = (df["Close"].shift(1) < df["Open"].shift(1)) & (df["Close"] > df["High"].shift(1))
        df["OB_Bear"] = (df["Close"].shift(1) > df["Open"].shift(1)) & (df["Close"] < df["Low"].shift(1))

        last_closed = df.iloc[-2] # الشمعة المغلقة
        live_price = df.iloc[-1]["Close"] # السعر الحالي
        atr = last_closed["ATR"]

        strategies = {}

        # SMC
        if live_price > last_swing_high:
            strategies["SMC"] = {"name": "SMC (كسر هيكل صاعد)", "status": "اختراق قمة سابقة (BOS صاعد)", "score": 2.0}
        elif live_price < last_swing_low:
            strategies["SMC"] = {"name": "SMC (كسر هيكل هابط)", "status": "اختراق قاع سابق (BOS هابط)", "score": -2.0}
        else:
            strategies["SMC"] = {"name": "SMC", "status": "داخل نطاق السيولة", "score": 0}

        # ICT
        if last_closed["FVG_Bull"] or last_closed["OB_Bull"]:
            strategies["ICT"] = {"name": "ICT (فجوة/بلوك)", "status": "فجوة أو بلوك أوامر شرائي", "score": 1.5}
        elif last_closed["FVG_Bear"] or last_closed["OB_Bear"]:
            strategies["ICT"] = {"name": "ICT (فجوة/بلوك)", "status": "فجوة أو بلوك أوامر بيعي", "score": -1.5}
        else:
            strategies["ICT"] = {"name": "ICT", "status": "لا توجد فجوات نشطة", "score": 0}

        # Elliott
        if last_closed["EMA_21"] > last_closed["EMA_200"] and live_price > last_closed["EMA_50"]:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة دافعة صاعدة (3/5)", "score": 1.0}
        elif last_closed["EMA_21"] < last_closed["EMA_200"] and live_price < last_closed["EMA_50"]:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة دافعة هابطة (3/5)", "score": -1.0}
        else:
            strategies["Elliott"] = {"name": "إليوت", "status": "موجة تصحيحية", "score": 0}

        # Technical
        if last_closed["RSI"] < 35:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"تشبع بيعي ({last_closed['RSI']:.1f})", "score": 1.0}
        elif last_closed["RSI"] > 65:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"تشبع شرائي ({last_closed['RSI']:.1f})", "score": -1.0}
        else:
            strategies["Technical"] = {"name": "الفني (RSI)", "status": f"محايد ({last_closed['RSI']:.1f})", "score": 0}

        total_score = sum([s["score"] for s in strategies.values()])

        action = "WAIT"
        if total_score >= 4.0: action = "BUY"
        elif total_score <= -4.0: action = "SELL"

        # إدارة المخاطر
        risk_amount = self.balance * self.risk_pct
        sl_dist = 1.5 * atr
        position_size = 0
        warning_msg = ""
        
        if action != "WAIT" and sl_dist > 0:
            entry = live_price
            sl = entry - sl_dist if action == "BUY" else entry + sl_dist
            tp = entry + (3.0 * atr) if action == "BUY" else entry - (3.0 * atr)
            position_size = risk_amount / sl_dist
            if position_size < 0.0001:
                warning_msg = "⚠️ حجم اللوت صغير جداً! قد يرفضه البروكر."
            entry = round(entry, 2)
            sl = round(sl, 2)
            tp = round(tp, 2)
        else:
            entry, sl, tp = 0, 0, 0

        candles = [{"time": int(idx.timestamp()), "open": float(row["Open"]), "high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"])} for idx, row in df.tail(150).iterrows()]

        return {
            "status": "ok", "symbol": self.symbol, "current_price": round(live_price, 2), "action": action,
            "levels": {"entry": entry, "sl": sl, "tp": tp},
            "position_size": round(position_size, 6), "risk_amount": round(risk_amount, 2),
            "warning": warning_msg, "strategies": list(strategies.values()), "candles": candles
        }

@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    await websocket.accept()
    # تحويل الرمز من BTCUSDT إلى BTC_USDT
    wb_symbol = symbol.replace("USDT", "_USDT")
    engine = SuperSignalEngine(symbol=wb_symbol, account_balance=30.0, risk_pct=0.01)
    
    try:
        # 1. جلب البيانات التاريخية
        await engine.fetch_historical_data()
        initial_result = engine.analyze_strategies()
        if initial_result:
            await websocket.send_text(json.dumps(initial_result))
        
        # 2. البث اللحظي من WhiteBIT
        # WhiteBIT WebSocket: wss://api.whitebit.com/ws
        async with websockets.connect("wss://api.whitebit.com/ws") as wb_ws:
            # الاشتراك في قناة kline لفريم 15 دقيقة
            subscribe_msg = {
                "method": "kline_subscribe",
                "params": [wb_symbol, "15m"],
                "id": 1
            }
            await wb_ws.send(json.dumps(subscribe_msg))
            
            while True:
                msg = await wb_ws.recv()
                data = json.loads(msg)
                
                # التحقق من أن الرسالة هي تحديث شمعة
                if "params" in data and data.get("method") == "kline_update":
                    kline = data["params"][0]
                    engine.update_live_data(kline)
                    
                    result = engine.analyze_strategies()
                    if result:
                        await websocket.send_text(json.dumps(result))
                
    except Exception as e:
        error_msg = json.dumps({"status": "error", "message": f"خطأ: {str(e)}"})
        try:
            await websocket.send_text(error_msg)
        except:
            pass

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>Super Signal Engine</title>
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
            .warning-box { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; padding: 8px; border-radius: 4px; font-size: 11px; text-align: center; display: none; margin-top: 5px; }
            .chart-wrap { flex: 1; background: #000000; }
            .nav-btn { background:#222; color:#fff; border:1px solid #444; padding:6px 12px; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold; }
        </style>
    </head>
    <body>
        <div class="header">
            <div style="font-size: 14px; font-weight: bold;">SUPER SIGNAL ENGINE (Account: $30)</div>
            <div style="display:flex; gap: 8px;">
                <button class="nav-btn" onclick="switchSymbol('BTCUSDT')">BTC/USDT</button>
                <button class="nav-btn" onclick="switchSymbol('ETHUSDT')">ETH/USDT</button>
                <button class="nav-btn" onclick="switchSymbol('SOLUSDT')">SOL/USDT</button>
            </div>
        </div>
        <div class="layout">
            <div class="panel">
                <div class="box" style="text-align:center;">
                    <div style="font-size:11px; color:#888; margin-bottom:5px;">إشارة التداول (فريم 15 دقيقة)</div>
                    <div id="signal-badge" class="badge-wait">جاري الاتصال بالبيانات...</div>
                    
                    <div style="margin-top:10px; font-size:12px; color:#aaa;">
                        حجم المركز: <strong id="pos-size" style="color:#38bdf8; font-size:16px;">0.00</strong><br>
                        <span style="font-size:10px;">(المخاطرة: $0.30 من أصل $30)</span>
                    </div>
                    <div id="warn-box" class="warning-box"></div>
                </div>

                <div class="box">
                    <div style="font-size:11px; color:#888; margin-bottom:6px;">مستويات الدخول (انسخها للبروكر)</div>
                    <div class="row"><span class="lbl">السعر الحالي</span><span id="p-live" class="val" style="color:#facc15;">0.00</span></div>
                    <div class="row"><span class="lbl">الدخول (Entry)</span><span id="p-entry" class="val" style="color:#38bdf8;">0.00</span></div>
                    <div class="row"><span class="lbl">وقف الخسارة (SL)</span><span id="p-sl" class="val" style="color:#ef4444;">0.00</span></div>
                    <div class="row"><span class="lbl">الهدف (TP)</span><span id="p-tp" class="val" style="color:#4ade80;">0.00</span></div>
                </div>

                <div class="box" style="flex:1;">
                    <div style="font-size:11px; color:#888; margin-bottom:6px;">تلاقي الاستراتيجيات (Confluence)</div>
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
                document.getElementById('signal-badge').innerText = "جاري جلب البيانات...";
                document.getElementById('signal-badge').className = 'badge-wait';
                
                let proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                ws = new WebSocket(proto + window.location.host + '/ws/' + symbol);

                ws.onmessage = function(event) {
                    let data = JSON.parse(event.data);
                    
                    if (data.status === 'error') {
                        document.getElementById('signal-badge').innerText = data.message;
                        document.getElementById('signal-badge').className = 'badge-sell';
                        return;
                    }

                    series.setData(data.candles);
                    clearLines();

                    const badge = document.getElementById('signal-badge');
                    badge.innerText = data.action === 'BUY' ? 'STRONG BUY (شراء)' : data.action === 'SELL' ? 'STRONG SELL (بيع)' : 'WAIT (ترقب)';
                    badge.className = data.action === 'BUY' ? 'badge-buy' : data.action === 'SELL' ? 'badge-sell' : 'badge-wait';

                    document.getElementById('pos-size').innerText = data.position_size;
                    document.getElementById('p-live').innerText = data.current_price;
                    document.getElementById('p-entry').innerText = data.levels.entry;
                    document.getElementById('p-sl').innerText = data.levels.sl;
                    document.getElementById('p-tp').innerText = data.levels.tp;

                    const warnBox = document.getElementById('warn-box');
                    if (data.warning) {
                        warnBox.style.display = 'block';
                        warnBox.innerText = data.warning;
                    } else {
                        warnBox.style.display = 'none';
                    }

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
            }
            window.onload = () => { initChart(); switchSymbol('BTCUSDT'); };
        </script>
    </body>
    </html>
    """
