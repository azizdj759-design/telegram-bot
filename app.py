import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from core.data_fetcher import DataFetcher
from core.smc_engine import SMCEngine
from core.wave_engine import WaveEngine
from core.signal_aggregator import SignalAggregator

# إعدادات الصفحة
st.set_page_config(page_title="منصة التحليل المؤسسي", layout="wide", initial_sidebar_state="expanded")
st.title("منصة التحليل المؤسسي للأسواق")
st.caption("محرك توافق متقدم (ICT/SMC + الموجات) مع رسم مناطق الصفقة على الشارت")

# التحديث التلقائي كل 60 ثانية
st_autorefresh(interval=60_000, key="market_refresh")

with st.sidebar:
    st.header("إعدادات التحليل")
    symbol = st.selectbox("الأصل", [
        "BTC/USDT (بيتكوين)", 
        "GC=F (الذهب)", 
        "CL=F (البترول)"
    ])
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

symbol_map = {
    "BTC/USDT (بيتكوين)": "BTC/USDT", 
    "GC=F (الذهب)": "GC=F", 
    "CL=F (البترول)": "CL=F"
}
symbol_raw = symbol_map[symbol]

try:
    with st.spinner("جاري تحليل السوق..."):
        df, current_price, final = run_analysis(symbol_raw, timeframe, min_confluence)

    # --- عرض النتائج النصية ---
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

    # --- شارت Plotly الاحترافي ---
    st.subheader("الرسم البياني التفاعلي")

    fig = go.Figure()

    # 1. رسم الشموع اليابانية
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        name="السعر"
    ))

    # 2. رسم منطقة الصفقة (إذا وجدت)
    if final["decision"] != "انتظار" and final["entry"] is not None:
        entry = final["entry"]
        sl = final["stop_loss"]
        tp = final["take_profit"]

        # مستطيل منطقة الدخول (يظلل بين الدخول والهدف)
        fig.add_shape(
            type="rect",
            x0=df.index[-1],
            x1=df.index[-1] + pd.Timedelta(hours=10), # عرض المستطيل
            y0=min(entry, tp),
            y1=max(entry, tp),
            fillcolor="rgba(38, 166, 154, 0.2)", # لون أخضر شفاف
            line=dict(width=0),
            layer="below"
        )
        
        # خط الدخول
        fig.add_hline(y=entry, line_dash="dash", line_color="#2962FF", annotation_text="دخول", annotation_position="top left")
        
        # خط وقف الخسارة
        fig.add_hline(y=sl, line_dash="dot", line_color="#EF5350", annotation_text="وقف خسارة", annotation_position="bottom left")
        
        # خط الهدف
        if tp:
            fig.add_hline(y=tp, line_dash="dot", line_color="#26A69A", annotation_text="هدف", annotation_position="top left")

    # تنسيق الشارت
    fig.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"حدث خطأ في التحليل: {e}")
