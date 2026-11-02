import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from streamlit_lightweight_charts_pro import renderChart
from core.data_fetcher import DataFetcher
from core.smc_engine import SMCEngine
from core.wave_engine import WaveEngine
from core.signal_aggregator import SignalAggregator

# إعدادات الصفحة
st.set_page_config(page_title="منصة التحليل المؤسسي", layout="wide", initial_sidebar_state="collapsed")
st.title("منصة التحليل المؤسسي للأسواق")
st.caption("محرك توافق متقدم (ICT/SMC + الموجات) مع رسم مناطق الصفقة على الشارت")

# التحديث التلقائي
st_autorefresh(interval=60_000, key="market_refresh")

with st.sidebar:
    st.header("إعدادات التحليل")
    symbol = st.selectbox("الأصل", ["BTC/USDT (بيتكوين)", "GC=F (الذهب)", "CL=F (البترول)"])
    timeframe = st.selectbox("الإطار الزمني", ["1h", "4h", "1d"], index=1)
    min_confluence = st.slider("الحد الأدنى للتوافق", 1, 2, 2)

@st.cache_data(ttl=60)
def run_analysis(symbol_raw, timeframe, min_confluence):
    fetcher = DataFetcher()
    df = fetcher.fetch_ohlcv(symbol_raw, timeframe)
    current_price = fetcher.get_current_price(symbol_raw)

    smc_signal = SMCEngine().analyze(df)
    wave_signal = WaveEngine().analyze(df)

    aggregator = SignalAggregator(min_confluence=min_confluence)
    final = aggregator.aggregate([smc_signal, wave_signal])
    
    return df, current_price, final

symbol_map = {"BTC/USDT (بيتكوين)": "BTC/USDT", "GC=F (الذهب)": "GC=F", "CL=F (البترول)": "CL=F"}
symbol_raw = symbol_map[symbol]

try:
    with st.spinner("جاري تحليل السوق..."):
        df, current_price, final = run_analysis(symbol_raw, timeframe, min_confluence)

    # --- عرض النتائج ---
    col1, col2, col3 = st.columns(3)
    col1.metric("السعر الحالي", f"${current_price:,.2f}")
    
    if final["decision"] == "انتظار":
        col2.warning(f"الوضع: {final['reason']}")
        col3.metric("نسبة النجاح", "0%")
    else:
        col2.success(f"القرار: {final['decision']}")
        col3.metric("نسبة النجاح المتوقعة", f"{final['win_rate']}%")

    if final["decision"] != "انتظار":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("نقطة الدخول", f"${final['entry']:,.2f}")
        c2.metric("وقف الخسارة", f"${final['stop_loss']:,.2f}")
        c3.metric("الهدف", f"${final['take_profit']:,.2f}" if final["take_profit"] else "—")
        c4.metric("المخاطرة/العائد", f"1:{final['risk_reward']}")

    # --- شارت TradingView المتقدم ---
    st.subheader("الرسم البياني التفاعلي")
    
    # تحويل البيانات إلى تنسيق الشارت
    chart_data = []
    for index, row in df.iterrows():
        chart_data.append({
            "time": str(index.date()) if timeframe == "1d" else str(index),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })

    # إعداد الشارت الأساسي
    chart_options = {
        "layout": {"background": {"color": "#131722"}, "textColor": "#d1d4dc"},
        "grid": {"vertLines": {"color": "#2B2B43"}, "horzLines": {"color": "#363C4E"}},
    }

    series = [{
        "type": "Candlestick",
        "data": chart_data,
        "options": {"upColor": "#26a69a", "downColor": "#ef5350"}
    }]

    # --- رسم مناطق الصفقة مباشرة على الشارت ---
    if final["decision"] != "انتظار":
        # إضافة خطوط أفقية للدخول ووقف الخسارة والهدف
        series[0]["price_lines"] = [
            {"price": final["entry"], "color": "#2962FF", "title": "Entry"},
            {"price": final["stop_loss"], "color": "#EF5350", "title": "SL"},
            {"price": final["take_profit"], "color": "#26A69A", "title": "TP"}
        ]
        
        # إضافة مستطيل يظلل منطقة الصفقة (من الدخول إلى الهدف/الوقف)
        # نستخدم علامة (marker) أو مستطيل إذا كانت المكتبة تدعم ذلك
        # في lightweight-charts-pro، يمكن استخدام annotations
        # للتبسيط، سنعتمد على الخطوط الأفقية الواضحة

    renderChart(
        series=series,
        options=chart_options,
        height=600
    )

except Exception as e:
    st.error(f"حدث خطأ في التحليل: {e}")
