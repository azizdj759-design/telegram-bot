@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pro Signal Engine</title>
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: system-ui, sans-serif; background-color: #000; color: #fff; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
            .header { height: 50px; background: #050505; border-bottom: 1px solid #141414; display: flex; align-items: center; justify-content: space-between; padding: 0 15px; flex-shrink: 0; }
            .header .brand { font-size: 13px; font-weight: bold; }
            .header .menu { display: flex; gap: 6px; }
            .m-btn { background: #222; color: #fff; border: 1px solid #444; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; }
            .m-btn.active { background: #444; font-weight: bold; }
            .layout { display: flex; flex: 1; overflow: hidden; width: 100%; height: calc(100vh - 50px); }
            .panel { width: 320px; background: #030303; border-left: 1px solid #121212; padding: 12px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; flex-shrink: 0; }
            .box { background: #080808; border: 1px solid #161616; padding: 10px; border-radius: 5px; }
            .badge-buy { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid #22c55e; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 14px; }
            .badge-sell { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid #ef4444; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 14px; }
            .badge-wait { background: rgba(234, 179, 8, 0.1); color: #eab308; border: 1px solid #eab308; padding: 8px; border-radius: 4px; text-align: center; font-weight: bold; font-size: 14px; }
            .row { display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px; padding-bottom: 3px; border-bottom: 1px solid #111; }
            .val { font-family: monospace; font-weight: bold; }
            .strat-item { font-size: 11px; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #111; }
            .warning-box { background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5; padding: 6px; border-radius: 4px; font-size: 10px; text-align: center; display: none; margin-top: 4px; }
            .source-tag { font-size: 9px; color: #666; text-align: center; margin-top: 4px; }
            .chart-wrap { flex: 1; background: #000; position: relative; height: 100%; min-width: 0; }
            #chart { width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
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
                const container = document.getElementById('chart');
                chart = LightweightCharts.createChart(container, {
                    width: container.clientWidth,
                    height: container.clientHeight,
                    layout: { background: { color: '#000' }, textColor: '#666' },
                    grid: { vertLines: { color: '#0a0a0a' }, horzLines: { color: '#0a0a0a' } },
                    timeScale: { timeVisible: true }
                });
                series = chart.addCandlestickSeries({ upColor: '#22c55e', downColor: '#ef4444', borderVisible: false });
                
                window.addEventListener('resize', () => {
                    chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
                });
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
                    
                    if (data.status === 'error') {
                        document.getElementById('signal-badge').innerText = data.message;
                        document.getElementById('signal-badge').className = 'badge-sell';
                        return;
                    }
                    if (data.status === 'loading') {
                        document.getElementById('signal-badge').innerText = data.message;
                        return;
                    }
                    
                    series.setData(data.candles);
                    chart.timeScale().fitContent(); // ضبط الشارت ليظهر البيانات بوضوح
                    clearLines();
                    
                    const badge = document.getElementById('signal-badge');
                    badge.innerText = data.action === 'BUY' ? 'شراء قوي' : data.action === 'SELL' ? 'بيع قوي' : 'ترقب';
                    badge.className = data.action === 'BUY' ? 'badge-buy' : data.action === 'SELL' ? 'badge-sell' : 'badge-wait';
                    
                    document.getElementById('pos-size').innerText = data.position_size;
                    document.getElementById('p-live').innerText = data.current_price;
                    document.getElementById('p-entry').innerText = data.levels.entry;
                    document.getElementById('p-sl').innerText = data.levels.sl;
                    document.getElementById('p-tp').innerText, document.getElementById('p-tp').innerText = data.levels.tp;
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
                ws.onclose = () => { 
                    console.log('WS closed. Reconnecting...');
                    setTimeout(() => switchSymbol(currentSymbol), 3000); 
                };
            }

            window.onload = () => { 
                initChart(); 
                switchSymbol('BTCUSDT'); 
            };
        </script>
    </body>
    </html>
    """
