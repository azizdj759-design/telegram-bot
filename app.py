import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from lightweight_charts_v5 import lightweight_charts_v5_component
from core.data_fetcher import DataFetcher
from core.smc_engine import SMCEngine
from core.wave_engine import WaveEngine
from core.signal_aggregator import SignalAggregator

# إعدادات الصفحة
st.set_page_config(page_title="محلل الأسواق المتعدد", layout="wide", initial_sidebar_state="expanded")
st.title("محلل الأسواق متعدد الاستراتيجيات")
st.caption("تحليل فني متقدم: SMC/ICT والتحليل الموجي، مع إشارات دخول وخروج وأهداف")

# التحديث التلقائي كل 60 ثانية
st_autorefresh(interval=60_000, key="market_refresh")

with st.sidebar:
    st.header("لوحة التحكم")
    # الأصول المطلوبة فقط
    symbol = st.selectbox("الأصل المالي", [
        "BTC/USDT (بيتكوين)",
        "GC=F (الذهب)",
        "CL=F (البترول)"
    ])
    timeframe = st.selectbox("الإطار الزمني", ["1h", "4h", "1d"], index=1)
    min_confluence = st.slider("الحد الأدنى للتوافق", 1, 3, 2)
    st.info("يتم تحديث البيانات تلقائياً كل 60 ثانية.")

@st.cache_data(ttl=60)
def run_analysis(symbol_raw, timeframe, min_confluence):
    fetcher = DataFetcher()
    df = fetcher.fetch_ohlcv(symbol_raw, timeframe)
    current_price = fetcher.get_current_price(symbol_raw)

    smc_signal = SMCEngine().analyze(df)
    wave_signal = WaveEngine().analyze(df)

    aggregator = SignalAggregator(min_confluence=min_confluence)
    final = aggregator.aggregate([smc_signal, wave_signal])
    
    # حساب نسبة النجاح بناءً على عدد الاستراتيجيات المتفقة
    confidence_score = 0
    if final["decision"] != "انتظار":
        confidence_score = (final.get("confluence_count", 0) / 2) * 100
        if final.get("risk_reward", 0) >= 2:
            confidence_score = min(100, confidence_score + 10)
    
    return df, current_price, smc_signal, wave_signal, final, confidence_score

# استخراج الرمز البرمجي
symbol_map = {"BTC/USDT (بيتكوين)": "BTC/USDT", "GC=F (الذهب)": "GC=F", "CL=F (البترول)": "CL=F"}
symbol_raw = symbol_map[symbol]

try:
    with st.spinner("جاري تحديث البيانات والتحليل..."):
        df, current_price, smc_sig, wave_sig, final, confidence = run_analysis(symbol_raw, timeframe, min_confluence)

    # عرض السعر الحالي
    st.metric("السعر الحالي", f"${current_price:,.2f}")

    st.header("القرار النهائي")
    if final["decision"] == "انتظار":
        st.warning(f"الوضع الحالي: انتظار — {final['reason']}")
    else:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.success(f"القرار: {final['decision']}")
        with col2:
            st.metric("نسبة النجاح المتوقعة", f"{confidence:.0f}%")
            st.progress(confidence / 100)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("نقطة الدخول", f"${final['entry']:,.2f}")
        c2.metric("وقف الخسارة", f"${final['stop_loss']:,.2f}")
        c3.metric("الهدف", f"${final['take_profit']:,.2f}" if final["take_profit"] else "—")
        c4.metric("المخاطرة/العائد", f"1:{final['risk_reward']}" if final["risk_reward"] else "—")
        st.caption(f"الاستراتيجيات المتفقة: {', '.join(final['confluence_strategies'])}")

    # تفاصيل الاستراتيجيات
    st.header("تفاصيل الاستراتيجيات")
    tab1, tab2 = st.tabs(["SMC / ICT", "التحليل الموجي"])
    with tab1: st.json(smc_sig)
    with tab2: st.json(wave_sig)

    # شارت TradingView
    st.header("الرسم البياني")
    
    # تحويل البيانات إلى تنسيق Lightweight Charts
    chart_data = []
    for index, row in df.iterrows():
        chart_data.append({
            "time": str(index.date()) if timeframe == "1d" else str(index),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "value": float(row["close"])
        })

    series_config = [{
        "type": "Candlestick",
        "data": chart_data,
        "options": {
            "upColor": "#26a69a",
            "downColor": "#ef5350",
            "borderVisible": False,
            "wickUpColor": "#26a69a",
            "wickDownColor": "#ef5350"
        }
    }]

    # إضافة خطوط الدخول والخروج إذا وجدت
    if final["entry"]:
        lines = [
            {"price": final["entry"], "color": "#2962FF", "title": "Entry"},
            {"price": final["stop_loss"], "color": "#EF5350", "title": "SL"},
            {"price": final["take_profit"], "color": "#26A69A", "title": "TP"}
        ]
        series_config[0]["price_lines"] = lines

    lightweight_charts_v5_component(
        name=f"{symbol} Chart",
        charts=[{
            "chart": {
                "layout": {
                    "background": {"color": "#131722"},
                    "textColor": "#d1d4dc"
                },
                "grid": {
                    "vertLines": {"color": "#2B2B43"},
                    "horzLines": {"color": "#363C4E"}
                },
                "crosshair": {"mode": 0}
            },
            "series": series_config,
            "height": 550
        }],
        height=550
    )

except Exception as e:
    st.error(f"حدث خطأ: {e}")
    st.exception(e) # لعرض تفاصيل الخطأ للمطور
