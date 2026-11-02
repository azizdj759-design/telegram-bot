import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from core.data_fetcher import DataFetcher
from core.smc_engine import SMCEngine
from core.wave_engine import WaveEngine
from core.signal_aggregator import SignalAggregator

st.set_page_config(page_title="محلل التقاء الاستراتيجيات", layout="wide")
st.title("📊 محلل الكريبتو والفوركس متعدد الاستراتيجيات")

# --- التحديث التلقائي ---
# تحديث الصفحة كل 60 ثانية (أو 5 دقائق حسب الحاجة)
st_autorefresh(interval=60_000, key="market_refresh")

with st.sidebar:
    st.header("الإعدادات")
    # إضافة الذهب والفوركس إلى القائمة
    symbol = st.selectbox("الأصل", [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", 
        "XAUUSD=X",  # الذهب مقابل الدولار
        "EURUSD=X",  # اليورو مقابل الدولار
        "GBPUSD=X"   # الجنيه مقابل الدولار
    ])
    timeframe = st.selectbox("الإطار الزمني", ["1h", "4h", "1d"], index=1)
    min_confluence = st.slider("الحد الأدنى للتوافق", 1, 3, 2)
    st.caption("يتم تحديث البيانات تلقائياً كل 60 ثانية.")

@st.cache_data(ttl=60) # تقليل مدة التخزين المؤقت لتحديث أسرع
def run_analysis(symbol, timeframe, min_confluence):
    fetcher = DataFetcher()
    df = fetcher.fetch_ohlcv(symbol, timeframe)
    current_price = fetcher.get_current_price(symbol)

    smc_signal = SMCEngine().analyze(df)
    wave_signal = WaveEngine().analyze(df)

    aggregator = SignalAggregator(min_confluence=min_confluence)
    final = aggregator.aggregate([smc_signal, wave_signal])
    
    # --- حساب نسبة النجاح (محاكاة بسيطة بناءً على التوافق) ---
    confidence_score = (final.get("confluence_count", 0) / 3) * 100
    if final["decision"] == "انتظار":
        confidence_score = 0
    
    return df, current_price, smc_signal, wave_signal, final, confidence_score

try:
    with st.spinner("جاري تحديث البيانات والتحليل..."):
        df, current_price, smc_sig, wave_sig, final, confidence = run_analysis(symbol, timeframe, min_confluence)

    st.metric("السعر الحالي", f"${current_price:,.2f}")

    st.header("🎯 القرار النهائي")
    if final["decision"] == "انتظار":
        st.warning(f"⏸️ **انتظار** — {final['reason']}")
    else:
        st.success(f"**القرار: {final['decision']}**")
        
        # عرض نسبة النجاح بشكل بصري
        st.metric("نسبة النجاح المتوقعة", f"{confidence:.0f}%")
        st.progress(confidence / 100)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("نقطة الدخول", f"${final['entry']:,.2f}")
        c2.metric("وقف الخسارة", f"${final['stop_loss']:,.2f}")
        c3.metric("الهدف", f"${final['take_profit']:,.2f}" if final["take_profit"] else "—")
        c4.metric("المخاطرة/العائد", f"1:{final['risk_reward']}" if final["risk_reward"] else "—")

    st.header("🔍 تفاصيل الاستراتيجيات")
    tab1, tab2 = st.tabs(["SMC / ICT", "التحليل الموجي"])
    with tab1: st.json(smc_sig)
    with tab2: st.json(wave_sig)

    st.header("📈 الرسم البياني")
    fig = go.Figure(data=[go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="green", decreasing_line_color="red"
    )])
    if final["entry"]:
        fig.add_hline(y=final["entry"], line_dash="dash", line_color="blue", annotation_text="Entry")
        fig.add_hline(y=final["stop_loss"], line_dash="dot", line_color="red", annotation_text="SL")
        if final["take_profit"]:
            fig.add_hline(y=final["take_profit"], line_dash="dot", line_color="green", annotation_text="TP")
    fig.update_layout(xaxis_rangeslider_visible=False, height=550)
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"حدث خطأ: {e}")
